"""The electricity bill: read it, take its real prices, check it, and split it by machine and product.

A monthly industrial time-of-use bill (from any utility: US, Canada, Japan, Nepal…) can't tell you which
machine used what: it only has monthly totals. But it has three things MeterZero
needs: the real price in each time band, the demand charge, and the month's kWh. So:

  * Gemini reads a photo of the bill into a fixed set of fields
  * the prices on it replace the example tariff everywhere in the app
  * its kWh are checked against the meter data MeterZero works from
  * the bill amount is split by machine and by product using MeterZero's estimates
"""
from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, Field

from .agent import gemini_model
from .savings import Tariff

BILL_PROMPT = """\
This is a photo of an electricity bill for a factory (it may be a time-of-day industrial bill).
Read the fields. Use 0 for anything that isn't on the bill. Dates as YYYY-MM-DD. Amounts as plain
numbers without thousands separators. If kWh is split into peak / normal / off-peak time bands,
fill those; if a rate per kWh is printed for a band, fill that rate. If a power factor or a low power
factor surcharge is printed, fill those too."""


class BillReading(BaseModel):
    utility: str = Field(default="", description="Who issued the bill")
    customer_category: str = Field(default="", description="Tariff category, e.g. 'Industrial (time of day)'")
    period_start: str = Field(description="First day of the billing period, YYYY-MM-DD")
    period_end: str = Field(description="Last day of the billing period, YYYY-MM-DD")
    kwh_peak: float = 0
    kwh_normal: float = 0
    kwh_offpeak: float = 0
    kwh_total: float = Field(description="Total kWh billed")
    max_demand_kva: float = Field(default=0, description="Maximum demand, in the unit given in demand_unit")
    demand_unit: str = Field(default="kVA", description="Unit the maximum demand is billed in: 'kW' or 'kVA'")
    rate_peak: float = Field(default=0, description="Price per kWh in the peak band")
    rate_normal: float = Field(default=0, description="Price per kWh in the normal band")
    rate_offpeak: float = Field(default=0, description="Price per kWh in the off-peak band")
    demand_rate: float = Field(default=0, description="Charge per kW or kVA of maximum demand")
    energy_charge: float = 0
    demand_charge: float = 0
    other_charges: float = 0
    power_factor: float = Field(default=0, description="Average power factor, if printed (e.g. 0.92)")
    power_factor_penalty: float = Field(default=0, description="Surcharge for low power factor, if any")
    total_amount: float = Field(description="Total amount to pay")
    currency: str = Field(default="Rs", description="Currency symbol or code on the bill")

    @property
    def days(self) -> int:
        return (pd.Timestamp(self.period_end) - pd.Timestamp(self.period_start)).days + 1


def read_bill(client, image: bytes, mime_type: str, model: str | None = None) -> BillReading:
    from google.genai import types

    response = client.models.generate_content(
        model=model or gemini_model(),
        contents=[types.Part.from_bytes(data=image, mime_type=mime_type), BILL_PROMPT],
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=BillReading,
                                           temperature=0),
    )
    return response.parsed if isinstance(response.parsed, BillReading) else BillReading.model_validate_json(response.text)


SYMBOLS = {"USD": "$", "US$": "$", "$": "$", "CAD": "C$", "C$": "C$", "JPY": "¥", "¥": "¥", "AUD": "A$", "A$": "A$",
           "INR": "₹", "₹": "₹", "NPR": "Rs ", "RS": "Rs ", "RS.": "Rs ", "NRS": "Rs "}


def currency_symbol(bill: BillReading) -> str:
    code = bill.currency.strip().upper()
    return SYMBOLS.get(code, bill.currency.strip() + " ")


def tariff_from_bill(bill: BillReading, template: Tariff | None = None) -> Tariff:
    """The bill's real prices, in the same time bands. Missing band rates fall back to the average rate."""
    template = template or Tariff()
    average = bill.energy_charge / bill.kwh_total if bill.kwh_total and bill.energy_charge else 0.0
    rates = {"peak": bill.rate_peak, "normal": bill.rate_normal, "off-peak": bill.rate_offpeak}
    bands = [(name, start, end, rates.get(name) or average or price) for name, start, end, price in template.bands]
    demand = bill.demand_rate or (bill.demand_charge / bill.max_demand_kva if bill.max_demand_kva else 0.0)
    # kVA vs kW: at the power factor most factories run (about 0.9) they're close enough for this split.
    return Tariff(bands=bands, demand_charge=demand or template.demand_charge, currency=currency_symbol(bill),
                  region=template.region, co2_kg_per_kwh=template.co2_kg_per_kwh, demand_unit=bill.demand_unit or template.demand_unit)


