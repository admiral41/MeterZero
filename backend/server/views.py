"""Turn MeterZero results into compact JSON for the web app. Pure functions: results in, dicts out."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from meterzero import anomalies, daily, live, savings
from meterzero.batches import BUILDING, SHARED
from meterzero.data import OTHER
from meterzero.explain import explain_machine
from meterzero.plant import LIBRARY, PlantSpec

# Fixed categorical palette (validated for colour-vision deficiency in order); cycles only past 12 machines.
PALETTE = ["#3b82f6", "#f97316", "#10b981", "#eab308", "#ec4899", "#22c55e", "#8b5cf6", "#ef4444",
           "#06b6d4", "#a855f7", "#84cc16", "#f43f5e"]
OTHER_COLOR = "#94a3b8"
Z90 = 1.645
STATE = {"off": 0, "idle": 1, "running": 2}


def num(value, digits: int = 2):
    value = float(value)
    return None if math.isnan(value) or math.isinf(value) else round(value, digits)


def nums(values, digits: int = 2) -> list:
    return [None if not np.isfinite(v) else round(float(v), digits) for v in np.asarray(values, dtype=float)]


def day_slice(day: pd.Timestamp) -> slice:
    return slice(day, day + pd.Timedelta(days=1) - pd.Timedelta(minutes=1))


def days_available(results) -> list[str]:
    return [f"{d:%Y-%m-%d}" for d in results.meter.index.normalize().unique()]


def pick_day(results, day: str | None) -> pd.Timestamp:
    days = results.meter.index.normalize().unique()
    if day:
        chosen = pd.Timestamp(day).normalize()
        if chosen in days:
            return chosen
    weekdays = [d for d in days if d.dayofweek < 5]
    return (weekdays[3] if len(weekdays) > 3 else days[0])


# --------------------------------------------------------------------------- the plant and its machines


def machines_meta(results, spec: PlantSpec) -> list[dict]:
    placed = {m.id: m for m in spec.machines}
    peaks = results.estimate.max()
    rows = []
    for i, m in enumerate(results.machines.itertuples()):
        s = placed.get(m.id)
        kind = LIBRARY.get(s.type) if s else None
        rows.append({
            "id": m.id, "name": m.name, "line": m.line,
            "group": "Utilities" if m.line == SHARED else "Building" if m.line == BUILDING else f"Line {m.line}",
            "type": s.type if s else "", "type_label": kind.label if kind else "",
            "shape": kind.shape if kind else "cabinet", "size": list(kind.size) if kind else [1.6, 1.4, 1.2],
            "rated_kw": s.rated_kw if s else num(peaks[m.id], 1), "x": s.x if s else 2.0 + i * 2, "y": s.y if s else 2.0,
            "rotation": s.rotation if s else 0.0,
            "color": PALETTE[i % len(PALETTE)], "peak_kw": num(peaks[m.id], 2),
        })
    office = next((r for r in spec.rooms if "office" in r.name.lower()), None)
    ox, oy = (office.x + office.w * 0.55, office.y + office.d * 0.6) if office else (spec.panel_x + 2, spec.panel_y + 2)
    rows.append({
        "id": OTHER, "name": "Lights, offices & other" if spec.reference else "Unmetered loads", "line": "other",
        "group": "Building", "type": "office", "type_label": "Everything not listed", "shape": "desk",
        "size": [2.2, 1.2, 0.7], "rated_kw": num(peaks[OTHER], 1), "x": ox, "y": oy, "rotation": 0.0,
        "color": OTHER_COLOR, "peak_kw": num(peaks[OTHER], 2),
    })
    return rows


def plant_payload(results, spec: PlantSpec) -> dict:
    return {
        "spec": spec.model_dump(),
        "machines": machines_meta(results, spec),
        "days": days_available(results),
        "default_day": f"{pick_day(results, None):%Y-%m-%d}",
        "period": [f"{results.meter.index[0]:%Y-%m-%d}", f"{results.meter.index[-1]:%Y-%m-%d}"],
    }


# --------------------------------------------------------------------------- the live twin


def staffed_minutes(log: pd.DataFrame, index: pd.DatetimeIndex) -> np.ndarray:
    today = log[log["start"].dt.normalize() == index[0].normalize()]
    if today.empty:
        return np.zeros(len(index), bool)
    return ((index >= today["start"].min() - pd.Timedelta(hours=1))
            & (index <= today["end"].max() + pd.Timedelta(minutes=30)))


def timeline(results, spec: PlantSpec, tariff: savings.Tariff, day: str | None) -> dict:
    """Everything the 3D twin needs to replay one day, minute by minute, in the browser."""
    day = pick_day(results, day)
    window = day_slice(day)
    estimate, sd, truth = results.estimate.loc[window], results.estimate_sd.loc[window], results.truth.loc[window]
    features = results.test_features.loc[window]
    index = estimate.index
    staffed = staffed_minutes(results.log, index)

    machines = {}
    for m in list(results.machines.itertuples()) + [None]:
        machine_id = OTHER if m is None else m.id
        kw = estimate[machine_id].to_numpy()
        if m is None or m.line == BUILDING:
            running = staffed
        elif m.line == SHARED:
            running = features["lines_active"].to_numpy() > 0
        else:
            running = features.get(f"{m.line}_active", pd.Series(0, index=index)).to_numpy() > 0
        state = np.where(kw < live.OFF_KW, STATE["off"], np.where(running, STATE["running"], STATE["idle"]))
        machines[machine_id] = {
            "kw": nums(kw, 2), "low": nums(np.maximum(kw - Z90 * sd[machine_id].to_numpy(), 0), 1),
            "high": nums(kw + Z90 * sd[machine_id].to_numpy(), 1), "hidden": nums(truth[machine_id].to_numpy(), 2),
            "state": state.astype(int).tolist(),
        }

    log = results.log
    todays = log[(log["end"] > day) & (log["start"] < day + pd.Timedelta(days=1))]
    batches = [{"line": b.line, "product": b.product, "units": int(b.units),
                "start": max(int((b.start - day) / pd.Timedelta(minutes=1)), 0),
                "end": min(int((b.end - day) / pd.Timedelta(minutes=1)), 1440)} for b in todays.itertuples()]

    alerts = []
    for row in results.anomalies.to_dict("records"):
        night = row["night"]
        for start, end in ((night - pd.Timedelta(hours=1), night + pd.Timedelta(hours=5)),):
            a = max(int((start - day) / pd.Timedelta(minutes=1)), 0)
            b = min(int((end - day) / pd.Timedelta(minutes=1)), 1440)
            if b > a:
                alerts.append({"machine": row["machine"], "from": a, "to": b,
                               "usual_kw": num(row["usual kW"]), "observed_kw": num(row["observed kW"])})

    events = live.events_between(results, day - pd.Timedelta(minutes=1), day + pd.Timedelta(days=1), tariff)
    prices = tariff.price_by_hour()
    return {
        "day": f"{day:%Y-%m-%d}", "weekday": f"{day:%A}", "minutes": len(index),
        "meter": nums(results.meter.loc[window].to_numpy(), 2),
        "machines": machines, "lights": staffed.astype(int).tolist(),
        "batches": batches, "alerts": alerts,
        "events": [{"minute": int((when - day) / pd.Timedelta(minutes=1)), "text": text} for when, text in events][::-1],
        "price_by_hour": nums(prices, 3), "band_by_hour": tariff.band_of_hour(), "currency": tariff.currency,
    }


# --------------------------------------------------------------------------- overview


def kpis(results, tariff: savings.Tariff) -> dict:
    bill = savings.bill(results.meter, tariff)
    idle = results.flows.loc[results.flows["destination"] == "Idle & overhead", "kWh"].sum()
    budget = results.budget
    reached = budget[budget["recommended"] >= 0.95]
    row = reached.iloc[0] if len(reached) else budget.iloc[-1]
    return {
        "energy_kwh": num(bill.energy_kwh, 0), "monthly_bill": num(bill.monthly_cost, 0), "peak_kw": num(bill.peak_kw, 1),
        "idle_kwh": num(idle, 0), "idle_share": num(idle / bill.energy_kwh, 3),
        "accuracy": num(budget["recommended"].iloc[0], 3), "accuracy_with_sensors": num(row["recommended"], 3),
        "sensors_needed": int(row["sensors"]), "coverage": num(results.coverage_by_machine.mean(), 3),
        "currency": tariff.currency,
    }


def flows(results, spec: PlantSpec) -> dict:
    meta = {m["id"]: m for m in machines_meta(results, spec)}
    machine_kwh = results.estimate.sum() / 60
    nodes, index = [], {}

    def node(name, color, kind):
        if name not in index:
            index[name] = len(nodes)
            nodes.append({"name": name, "color": color, "kind": kind})
        return index[name]

    meter = node("Main meter", "#64748b", "meter")
    links = []
    for machine_id, kwh in machine_kwh.items():
        m = meta[machine_id]
        links.append({"source": meter, "target": node(m["name"], m["color"], "machine"), "value": num(kwh, 1)})
    renamed = {"Idle & overhead": "Made nothing", "Building": "Building & offices"}
    for row in results.flows.itertuples():
        dest = renamed.get(row.destination, row.destination)
        kind = "waste" if dest == "Made nothing" else "building" if dest.startswith("Building") else "product"
        color = {"waste": "#ef4444", "building": OTHER_COLOR}.get(kind, "#93c5fd")
        links.append({"source": index[meta[row.machine]["name"]], "target": node(dest, color, kind), "value": num(row.kWh, 1)})
    links.append({"source": index[meta[OTHER]["name"]], "target": node("Building & offices", OTHER_COLOR, "building"),
                  "value": num(machine_kwh[OTHER], 1)})
    return {"nodes": nodes, "links": [link for link in links if link["value"] and link["value"] > 0]}


def morning(results, tariff: savings.Tariff, day: str | None) -> dict:
    days = results.meter.index.normalize().unique()
    weekdays = [d for d in days if d.dayofweek < 5]
    chosen = pd.Timestamp(day).normalize() if day else (weekdays[-1] if weekdays else days[-1])
    lines = daily.morning_check(results, chosen, tariff)
    return {"day": f"{chosen:%Y-%m-%d}", "weekday": f"{chosen:%A}", "days": days_available(results),
            "lines": [{"kind": l.kind, "text": l.text, "good": l.good} for l in lines]}


def machine_energy(results, spec: PlantSpec) -> list[dict]:
    kwh = results.estimate.sum() / 60
    sd = results.estimate_sd.sum() / 60 * results.daily_sd_scale
    total = kwh.sum()
    return [{"id": m["id"], "name": m["name"], "color": m["color"], "group": m["group"], "kwh": num(kwh[m["id"]], 0),
             "share": num(kwh[m["id"]] / total, 3), "plus_minus": num(Z90 * sd[m["id"]], 0)}
            for m in machines_meta(results, spec)]


# --------------------------------------------------------------------------- accuracy


def accuracy(results, spec: PlantSpec) -> dict:
    names = {m["id"]: m["name"] for m in machines_meta(results, spec)}
    batches = results.batches
    batch_inside = float(((batches["true kWh"] - batches["estimated kWh"]).abs() <= Z90 * batches["sd kWh"]).mean())
    report = results.per_machine
    return {
        "ladder": [{"model": label, "accuracy": num(a, 4)} for label, a in
                   zip(["Rule of thumb", "Learned from history", "Learned + matched to the meter"], results.ladder["accuracy"])],
        "coverage_curve": [{"claimed": num(r.claimed, 2), "actual": num(r.actual, 3)} for r in results.coverage.itertuples()],
        "coverage": {"minute": num(results.coverage_by_machine.mean(), 3), "daily": num(results.daily_coverage, 3),
                     "batch": num(batch_inside, 3)},
        "by_machine": [{"id": mid, "name": names[mid], "mae_kw": num(report.loc[mid, "MAE (kW)"], 2),
                        "true_kwh": num(report.loc[mid, "true kWh"], 0), "estimated_kwh": num(report.loc[mid, "estimated kWh"], 0),
                        "error_pct": num(report.loc[mid, "energy error %"], 1),
                        "inside_range": num(results.coverage_by_machine.get(mid, float("nan")), 3)} for mid in report.index],
        "budget": [{"sensors": int(b.sensors), "added": names.get(b.added, ""), "recommended": num(b.recommended, 4),
                    "random": num(b.random, 4)} for b in results.budget.itertuples()],
        "sensor_check": [{"machine": names[r["machine"]], "expected": num(r["expected reduction (kW)"], 2),
                          "actual": num(r["actual reduction (kW)"], 2)} for r in results.sensor_check.to_dict("records")],
        "products": [{"product": r["product"], "line": r["line"], "estimated": num(r["estimated kWh/unit"], 4),
                      "plus_minus": num(r["± kWh/unit (90%)"], 4), "true": num(r["true kWh/unit"], 4),
                      "error_pct": num(r["error %"], 1), "units": int(r["units"])} for r in results.products.to_dict("records")],
    }


# --------------------------------------------------------------------------- money


def prices(results, tariff: savings.Tariff) -> dict:
    bill = savings.bill(results.meter, tariff)
    by_band = savings.cost_by_band(results.meter, tariff)
    profile = results.meter.groupby(results.meter.index.hour).mean()
    return {
        "currency": tariff.currency, "demand_charge": tariff.demand_charge, "region": tariff.region,
        "demand_unit": tariff.demand_unit, "co2_kg_per_kwh": tariff.co2_kg_per_kwh,
        "bands": [{"name": name, "start": start, "end": end, "price": price,
                   "share": num(by_band.loc[name, "share of kWh"], 3), "cost": num(by_band.loc[name, "cost"], 0)}
                  for name, start, end, price in tariff.bands],
        "monthly_bill": num(bill.monthly_cost, 0), "peak_kw": num(bill.peak_kw, 1),
        "demand_cost": num(tariff.demand_charge * bill.peak_kw, 0), "hourly_kw": nums(profile.to_numpy(), 1),
        "price_by_hour": nums(tariff.price_by_hour(), 3),
    }


def shift(results, tariff: savings.Tariff, line: str, product: str, hours: float) -> dict:
    plan = savings.plan_shift(results, tariff, line, product, hours)
    before = plan.load_before.groupby(plan.load_before.index.hour).mean()
    after = plan.load_after.groupby(plan.load_after.index.hour).mean()
    return {**plan.summary(), "before": nums(before.to_numpy(), 1), "after": nums(after.to_numpy(), 1)}


def repairs(results, tariff: savings.Tariff, spec: PlantSpec) -> list[dict]:
    names = {m["id"]: m["name"] for m in machines_meta(results, spec)}
    summary = anomalies.summarize_alerts(results.anomalies)
    rows = []
    for alert in summary.to_dict("records"):
        fix = savings.plan_fix_waste(results, tariff, alert["machine"])
        rows.append({**fix, "name": names[alert["machine"]], "since": f"{alert['first night']:%Y-%m-%d}",
                     "nights": int(alert["nights flagged"]), "usual_kw": num(alert["usual kW"]),
                     "observed_kw": num(alert["observed kW"]),
                     "text": anomalies.describe(pd.Series(alert), names[alert["machine"]])})
    return rows


def overnight(results, machine: str) -> list[dict]:
    profile = results.overnight[results.overnight["machine"] == machine]
    return [{"night": f"{r['night']:%Y-%m-%d}", "estimated": num(r["estimated"]), "actual": num(r.get("actual", float("nan"))),
             "period": r["period"]} for r in profile.to_dict("records")]


def explain(results, machine: str, day: str | None) -> dict:
    start = pick_day(results, day)
    e = explain_machine(results, machine, start, start + pd.Timedelta(days=1))
    return {
        "name": e["name"], "kind": e["kind"], "final_kwh": num(e["final kWh"], 1), "plus_minus": num(e["90% band ± kWh"], 1),
        "learned_kwh": num(e["learned guess kWh"], 1), "adjustment_kwh": num(e["meter adjustment kWh"], 1),
        "share": num(e["share of site energy"], 3), "production": e.get("production", []),
        "drivers": [d["meaning"] for d in e["top drivers"][:4]],
    }
