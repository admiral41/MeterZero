"""Six months of sample electricity bills for the demo plant, for every region in meterzero/regions.py.

    python scripts/make_bills.py

March matches the simulated meter data, priced at the region's example rates. The other months are
scaled from it, and three of them carry the problems real industrial bills have, so the bill check
has something to find:

  * December: a low power factor surcharge
  * January: a higher maximum demand (a cold month, everything started at once)
  * February: energy charges that don't add up to units × rates

Every bill is clearly marked as a sample: no utility name, logo or official layout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_samples import ROOT, font, photo_finish  # noqa: E402

from meterzero.regions import REGIONS, Region  # noqa: E402

OUT = ROOT / "samples" / "bills"
POWER_FACTOR = 0.9          # converts kW to kVA where demand is billed in kVA
PF_PENALTY_RATE = 0.005     # share of the energy charge per 0.01 of power factor below 0.90 (example only)

# month: (first day, last day, share of March's units, max demand vs March, power factor, energy overcharge share)
MONTHS = {
    "2025-10": ("2025-10-01", "2025-10-31", 1.06, 1.00, 0.93, 0),
    "2025-11": ("2025-11-01", "2025-11-30", 1.02, 0.98, 0.92, 0),
    "2025-12": ("2025-12-01", "2025-12-31", 1.04, 1.01, 0.82, 0),
    "2026-01": ("2026-01-01", "2026-01-31", 1.09, 1.12, 0.91, 0),
    "2026-02": ("2026-02-01", "2026-02-28", 0.97, 0.99, 0.92, 0.024),
}
BAND_LABELS = {"us": ("On-peak", "Mid-peak", "Off-peak"), "ca": ("On-peak", "Mid-peak", "Off-peak"),
               "au": ("Peak", "Shoulder", "Off-peak")}


def march(meter: pd.Series, region: Region) -> dict:
    """What the demo plant's month on the main meter adds up to, at the region's example rates."""
    bands = {name: (start, end, price) for name, start, end, price in region.bands}
    hour_band = {}
    for name, (start, end, _) in bands.items():
        for h in (range(start, end) if start < end else [*range(start, 24), *range(0, end)]):
            hour_band[h] = name
    labels = pd.Series([hour_band[h] for h in meter.index.hour], index=meter.index)
    kwh = {name: round(float(meter[labels == name].sum() / 60)) for name in bands}
    peak_kw = float(meter.resample("15min").mean().max())
    demand = round(peak_kw / POWER_FACTOR if region.demand_unit == "kVA" else peak_kw, 1)
    energy = round(sum(kwh[name] * bands[name][2] for name in bands))
    other = round(1500 * region.demand_charge / 280)   # a fixed service charge, in proportion to local prices
    return {
        "utility": "Sample Electricity Supplier (demo)", "customer_category": f"Industrial, time of use ({region.name}, sample)",
        "period_start": f"{meter.index[0]:%Y-%m-%d}", "period_end": f"{meter.index[-1]:%Y-%m-%d}",
        "kwh_peak": kwh["peak"], "kwh_normal": kwh["normal"], "kwh_offpeak": kwh["off-peak"], "kwh_total": sum(kwh.values()),
        "max_demand_kva": demand, "demand_unit": region.demand_unit,
        "rate_peak": bands["peak"][2], "rate_normal": bands["normal"][2], "rate_offpeak": bands["off-peak"][2],
        "demand_rate": region.demand_charge, "energy_charge": energy, "demand_charge": round(demand * region.demand_charge),
        "other_charges": other, "power_factor": 0.93, "power_factor_penalty": 0,
        "total_amount": energy + round(demand * region.demand_charge) + other, "currency": region.currency_code,
    }


def month_from(base: dict, first: str, last: str, units: float, demand: float, pf: float, overcharge: float) -> dict:
    days = (pd.Timestamp(last) - pd.Timestamp(first)).days + 1
    base_days = (pd.Timestamp(base["period_end"]) - pd.Timestamp(base["period_start"])).days + 1
    scale = units * days / base_days
    kwh = {band: round(base[f"kwh_{band}"] * scale) for band in ("peak", "normal", "offpeak")}
    correct = kwh["peak"] * base["rate_peak"] + kwh["normal"] * base["rate_normal"] + kwh["offpeak"] * base["rate_offpeak"]
    energy = round(correct * (1 + overcharge))
    peak = round(base["max_demand_kva"] * demand, 1)
    demand_charge = round(peak * base["demand_rate"])
    penalty = round(energy * PF_PENALTY_RATE * round((0.90 - pf) * 100)) if pf < 0.90 else 0
    return {
        **base, "period_start": first, "period_end": last,
        "kwh_peak": kwh["peak"], "kwh_normal": kwh["normal"], "kwh_offpeak": kwh["offpeak"], "kwh_total": sum(kwh.values()),
        "max_demand_kva": peak, "energy_charge": energy, "demand_charge": demand_charge,
        "power_factor": pf, "power_factor_penalty": penalty,
        "total_amount": energy + demand_charge + base["other_charges"] + penalty,
    }


def money(value: float) -> str:
    return f"{value:,.0f}"


def rate(value: float) -> str:
    return f"{value:.3f}" if value < 1 else f"{value:.2f}"


def draw_bill(numbers: dict, region: Region) -> Image.Image:
    """A plain, clearly marked sample bill. Deliberately no utility name, logo or official layout."""
    width, height = 1100, 1200
    page = Image.new("RGB", (width, height), (252, 252, 249))
    draw = ImageDraw.Draw(page)
    title, head = font(["arialbd.ttf"], 44), font(["arialbd.ttf"], 26)
    body, mono = font(["arial.ttf"], 25), font(["consola.ttf", "arial.ttf"], 26)
    ink, muted, rule = (30, 32, 36), (95, 98, 104), (200, 198, 190)
    code = region.currency_code

    draw.rectangle([0, 0, width, 120], fill=(12, 48, 74))
    draw.text((60, 34), "ELECTRICITY BILL", font=title, fill=(255, 255, 255))
    draw.text((640, 46), "SAMPLE FOR THE DEMO PLANT", font=head, fill=(122, 214, 150))

    y = 160
    for label, value in [("Supplier", numbers["utility"]), ("Customer", "Demo Plastics & Metal Works (sample)"),
                         ("Rate class", numbers["customer_category"]),
                         ("Billing period", f"{numbers['period_start']}  to  {numbers['period_end']}")]:
        draw.text((60, y), label, font=body, fill=muted)
        draw.text((330, y), value, font=body, fill=ink)
        y += 46

    def table(y, title_text, rows, columns):
        draw.text((60, y), title_text, font=head, fill=ink)
        y += 44
        draw.line([(60, y), (width - 60, y)], fill=rule, width=2)
        y += 12
        for x, text in columns:
            draw.text((x, y), text, font=body, fill=muted)
        y += 40
        for row in rows:
            for (x, _), text in zip(columns, row):
                draw.text((x, y), text, font=mono, fill=ink)
            y += 42
        draw.line([(60, y), (width - 60, y)], fill=rule, width=2)
        return y + 30

    peak, normal, off = BAND_LABELS.get(region.id, ("Peak", "Normal", "Off-peak"))
    hours = {name: f"{start:02d}:00-{end:02d}:00" for name, start, end, _ in region.bands}
    y = table(y + 20, "Energy by time of use", [
        [f"{peak} ({hours['peak']})", f"{numbers['kwh_peak']:,}", rate(numbers["rate_peak"]), money(numbers["kwh_peak"] * numbers["rate_peak"])],
        [f"{normal} ({hours['normal']})", f"{numbers['kwh_normal']:,}", rate(numbers["rate_normal"]), money(numbers["kwh_normal"] * numbers["rate_normal"])],
        [f"{off} ({hours['off-peak']})", f"{numbers['kwh_offpeak']:,}", rate(numbers["rate_offpeak"]), money(numbers["kwh_offpeak"] * numbers["rate_offpeak"])],
        ["Total", f"{numbers['kwh_total']:,}", "", money(numbers["energy_charge"])],
    ], [(60, "Period"), (500, "Units (kWh)"), (710, f"Rate ({code})"), (880, f"Amount ({code})")])

    charges = [
        ["Maximum demand", f"{numbers['max_demand_kva']:,} {region.demand_unit}", rate(numbers["demand_rate"]), money(numbers["demand_charge"])],
        ["Customer and meter charge", "", "", money(numbers["other_charges"])],
    ]
    if numbers.get("power_factor"):
        charges.append(["Power factor adjustment", f"PF {numbers['power_factor']:.2f}", "", money(numbers.get("power_factor_penalty", 0))])
    y = table(y, "Demand and other charges", charges, [(60, "Item"), (500, "Reading"), (710, f"Rate ({code})"), (880, f"Amount ({code})")])

    draw.rectangle([60, y, width - 60, y + 90], outline=(12, 48, 74), width=3)
    draw.text((90, y + 26), "TOTAL AMOUNT DUE", font=head, fill=ink)
    draw.text((620, y + 22), f"{code} {money(numbers['total_amount'])}", font=font(["arialbd.ttf"], 36), fill=ink)
    draw.text((60, height - 90), "Example rates for a simulated plant. This is not a real bill from any utility.",
              font=font(["ariali.ttf", "arial.ttf"], 22), fill=muted)

    # A big diagonal watermark so nobody mistakes it for a real bill
    label = "SAMPLE  ·  NOT A REAL BILL"
    mark_font = font(["arialbd.ttf"], 64)
    left, top, right, bottom = draw.textbbox((0, 0), label, font=mark_font)
    stamp = Image.new("RGBA", (right - left + 40, bottom - top + 40), (0, 0, 0, 0))
    ImageDraw.Draw(stamp).text((20 - left, 20 - top), label, font=mark_font, fill=(200, 40, 40, 70))
    stamp = stamp.rotate(28, expand=True)
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    layer.paste(stamp, ((width - stamp.width) // 2, (height - stamp.height) // 2 - 80), stamp)
    page = Image.alpha_composite(page.convert("RGBA"), layer).convert("RGB")
    return photo_finish(page, angle=1.6, seed=11)


def main() -> int:
    meter_path = ROOT / "data" / "meter.csv"
    if not meter_path.exists():
        print("Run `python -m meterzero all` first, so March matches the simulated plant.")
        return 1
    meter = pd.read_csv(meter_path, parse_dates=["timestamp"], index_col="timestamp")["power_kw"]
    for region in REGIONS.values():
        base = march(meter, region)
        bills = {month: month_from(base, *args) for month, args in MONTHS.items()} | {"2026-03": base}
        folder = OUT / region.id
        folder.mkdir(parents=True, exist_ok=True)
        for month, numbers in bills.items():
            draw_bill(numbers, region).save(folder / f"{month}.jpg", quality=84)
            (folder / f"{month}.json").write_text(json.dumps(numbers, indent=1), encoding="utf-8")
        print(f"{region.name}: {len(bills)} bills in {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
