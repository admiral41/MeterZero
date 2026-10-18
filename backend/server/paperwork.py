"""Paperwork: a logbook page checked against the system log, and electricity bills checked and split."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Query

from meterzero import bill as bill_module
from meterzero import vision

from . import views
from .common import results_or_409
from .store import store

router = APIRouter(prefix="/api")


@router.post("/plants/{plant_id}/logbook")
def logbook(plant_id: str, page: dict):
    results = results_or_409(plant_id)
    reading = vision.LogbookPage.model_validate(page)
    log, problems = vision.page_to_log(reading, vision.product_catalog(results.log))
    if log.empty:
        return {"problems": problems, "check": [], "batches": []}
    check = vision.compare_with_system_log(log, results.log)
    batches = vision.energy_from_page(results, log)
    return {
        "problems": problems,
        "check": check.to_dict("records"),
        "batches": [{"line": b["line"], "product": b["product"], "start": f"{b['start']:%H:%M}",
                     "end": f"{b['end']:%H:%M}", "units": int(b["units"]), "kwh": views.num(b["estimated kWh"], 1),
                     "plus_minus": views.num(1.645 * b["sd kWh"], 1), "true_kwh": views.num(b["true kWh"], 1)}
                    for b in batches.to_dict("records")],
    }


@router.post("/plants/{plant_id}/bill")
def bill(plant_id: str, reading: dict, apply: bool = Query(False)):
    results = results_or_409(plant_id)
    parsed = bill_module.BillReading.model_validate(reading)
    tariff = bill_module.tariff_from_bill(parsed, store.tariff(plant_id))
    if apply:
        store.set_tariff(plant_id, tariff)
    check = bill_module.check_against_meter(results, parsed, tariff)
    names = {m["id"]: m["name"] for m in views.machines_meta(results, store.spec(plant_id))}
    colors = {m["id"]: m["color"] for m in views.machines_meta(results, store.spec(plant_id))}
    machines = bill_module.split_by_machine(results, parsed, tariff)
    products = bill_module.split_by_product(results, parsed)
    return {
        "currency": tariff.currency, "days": parsed.days, "applied": apply,
        "findings": bill_findings(results, parsed, tariff, names),
        "check": {k: (views.num(v, 3) if not isinstance(v, dict) else {kk: views.num(vv, 3) for kk, vv in v.items()})
                  for k, v in check.items()},
        "by_machine": [{"id": mid, "name": names[mid], "color": colors[mid], "amount": views.num(row["total"], 0),
                        "share": views.num(row["share"], 3)} for mid, row in machines.iterrows()],
        "by_product": [{"name": {"Idle & overhead": "Made nothing", "Building": "Building & offices"}.get(name, name),
                        "amount": views.num(row["amount"], 0), "share": views.num(row["kWh share"], 3)}
                       for name, row in products.iterrows()],
    }


def bill_findings(results, parsed, tariff, names: dict[str, str]) -> list[dict]:
    findings = bill_module.check_bill(results, parsed, tariff)
    for finding in findings:
        if "machines" in finding:
            readable = [names.get(m, "lights and offices" if m == "other" else m).lower() for m in finding["machines"]]
            finding["detail"] = finding["detail"].replace(", ".join(finding["machines"]), ", ".join(readable))
            finding["machines"] = readable
    return findings


BILLS = Path(__file__).resolve().parents[1] / "samples" / "bills"


@router.get("/plants/{plant_id}/bills")
def bill_history(plant_id: str):
    """The sample bill history for the plant's region: each month pre-read (so it works without AI) and checked."""
    results = results_or_409(plant_id)
    region = store.tariff(plant_id).region
    names = {m["id"]: m["name"] for m in views.machines_meta(results, store.spec(plant_id))}
    months = []
    for path in sorted((BILLS / region).glob("*.json")):
        reading = json.loads(path.read_text(encoding="utf-8"))
        parsed = bill_module.BillReading.model_validate(reading)
        tariff = bill_module.tariff_from_bill(parsed, store.tariff(plant_id))
        findings = bill_findings(results, parsed, tariff, names)
        problems = [f for f in findings if f["tone"] == "bad"]
        months.append({
            "month": path.stem, "reading": reading, "currency": bill_module.currency_symbol(parsed),
            "image": f"/api/samples/bills/{region}/{path.stem}.jpg",
            "per_kwh": views.num(parsed.total_amount / parsed.kwh_total, 2) if parsed.kwh_total else 0,
            "peak_share": views.num(parsed.kwh_peak / parsed.kwh_total, 3) if parsed.kwh_total else 0,
            "problems": len(problems), "recoverable": round(sum(max(f["amount"], 0) for f in problems)),
        })
    return months
