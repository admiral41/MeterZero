"""A stand-in for the Gemini client, for tests and offline UI checks.

It behaves like the real SDK from MeterZero's point of view: chat turns call the
registered tools (as automatic function calling would) and structured requests
return parsed pydantic objects. Answers are built from what the tools returned.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from meterzero.agent import Findings
from meterzero.bill import BillReading
from meterzero.vision import LogbookPage, LogbookRow, Nameplate


class FakeChat:
    def __init__(self, tools):
        self.tools = {tool.__name__: tool for tool in tools}

    def call(self, name, **kwargs):
        return self.tools[name](**kwargs)

    def send_message(self, message):
        text = message if isinstance(message, str) else str(message)
        alerts = self.call("get_anomalies").get("alerts", [])
        lines = []
        if alerts:
            machine = alerts[0]["machine"]
            self.call("get_overnight_history", machine=machine)
            fix = self.call("plan_fix_waste", machine=machine)
            lines.append(f"- **{machine}** leak: saves {fix['currency']}{fix['monthly_saving']} "
                         f"± {fix['monthly_saving_plus_minus_90pct']}/month.")
        if "schedule" in text.lower() or "investigat" in text.lower() or "plan" in text.lower():
            self.call("get_tariff_breakdown")
            for line, hours in (("C", -2), ("C", 6), ("B", -3)):
                shift = self.call("plan_schedule_shift", line=line, hours=hours)
                if "error" not in shift:
                    lines.append(f"- {shift['change']}: {shift['monthly_saving']} ± "
                                 f"{shift['monthly_saving_plus_minus_90pct']}/month.")
            self.call("get_sensor_recommendation")
        self.call("get_machine_energy", machine="teleporter")  # a bad call, like a real model sometimes makes
        return SimpleNamespace(text="Findings:\n" + "\n".join(lines))


class FakeModels:
    def __init__(self, system_log=None, day: str = "2026-03-26"):
        self.system_log = system_log
        self.day = pd.Timestamp(day)

    def generate_content(self, model, contents, config=None):
        schema = getattr(config, "response_schema", None) if config is not None else None
        if schema is Findings:
            return SimpleNamespace(text="", parsed=Findings.model_validate({
                "headline": "Fix the compressed-air leak first: it is worth more than any schedule change.",
                "findings": [
                    {"title": "Compressed-air leak since Thursday", "kind": "waste", "machine": "compressor",
                     "evidence": "Overnight draw rose from about 1.5 kW to 5.5 kW.", "monthly_saving": 369,
                     "saving_plus_minus": 78, "confidence": "high", "action": "Run an ultrasonic leak survey."},
                    {"title": "Start the curing oven 2 hours earlier", "kind": "schedule", "machine": "oven",
                     "evidence": "Moves oven load out of the peak band without clashes.", "monthly_saving": 84,
                     "saving_plus_minus": 40, "confidence": "medium", "action": "Trial for one week."},
                    {"title": "Meter the chiller next", "kind": "sensor", "machine": "chiller",
                     "evidence": "Largest expected error reduction.", "monthly_saving": 0,
                     "saving_plus_minus": 0, "confidence": "high", "action": "Install a clamp meter."},
                ],
            }))
        if schema is LogbookPage:
            log = self.system_log
            next_day = self.day + pd.Timedelta(days=1)
            day = log[(log["start"] >= self.day) & (log["start"] < next_day)].sort_values(["line", "start"])
            rows = [LogbookRow(line=b.line, product=b.product.lower(), start=f"{b.start:%H:%M}",
                               end=f"{b.end:%H:%M}", units=int(b.units)) for b in day.itertuples()]
            return SimpleNamespace(text="", parsed=LogbookPage(date=f"{self.day:%Y-%m-%d}", rows=rows))
        if schema is BillReading:
            numbers = json.loads((Path(__file__).resolve().parents[1] / "samples" / "bills" / "np" / "2026-03.json").read_text())
            return SimpleNamespace(text="", parsed=BillReading.model_validate(numbers))
        if schema is Nameplate:
            return SimpleNamespace(text="", parsed=Nameplate(
                manufacturer="MZ Demo Air Systems", model="SC-22 VS", machine_type="rotary screw air compressor",
                rated_power_kw=22.0, voltage_v=400, current_a=41, year="2019"))
        return SimpleNamespace(text="Is anything wasting energy right now?", parsed=None)


class FakeClient:
    def __init__(self, system_log=None, day: str = "2026-03-26"):
        self.chats = SimpleNamespace(create=lambda model, config: FakeChat(config.tools))
        self.models = FakeModels(system_log, day)
