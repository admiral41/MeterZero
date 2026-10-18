"""Gemini energy analyst: answers plant questions by calling MeterZero's own numbers.

Gemini never sees raw data or the hidden ground truth. It gets tools that return
the model's estimates *with their uncertainty*, plus a what-if planner that prices
schedule changes and repairs, and it is told to quote those numbers rather than
guess. Every tool call is logged (and can be streamed to the UI as it happens).

Three ways it's used:
  * EnergyAgent.ask        a chat turn (text, or a transcribed voice question)
  * EnergyAgent.investigate the Energy Detective: Gemini plans its own investigation,
                           calls up to 25 tools, and returns ranked, structured findings
  * vision.py               reading logbook pages and nameplates from photos

Configure with either
    GEMINI_API_KEY=...                       (Google AI Studio key), or
    GOOGLE_GENAI_USE_VERTEXAI=true           (Vertex AI, e.g. on Cloud Run with a
    GOOGLE_CLOUD_PROJECT=... GOOGLE_CLOUD_LOCATION=global   service account, no key)
and optionally GEMINI_MODEL (default below).

Note: no `from __future__ import annotations` here. The Gemini SDK reads the tool
functions' type hints at runtime to build their schemas.
"""
import functools
import json
import os
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd
from pydantic import BaseModel, Field

from . import anomalies as anomaly_checks
from . import daily, savings
from .data import OTHER
from .explain import explain_machine

DEFAULT_MODEL = "gemini-3.8-flash"

SYSTEM_PROMPT = """\
You are MeterZero, an energy analyst for a manufacturing plant. The plant has one
main electricity meter; MeterZero's model splits it into per-machine and
per-product energy with calibrated uncertainty bands, flags waste, and can price
schedule changes and repairs under the plant's tariff.

Rules:
- Get every number from the tools. Never invent figures. If a tool can't answer, say so.
- Always give the likely range with an estimate, in plain words: "about 412 kWh (likely 394-430)",
  "saves about $84 a month (likely $44-$124)". The tools give "plus_minus" values: range = value ± that.
- Money: use the tariff tools and the currency they return.
- Be concrete and practical: name the machine, the size of the opportunity, and the next action.
- When comparing options, actually run each option through the planner before recommending one.
- Point out practical catches the tools report (batches clashing, night staffing needed).
- Write for a plant manager, not an engineer. Short sentences, everyday words. Never use words like
  disaggregation, reconciliation, sd, band, prior, model, tool or function in answers.
- Keep answers short: a few sentences or a compact list. Use Markdown.
- If asked how reliable the model is, use the overview's held-out test scores.
- Mention that the data comes from a simulated factory if the user asks where it comes from.
"""

DETECTIVE_PROMPT = """\
Investigate this plant's energy for the analysis week like an experienced energy auditor,
and find the three most valuable opportunities. Work step by step with the tools:
1. Get the overview and the tariff breakdown (when is energy bought, at what price).
2. Check for waste alerts; for each, look at the machine's overnight history and price the fix.
3. Look for schedule opportunities: try at least three different batch shifts with the planner
   (different lines/products, earlier and later), and keep the best one that doesn't clash
   with other batches.
4. Check where the model is least certain (sensor recommendation) and whether that matters.
Then write a short report for the plant manager in plain words: for each of the top three findings
say what you found, the evidence (numbers from the tools), the monthly saving with its likely range,
how sure you are, and what to do. Finish with one line on what to do first and why.
"""

def gemini_model() -> str:
    return os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)


def gemini_status() -> str | None:
    """None if Gemini is configured, otherwise a hint on how to configure it."""
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return None
    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true"):
        return None
    return "Set GEMINI_API_KEY (AI Studio) or GOOGLE_GENAI_USE_VERTEXAI=true with a Google Cloud project."