def check_against_meter(results, bill: BillReading, tariff: Tariff) -> dict:
    """Does the bill look like the meter data MeterZero works from? Compared per day, and by time band."""
    meter = results.meter
    days = (meter.index[-1] - meter.index[0]) / pd.Timedelta(days=1)
    meter_per_day = meter.sum() / 60 / days
    bill_per_day = bill.kwh_total / bill.days
    bands = pd.Series(tariff.band_of_hour())[meter.index.hour].to_numpy()
    meter_share = {name: float(meter[bands == name].sum() / meter.sum()) for name, *_ in tariff.bands}
    bill_bands = {"peak": bill.kwh_peak, "normal": bill.kwh_normal, "off-peak": bill.kwh_offpeak}
    bill_share = ({k: v / bill.kwh_total for k, v in bill_bands.items()} if bill.kwh_total and sum(bill_bands.values()) else {})
    return {
        "bill_kwh_per_day": bill_per_day,
        "meter_kwh_per_day": meter_per_day,
        "difference": meter_per_day / bill_per_day - 1 if bill_per_day else float("nan"),
        "meter_share": meter_share,
        "bill_share": bill_share,
    }


def split_by_machine(results, bill: BillReading, tariff: Tariff) -> pd.DataFrame:
    """Share out the bill: energy charges by each machine's priced energy, the demand charge by
    each machine's load at the plant's busiest 15 minutes, the rest in proportion to energy."""
    estimate = results.estimate
    prices = tariff.price_by_hour()[estimate.index.hour]
    energy_value = estimate.mul(prices, axis=0).sum() / 60
    energy_share = energy_value / energy_value.sum()

    quarter = estimate.resample("15min").mean()
    peak_moment = quarter.sum(axis=1).idxmax()
    demand_share = quarter.loc[peak_moment] / quarter.loc[peak_moment].sum()

    energy_charge = bill.energy_charge or max(bill.total_amount - bill.demand_charge - bill.other_charges, 0)
    split = pd.DataFrame({
        "energy": energy_share * energy_charge,
        "demand": demand_share * bill.demand_charge,
        "other": energy_share * bill.other_charges,
    })
    split["total"] = split.sum(axis=1)
    # Anything not covered above (rounding, taxes folded into the total) goes in proportion too.
    gap = bill.total_amount - split["total"].sum()
    split["total"] += energy_share * gap
    split["share"] = split["total"] / split["total"].sum()
    return split.sort_values("total", ascending=False)


def split_by_product(results, bill: BillReading) -> pd.DataFrame:
    """The bill by what the energy went into: each product, energy that made nothing, and the building."""
    flows = results.flows.groupby("destination")["kWh"].sum()
    building = results.estimate.drop(columns=results.machine_ids).sum().sum() / 60
    kwh = pd.concat([flows, pd.Series({"Lights, offices & other": building})])
    share = kwh / kwh.sum()
    return pd.DataFrame({"kWh share": share, "amount": share * bill.total_amount}).sort_values("amount", ascending=False)


def _overlaps_meter(results, bill: BillReading) -> bool:
    start, end = pd.Timestamp(bill.period_start), pd.Timestamp(bill.period_end) + pd.Timedelta(days=1)
    return start < results.meter.index[-1] and end > results.meter.index[0]


