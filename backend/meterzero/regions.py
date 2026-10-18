"""Regional presets: how electricity is priced and billed for industrial customers in each region.

The rates are typical example values for a mid-size factory on a time-of-use contract, rounded,
so the app feels realistic out of the box. They are not any utility's published tariff; load a
real bill (Bills & paperwork) to replace them with the plant's actual prices.
"""
from __future__ import annotations

from dataclasses import dataclass

from .savings import Tariff


@dataclass(frozen=True)
class Region:
    id: str
    name: str
    currency: str            # symbol as shown in the app, with a trailing space where it reads better
    currency_code: str
    locale: str              # for number and date formatting in the browser
    bands: tuple             # (name, start hour, end hour, price per kWh)
    demand_charge: float     # per unit of the month's highest 15-minute demand
    demand_unit: str         # what the bill measures demand in: "kW" or "kVA"
    co2_kg_per_kwh: float    # average grid emissions
    grid_note: str

    def tariff(self) -> Tariff:
        return Tariff(bands=[tuple(b) for b in self.bands], demand_charge=self.demand_charge, currency=self.currency,
                      region=self.id, co2_kg_per_kwh=self.co2_kg_per_kwh, demand_unit=self.demand_unit)


REGIONS: dict[str, Region] = {r.id: r for r in [
    Region("us", "United States", "$", "USD", "en-US",
           (("off-peak", 23, 5, 0.08), ("normal", 5, 17, 0.12), ("peak", 17, 23, 0.20)),
           8.0, "kW", 0.37, "US average grid mix"),
    Region("ca", "Canada", "C$", "CAD", "en-CA",
           (("off-peak", 19, 7, 0.087), ("normal", 7, 11, 0.122), ("peak", 11, 19, 0.158)),
           12.0, "kW", 0.10, "Canadian average grid mix (mostly hydro and nuclear)"),
    Region("jp", "Japan", "¥", "JPY", "ja-JP",
           (("off-peak", 22, 8, 17.0), ("normal", 8, 16, 22.0), ("peak", 16, 22, 27.0)),
           1800.0, "kW", 0.45, "Japanese average grid mix"),
    Region("au", "Australia", "A$", "AUD", "en-AU",
           (("off-peak", 21, 7, 0.11), ("normal", 7, 15, 0.17), ("peak", 15, 21, 0.26)),
           14.0, "kVA", 0.62, "Australian average grid mix"),
    Region("in", "India", "₹", "INR", "en-IN",
           (("off-peak", 22, 6, 6.0), ("normal", 6, 18, 7.5), ("peak", 18, 22, 9.0)),
           450.0, "kVA", 0.71, "Indian average grid mix"),
    Region("np", "Nepal", "Rs ", "NPR", "en-NP",
           (("off-peak", 23, 5, 7.0), ("normal", 5, 17, 10.5), ("peak", 17, 23, 12.5)),
           280.0, "kVA", 0.02, "Nepal's grid (almost all hydro)"),
]}
DEFAULT_REGION = "us"


def region(region_id: str | None) -> Region:
    return REGIONS.get(region_id or DEFAULT_REGION, REGIONS[DEFAULT_REGION])


def describe() -> list[dict]:
    return [{"id": r.id, "name": r.name, "currency": r.currency, "currency_code": r.currency_code, "locale": r.locale,
             "bands": [list(b) for b in r.bands], "demand_charge": r.demand_charge, "demand_unit": r.demand_unit,
             "co2_kg_per_kwh": r.co2_kg_per_kwh, "grid_note": r.grid_note} for r in REGIONS.values()]