def make_client(api_key: str | None = None):
    """A Gemini client: the user's key if given, else the server's key, else Vertex AI settings."""
    from google import genai

    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true") and not api_key:
        return genai.Client()
    # Keys pasted into a file or a secret often carry a stray newline, which the API rejects.
    key = (api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    return genai.Client(api_key=key) if key else genai.Client()


def _round(value, digits: int = 1):
    return round(float(value), digits)


class EnergyTools:
    """The functions Gemini may call. Each returns plain JSON-friendly data."""

    def __init__(self, results, tariff: savings.Tariff | None = None):
        self.results = results
        self.tariff = tariff or savings.Tariff()
        self.names = dict(zip(results.machines["id"], results.machines["name"]))
        self.names[OTHER] = "Other loads (unmetered)"

    # -- helpers ---------------------------------------------------------------

    def _machine(self, machine: str) -> str:
        key = machine.strip().lower()
        for machine_id, name in self.names.items():
            if key in (machine_id.lower(), name.lower()) or key in name.lower():
                return machine_id
        raise ValueError(f"Unknown machine '{machine}'. Known: {', '.join(self.names.values())}")

    def _window(self, day: str):
        index = self.results.meter.index
        if not day:
            return index[0], index[-1] + pd.Timedelta(minutes=1)
        start = pd.Timestamp(day).normalize()
        if start < index[0].normalize() or start > index[-1]:
            raise ValueError(f"Day must be between {index[0]:%Y-%m-%d} and {index[-1]:%Y-%m-%d}")
        return start, start + pd.Timedelta(days=1)

    # -- what is happening -------------------------------------------------------

    def get_factory_overview(self) -> dict:
        """Machines, the analysis period, site energy, each machine's share, and how accurate the model is."""
        r = self.results
        kwh = r.estimate.sum() / 60
        final = r.ladder.iloc[-1]
        return {
            "data_source": f"simulated plant with {len(r.machines)} machines (sub-meters hidden from the model)",
            "period": f"{r.meter.index[0]:%Y-%m-%d} to {r.meter.index[-1]:%Y-%m-%d}",
            "site_energy_kwh": _round(r.meter.sum() / 60, 0),
            "machines": [
                {"id": m.id, "name": m.name, "line": m.line, "kind": m.kind,
                 "estimated_kwh": _round(kwh[m.id], 0), "share_of_site": f"{kwh[m.id] / kwh.sum():.0%}"}
                for m in r.machines.itertuples()
            ] + [{"id": OTHER, "name": self.names[OTHER], "estimated_kwh": _round(kwh[OTHER], 0),
                  "share_of_site": f"{kwh[OTHER] / kwh.sum():.0%}"}],
            "production_lines": {line: sorted(g["product"].unique()) for line, g in r.log.groupby("line")},
            "model_reliability_on_held_out_week": {
                "disaggregation_accuracy": f"{final['accuracy']:.1%}",
                "mean_abs_energy_error": f"{final['mean |energy error| %']:.1f}%",
                "held_out_coverage_of_90pct_bands": f"{r.coverage_by_machine.mean():.0%}",
            },
        }

    def get_machine_energy(self, machine: str, day: str = "") -> dict:
        """Estimated energy of one machine, with a 90% band. `day` is YYYY-MM-DD, or empty for the whole period."""
        machine = self._machine(machine)
        start, end = self._window(day)
        e = explain_machine(self.results, machine, start, end)
        window = self.results.estimate.loc[start:end - pd.Timedelta(minutes=1), machine]
        return {
            "machine": e["name"], "period": day or "whole period",
            "estimated_kwh": _round(e["final kWh"]), "plus_minus_kwh_90pct": _round(e["90% band ± kWh"]),
            "share_of_site": f"{e['share of site energy']:.0%}",
            "peak_kw": _round(window.max()), "peak_time": f"{window.idxmax():%Y-%m-%d %H:%M}",
        }

    def explain_estimate(self, machine: str, day: str = "") -> dict:
        """Why the model gave this machine its number: learned guess, meter adjustment, production, top drivers."""
        start, end = self._window(day)
        e = explain_machine(self.results, self._machine(machine), start, end)
        return {
            "machine": e["name"], "kind": e["kind"],
            "final_kwh": _round(e["final kWh"]), "plus_minus_kwh_90pct": _round(e["90% band ± kWh"]),
            "learned_guess_kwh": _round(e["learned guess kWh"]),
            "meter_adjustment_kwh": _round(e["meter adjustment kWh"]),
            "share_of_meter_gap_absorbed": f"{e['share of the meter gap it absorbs']:.0%}",
            "production_on_its_line": e.get("production", [])[:6],
            "model_relies_on": [d["meaning"] for d in e["top drivers"][:4]],
        }

    def get_daily_profile(self, day: str) -> dict:
        """Per-machine kWh for one day (YYYY-MM-DD), plus the site's peak hour and the batches run."""
        start, end = self._window(day)
        window = slice(start, end - pd.Timedelta(minutes=1))
        kwh = self.results.estimate.loc[window].sum() / 60
        hourly = self.results.meter.loc[window].groupby(self.results.meter.loc[window].index.hour).mean()
        log = self.results.log
        batches = log[(log["start"] >= start) & (log["start"] < end)]
        return {
            "day": f"{start:%A %Y-%m-%d}",
            "site_kwh": _round(kwh.sum(), 0),
            "kwh_by_machine": {self.names[m]: _round(v, 0) for m, v in kwh.sort_values(ascending=False).items()},
            "peak_hour": f"{int(hourly.idxmax()):02d}:00 ({hourly.max():.0f} kW average)",
            "batches": [f"line {b.line}: {b.product} {b.start:%H:%M}-{b.end:%H:%M}" for b in batches.itertuples()],
        }

    def get_hourly_profile(self, machine: str, day: str = "") -> dict:
        """A machine's average kW for each hour of the day (one day, or averaged over the whole period)."""
        machine = self._machine(machine)
        start, end = self._window(day)
        series = self.results.estimate.loc[start:end - pd.Timedelta(minutes=1), machine]
        hourly = series.groupby(series.index.hour).mean()
        return {"machine": self.names[machine], "period": day or "average over the period",
                "kw_by_hour": {f"{h:02d}:00": _round(v) for h, v in hourly.items()}}

    def get_overnight_history(self, machine: str) -> dict:
        """A machine's average kW between 23:00 and 05:00 for every night, validation week then analysis week."""
        machine = self._machine(machine)
        profile = self.results.overnight[self.results.overnight["machine"] == machine]
        return {"machine": self.names[machine], "nights": [
            {"night": f"{row['night']:%a %Y-%m-%d}", "period": row["period"], "kw": _round(row["estimated"], 2)}
            for row in profile.to_dict("records")
        ]}

    def get_product_energy(self, product: str = "") -> dict:
        """kWh per unit for each product (or one product), with a 90% band, from batch-level estimates."""
        table = self.results.products
        if product:
            table = table[table["product"].str.lower() == product.strip().lower()]
            if table.empty:
                raise ValueError(f"Unknown product. Known: {', '.join(self.results.products['product'])}")
        return {"products": [
            {"product": row["product"], "line": row["line"], "batches": int(row["batches"]),
             "units": int(row["units"]), "kwh_per_unit": round(row["estimated kWh/unit"], 4),
             "plus_minus_90pct": round(row["± kWh/unit (90%)"], 4)}
            for row in table.to_dict("records")
        ]}

    def get_anomalies(self) -> dict:
        """Machines whose overnight draw jumped above their usual level (leaks, kit left on), with wasted kWh/day."""
        summary = anomaly_checks.summarize_alerts(self.results.anomalies)
        if summary.empty:
            return {"alerts": [], "note": "No machine is drawing more than usual overnight."}
        return {"alerts": [
            {"machine": self.names[row["machine"]], "machine_id": row["machine"],
             "since": f"{row['first night']:%a %Y-%m-%d}", "nights_flagged": int(row["nights flagged"]),
             "usual_overnight_kw": _round(row["usual kW"]), "observed_overnight_kw": _round(row["observed kW"]),
             "wasted_kwh_per_day_if_it_persists": _round(row["kWh/day if it persists"], 0)}
            for row in summary.to_dict("records")
        ]}

    def get_sensor_recommendation(self) -> dict:
        """Which extra sensor would cut estimation error the most, and accuracy vs number of sensors."""
        r = self.results
        check = r.sensor_check
        return {
            "ranking": [
                {"machine": self.names[row["machine"]],
                 "expected_error_reduction_kw": _round(row["expected reduction (kW)"], 2)}
                for row in check.to_dict("records")
            ],
            "accuracy_by_sensor_count": [
                {"extra_sensors": int(b.sensors), "added": self.names.get(b.added, ""),
                 "accuracy": f"{b.recommended:.1%}", "random_placement_accuracy": f"{b.random:.1%}"}
                for b in r.budget.itertuples()
            ],
        }

    # -- what it costs and what to change ---------------------------------------

    def get_tariff_breakdown(self) -> dict:
        """The tariff bands (hours and price), the site's energy and cost in each band, its peak and monthly bill."""
        t = self.tariff
        bands = savings.cost_by_band(self.results.meter, t)
        current = savings.bill(self.results.meter, t)
        return {
            "currency": t.currency,
            "bands": [{"band": name, "hours": f"{start:02d}:00-{end:02d}:00", "price_per_kwh": price,
                       "share_of_site_kwh": f"{bands.loc[name, 'share of kWh']:.0%}",
                       "cost_this_week": _round(bands.loc[name, "cost"], 0)}
                      for name, start, end, price in t.bands],
            "demand_charge_per_kw_month": t.demand_charge,
            "peak_15min_kw": _round(current.peak_kw),
            "estimated_monthly_bill": _round(current.monthly_cost, 0),
        }

    def plan_schedule_shift(self, line: str, hours: float, product: str = "") -> dict:
        """Price moving every batch on a line (or only one product) by `hours` (negative = earlier). Reports
        the monthly saving with a band, peak change, and practical catches (clashes, night staffing)."""
        plan = savings.plan_shift(self.results, self.tariff, line.strip().upper(), product.strip(), float(hours))
        return plan.summary()

    def plan_fix_waste(self, machine: str) -> dict:
        """What repairing a machine with a waste alert is worth per month and per year, with a band."""
        return savings.plan_fix_waste(self.results, self.tariff, self._machine(machine))

    def estimate_cost_and_carbon(self, kg_co2_per_kwh: float = 0.0) -> dict:
        """Energy cost (at the tariff's average price) and CO2 per machine and per product unit.

        Leave kg_co2_per_kwh at 0 to use the plant's regional grid factor."""
        kg_co2_per_kwh = kg_co2_per_kwh or self.tariff.co2_kg_per_kwh
        price = float(self.tariff.price_by_hour().mean())
        kwh = self.results.estimate.sum() / 60
        products = self.results.products
        return {
            "assumptions": {"average_price_per_kwh": round(price, 3), "kg_co2_per_kwh": kg_co2_per_kwh,
                            "currency": self.tariff.currency, "period": "analysis week"},
            "per_machine": {self.names[m]: {"cost": _round(v * price, 0), "kg_co2": _round(v * kg_co2_per_kwh, 0)}
                            for m, v in kwh.items()},
            "per_unit": {
                row["product"]: {"cost": round(row["estimated kWh/unit"] * price, 4),
                                 "kg_co2": round(row["estimated kWh/unit"] * kg_co2_per_kwh, 4)}
                for row in products.to_dict("records")
            },
        }

    def get_morning_check(self, day: str = "") -> dict:
        """The morning check for one day (YYYY-MM-DD, default the last full day): energy and cost, energy used
        while nothing was running, overnight waste, energy bought at the expensive time, products using more than usual."""
        index = self.results.meter.index
        start = pd.Timestamp(day).normalize() if day else index[-1].normalize() - pd.Timedelta(days=1)
        self._window(f"{start:%Y-%m-%d}")
        lines = daily.morning_check(self.results, start, self.tariff)
        return {"day": f"{start:%A %Y-%m-%d}", "checks": [
            {"topic": line.kind, "status": {True: "fine", False: "needs attention", None: "tip"}[line.good],
             "text": line.text} for line in lines
        ]}

    def get_energy_without_production(self) -> dict:
        """Energy each machine used that went into no product (warm-ups, idling between batches, nights)."""
        flows = self.results.flows
        idle = flows[flows["destination"] == "Idle & overhead"].set_index("machine")["kWh"]
        total = self.results.meter.sum() / 60
        return {
            "period": "analysis week",
            "total_kwh": _round(idle.sum(), 0),
            "share_of_site": f"{idle.sum() / total:.0%}",
            "by_machine_kwh": {self.names[m]: _round(v, 0) for m, v in idle.sort_values(ascending=False).items()},
        }

    def functions(self) -> list:
        return [
            self.get_factory_overview, self.get_machine_energy, self.explain_estimate,
            self.get_daily_profile, self.get_hourly_profile, self.get_overnight_history,
            self.get_product_energy, self.get_anomalies, self.get_sensor_recommendation,
            self.get_tariff_breakdown, self.plan_schedule_shift, self.plan_fix_waste,
            self.estimate_cost_and_carbon, self.get_morning_check, self.get_energy_without_production,
        ]


# --------------------------------------------------------------------------- structured findings


class Finding(BaseModel):
    title: str = Field(description="Short plain headline a plant manager understands, e.g. 'Fix the air leak on the compressor'")
    kind: str = Field(description="One of: waste, schedule, sensor, product, other")
    machine: str = Field(description="Machine id this is about (e.g. 'compressor'), or '' if none")
    evidence: str = Field(description="Why, in one or two plain sentences with the key numbers. No jargon.")
    monthly_saving: float = Field(description="Monthly saving in the tariff currency, 0 if not a saving")
    saving_plus_minus: float = Field(description="90% band on the saving, 0 if none")
    confidence: str = Field(description="high, medium or low")
    action: str = Field(description="What to do next, one plain sentence")


class Findings(BaseModel):
    headline: str = Field(description="One plain sentence: the single most important thing for the plant manager to do")
    findings: list[Finding]


@dataclass
class Reply:
    text: str
    tool_calls: list[dict] = field(default_factory=list)


@dataclass
class Investigation:
    report: str
    findings: Findings
    tool_calls: list[dict]


class EnergyAgent:
    """A Gemini chat session wired to EnergyTools, with automatic function calling."""

    def __init__(self, results, client=None, model: str | None = None, tariff: savings.Tariff | None = None,
                 on_tool_call: Callable[[dict], None] | None = None, max_tool_calls: int = 10):
        from google.genai import types

        self.model = model or gemini_model()
        self.client = client or make_client()
        self.calls: list[dict] = []
        self.on_tool_call = on_tool_call
        self.tools = EnergyTools(results, tariff)
        self.chat = self.client.chats.create(
            model=self.model,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[self._logged(f) for f in self.tools.functions()],
                temperature=0.3,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    maximum_remote_calls=max_tool_calls
                ),
            ),
        )

    def _logged(self, function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            entry = {"tool": function.__name__, "args": kwargs or list(args)}
            try:
                result = function(*args, **kwargs)
            except ValueError as error:  # hand the problem back to Gemini instead of crashing
                result = {"error": str(error)}
            entry["result"] = result
            self.calls.append(entry)
            if self.on_tool_call:
                self.on_tool_call(entry)
            return result

        return wrapper

    def ask(self, question: str) -> Reply:
        self.calls = []
        response = self.chat.send_message(question)
        return Reply(text=response.text or "(no answer)", tool_calls=list(self.calls))

    def briefing(self) -> Reply:
        return self.ask(
            "Write a one-page energy briefing for the plant manager for this period. Sections: "
            "**Where the energy went** (top machines with bands), **Energy per product**, "
            "**Waste found** (alerts with the monthly cost of fixing vs not fixing), "
            "**Cheapest schedule change** (try a few with the planner), "
            "**Next sensor to install** (and the accuracy gain), **Three actions this week**. "
            "Use the tools for every number."
        )

    def investigate(self) -> Investigation:
        """Gemini runs its own investigation, then its report is turned into structured findings."""
        reply = self.ask(DETECTIVE_PROMPT)
        findings = structure_findings(self.client, self.model, reply, self.tools.results.machine_ids)
        return Investigation(reply.text, findings, reply.tool_calls)


def structure_findings(client, model: str, reply: Reply, machine_ids: list[str]) -> Findings:
    """Turn a free-text investigation into typed findings the UI can draw cards and charts for."""
    from google.genai import types

    evidence = json.dumps([{"tool": c["tool"], "args": c["args"], "result": c["result"]} for c in reply.tool_calls],
                          default=str)[:20000]
    response = client.models.generate_content(
        model=model,
        contents=(
            "Convert this energy investigation into structured findings, most valuable first (max 4). "
            "Only use numbers that appear in the report or the tool results. Machine ids must be one of: "
            f"{', '.join(machine_ids)}, other, or ''.\n\n"
            f"REPORT:\n{reply.text}\n\nTOOL RESULTS:\n{evidence}"
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=Findings, temperature=0
        ),
    )
    return response.parsed if isinstance(response.parsed, Findings) else Findings.model_validate_json(response.text)


def transcribe(client, audio: bytes, mime_type: str = "audio/wav", model: str | None = None) -> str:
    """Speech to text with Gemini, for asking questions by voice on the shop floor."""
    from google.genai import types

    response = client.models.generate_content(
        model=model or gemini_model(),
        contents=[types.Part.from_bytes(data=audio, mime_type=mime_type),
                  "Transcribe this spoken question exactly. Reply with the transcript only."],
        config=types.GenerateContentConfig(temperature=0),
    )
    return (response.text or "").strip()