def check_bill(results, bill: BillReading, tariff: Tariff) -> list[dict]:
    """The things worth checking on any industrial bill, most money first.

    Each check is a plain sentence a plant manager can act on, with the amount at stake per month.
    """
    money = currency_symbol(bill)
    found: list[dict] = []

    # 1. Do the energy lines add up?
    bands = [(bill.kwh_peak, bill.rate_peak), (bill.kwh_normal, bill.rate_normal), (bill.kwh_offpeak, bill.rate_offpeak)]
    if all(rate for kwh, rate in bands if kwh) and bill.energy_charge:
        expected = sum(kwh * rate for kwh, rate in bands)
        extra = bill.energy_charge - expected
        if abs(extra) > max(0.005 * expected, 50):
            found.append({
                "kind": "arithmetic", "tone": "bad" if extra > 0 else "warn", "amount": round(extra),
                "title": f"Energy charges don't add up: {money}{abs(extra):,.0f} {'too much' if extra > 0 else 'too little'}",
                "detail": f"Units × rates come to {money}{expected:,.0f}, but the bill charges {money}{bill.energy_charge:,.0f}. "
                          "Ask the supplier to correct it before paying.",
            })
        else:
            found.append({"kind": "arithmetic", "tone": "ok", "amount": 0, "title": "Energy charges add up",
                          "detail": f"Units × rates match the {money}{bill.energy_charge:,.0f} charged."})

    # 2. Does the total add up?
    parts = bill.energy_charge + bill.demand_charge + bill.other_charges + bill.power_factor_penalty
    if parts and abs(bill.total_amount - parts) > max(0.005 * parts, 50):
        gap = bill.total_amount - parts
        found.append({"kind": "total", "tone": "warn", "amount": round(gap),
                      "title": f"The total is {money}{abs(gap):,.0f} {'more' if gap > 0 else 'less'} than its parts",
                      "detail": "Could be taxes or arrears not itemised on the bill. Worth asking what it is."})

    # 3. Power factor surcharge: usually the cheapest fix there is.
    if bill.power_factor_penalty > 0 or 0 < bill.power_factor < 0.9:
        pf = f"{bill.power_factor:.2f}" if bill.power_factor else "too low"
        found.append({
            "kind": "power_factor", "tone": "bad", "amount": round(bill.power_factor_penalty),
            "title": f"Low power factor ({pf}) cost {money}{bill.power_factor_penalty:,.0f}",
            "detail": "Motors and compressors draw reactive power the supplier charges for below 0.90. A capacitor bank "
                      f"at the main panel removes this surcharge: about {money}{12 * bill.power_factor_penalty:,.0f} a year "
                      "if it happens every month.",
        })

    # 4. Paying the peak price
    if bill.kwh_total and bill.kwh_peak and bill.rate_peak > bill.rate_normal:
        share = bill.kwh_peak / bill.kwh_total
        premium = bill.kwh_peak * (bill.rate_peak - bill.rate_normal)
        found.append({
            "kind": "peak", "tone": "warn" if share > 0.2 else "info", "amount": round(premium),
            "title": f"{share:.0%} of units bought at the peak price",
            "detail": f"Those {bill.kwh_peak:,.0f} kWh cost {money}{premium:,.0f} more than at the normal price. "
                      "Moving a line earlier (see What if) cuts this.",
        })

    # 5. The demand charge, and what caused the busiest 15 minutes
    if bill.demand_charge:
        estimate = results.estimate
        quarter = estimate.resample("15min").mean()
        moment = quarter.sum(axis=1).idxmax()
        top = quarter.loc[moment].sort_values(ascending=False)
        names = [str(m) for m in top.index[:3]]
        unit = "kVA" if bill.demand_unit.strip().lower() == "kva" else "kW"
        usual = quarter.sum(axis=1).max() / (0.9 if unit == "kVA" else 1)   # kW to kVA at a typical power factor
        rate = bill.demand_rate or bill.demand_charge / max(bill.max_demand_kva, 1)
        excess = bill.max_demand_kva - usual
        higher = excess > 0.05 * usual
        found.append({
            "kind": "demand", "tone": "warn" if higher else "info", "amount": round(excess * rate) if higher else round(bill.demand_charge),
            "title": (f"Demand {bill.max_demand_kva:,.0f} {unit}: {excess:,.0f} {unit} above usual, {money}{excess * rate:,.0f} extra"
                      if higher else f"Demand charge {money}{bill.demand_charge:,.0f} for {bill.max_demand_kva:,.0f} {unit}"),
            "detail": (f"The meter data usually peaks around {usual:,.0f} {unit}. " if higher else "")
                      + f"In the meter data the busiest 15 minutes were {moment:%a %d %b at %H:%M}, when {', '.join(names)} "
                      "ran together. Staggering their start-ups by a few minutes lowers this charge.",
            "machines": names,
        })

    # 6. Units against MeterZero's meter data, when the dates overlap
    if _overlaps_meter(results, bill):
        check = check_against_meter(results, bill, tariff)
        difference = check["difference"]
        close = abs(difference) < 0.05
        found.append({
            "kind": "meter", "tone": "ok" if close else "warn", "amount": 0,
            "title": "Units match the meter data" if close else f"Units differ from the meter data by {difference:+.0%}",
            "detail": f"The bill works out to {check['bill_kwh_per_day']:,.0f} kWh a day; the meter data MeterZero works "
                      f"from averages {check['meter_kwh_per_day']:,.0f} kWh a day."
                      + ("" if close else " Check the meter reading dates, or whether the supplier estimated the reading."),
        })

    order = {"bad": 0, "warn": 1, "info": 2, "ok": 3}
    return sorted(found, key=lambda f: (order[f["tone"]], -abs(f["amount"])))
