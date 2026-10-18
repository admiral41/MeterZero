"""The morning check: what a plant manager wants to know about yesterday, in four lines.

No AI here: each line is a plain comparison against the other days of the week,
so it's always available and always the same for the same data.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .savings import Tariff

MIN_CHANGE_KWH = 40   # idle-energy differences smaller than this are just scheduling noise
MIN_DRIFT = 0.10      # flag products that use 10%+ more energy per item than usual


@dataclass
class CheckLine:
    kind: str    # "energy", "waste", "price", "product", "ok"
    text: str
    good: bool | None  # None = a neutral tip, neither good nor bad


def day_type(day: pd.Timestamp) -> str:
    return "weekday" if day.dayofweek < 5 else ("saturday" if day.dayofweek == 5 else "sunday")


def similar_days(results, day: pd.Timestamp) -> list[pd.Timestamp]:
    days = results.meter.index.normalize().unique()
    return [d for d in days if d != day and day_type(d) == day_type(day)]


def idle_kwh(results, day: pd.Timestamp) -> float:
    """Site energy during minutes when no production line was running."""
    end = day + pd.Timedelta(days=1) - pd.Timedelta(minutes=1)
    idle = results.test_features.loc[day:end, "lines_active"] == 0
    return float(results.meter.loc[day:end][idle.to_numpy()].sum() / 60)


def morning_check(results, day: pd.Timestamp, tariff: Tariff) -> list[CheckLine]:
    day = pd.Timestamp(day).normalize()
    end = day + pd.Timedelta(days=1) - pd.Timedelta(minutes=1)
    names = dict(zip(results.machines["id"], results.machines["name"]))
    prices = tariff.price_by_hour()
    lines: list[CheckLine] = []

    # 1. Energy and cost, and how much of it was used while nothing was being made.
    # Production changes day to day, so comparing whole days is noisy; the idle part isn't.
    meter = results.meter.loc[day:end]
    kwh = meter.sum() / 60
    cost = (meter.to_numpy() * prices[meter.index.hour]).sum() / 60
    idle = idle_kwh(results, day)
    usual = [idle_kwh(results, d) for d in similar_days(results, day)]
    typical = sorted(usual)[len(usual) // 2] if usual else idle
    extra = idle - typical
    text = (f"Used {kwh:,.0f} kWh ({tariff.currency}{cost:,.0f}). {idle:,.0f} kWh of it was used while no "
            "production line was running")
    if not usual:
        text += "."
    elif extra >= MIN_CHANGE_KWH:
        text += f", {extra:,.0f} kWh more than on a normal {day_type(day)}."
    else:
        text += ", which is normal."
    lines.append(CheckLine("energy", text, good=not (usual and extra >= MIN_CHANGE_KWH)))

    # 2. Anything running overnight that shouldn't be (the night ending this morning)
    alerts = results.anomalies[results.anomalies["night"] == day]
    if len(alerts):
        for alert in alerts.to_dict("records"):
            lines.append(CheckLine(
                "waste",
                f"Overnight, the {names[alert['machine']].lower()} averaged {alert['observed kW']:.1f} kW "
                f"(normally {alert['usual kW']:.1f}). About {alert['kWh/day if it persists']:.0f} kWh a day is being wasted.",
                good=False,
            ))
    else:
        lines.append(CheckLine("ok", "Nothing unusual running overnight.", good=True))

    # 3. Energy bought at the most expensive time, and what was running then
    expensive = max(tariff.bands, key=lambda band: band[3])
    hours = meter.index.hour
    bands = pd.Series(tariff.band_of_hour())[hours].to_numpy()
    share = meter[bands == expensive[0]].sum() / max(meter.sum(), 1e-9)
    log = results.log
    running = log[(log["end"] > day + pd.Timedelta(hours=expensive[1])) & (log["start"] < day + pd.Timedelta(days=1))
                  & (log["start"] >= day)]
    in_peak = running[running["end"].dt.hour >= expensive[1]]["line"].unique()
    if len(in_peak):
        lines.append(CheckLine(
            "price",
            f"{share:.0%} of the electricity was bought at the {expensive[0]} price "
            f"({expensive[1]:02d}:00 onwards). Line{'s' if len(in_peak) > 1 else ''} {', '.join(sorted(in_peak))} "
            "ran then; see the What if… page for cheaper times.",
            good=None,
        ))

    # 4. A product that took more energy per item than it usually does
    batches = results.batches
    week = batches.groupby("product").apply(lambda g: g["estimated kWh"].sum() / g["units"].sum(), include_groups=False)
    today_batches = batches[batches["start"].dt.normalize() == day]
    if len(today_batches):
        per_item = today_batches.groupby("product").apply(
            lambda g: g["estimated kWh"].sum() / g["units"].sum(), include_groups=False)
        drift = (per_item / week.reindex(per_item.index) - 1).sort_values(ascending=False)
        if len(drift) and drift.iloc[0] >= MIN_DRIFT:
            lines.append(CheckLine(
                "product",
                f"{drift.index[0]} took {drift.iloc[0]:.0%} more energy per item than its weekly average.",
                good=False,
            ))
        else:
            made = today_batches.groupby("product")["units"].sum().sort_values(ascending=False)
            lines.append(CheckLine(
                "ok", f"Products used normal energy per item. Most made: {made.index[0]} ({made.iloc[0]:,}).", good=True,
            ))
    return lines
