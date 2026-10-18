"""What-if planner: put a price on schedule changes and repairs before anyone touches the plant.

Everything is computed from MeterZero's per-machine estimates for the test week:

* a time-of-use tariff (with a demand charge on the 15-minute peak) prices the site load
* moving a batch moves its *extra* load (machine power above idle) to the new slot
* fixing a waste alert removes the excess draw it measured

Savings come with a band, because the load being moved is itself an estimate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .batches import BUILDING, SHARED, allocation_weights

Z90 = 1.645
DAYS_PER_MONTH = 30.0


@dataclass
class Tariff:
    """Example time-of-use tariff. Set the bands and prices to the plant's real contract."""

    bands: list[tuple[str, int, int, float]] = field(default_factory=lambda: [
        # name, start hour, end hour (exclusive), price per kWh
        ("off-peak", 23, 5, 0.08),
        ("normal", 5, 17, 0.12),
        ("peak", 17, 23, 0.20),
    ])
    demand_charge: float = 8.0  # per kW of the month's highest 15-minute average
    currency: str = "$"
    region: str = "us"          # see regions.py: sets these defaults for a country
    co2_kg_per_kwh: float = 0.37
    demand_unit: str = "kW"     # what the utility bills demand in: kW, or kVA in many countries

    def price_by_hour(self) -> np.ndarray:
        prices = np.zeros(24)
        for _, start, end, price in self.bands:
            hours = range(start, end) if start < end else [*range(start, 24), *range(0, end)]
            prices[list(hours)] = price
        return prices

    def band_of_hour(self) -> list[str]:
        names = [""] * 24
        for name, start, end, _ in self.bands:
            hours = range(start, end) if start < end else [*range(start, 24), *range(0, end)]
            for h in hours:
                names[h] = name
        return names


@dataclass
class Bill:
    energy_kwh: float
    energy_cost: float
    peak_kw: float
    days: float
    tariff: Tariff

    @property
    def monthly_cost(self) -> float:
        scale = DAYS_PER_MONTH / self.days
        return self.energy_cost * scale + self.tariff.demand_charge * self.peak_kw


def bill(load_kw: pd.Series, tariff: Tariff) -> Bill:
    prices = tariff.price_by_hour()[load_kw.index.hour]
    peak = load_kw.resample("15min").mean().max()
    days = (load_kw.index[-1] - load_kw.index[0]) / pd.Timedelta(days=1) + 1 / 1440
    return Bill(
        energy_kwh=float(load_kw.sum() / 60),
        energy_cost=float((load_kw.to_numpy() * prices).sum() / 60),
        peak_kw=float(peak),
        days=float(days),
        tariff=tariff,
    )


def cost_by_band(load_kw: pd.Series, tariff: Tariff) -> pd.DataFrame:
    bands = np.array(tariff.band_of_hour())[load_kw.index.hour]
    prices = tariff.price_by_hour()[load_kw.index.hour]
    frame = pd.DataFrame({"band": bands, "kWh": load_kw.to_numpy() / 60, "cost": load_kw.to_numpy() * prices / 60})
    summary = frame.groupby("band")[["kWh", "cost"]].sum()
    summary["share of kWh"] = summary["kWh"] / summary["kWh"].sum()
    return summary.reindex([b[0] for b in tariff.bands]).fillna(0)


# --------------------------------------------------------------------------- schedule shifts


def working_hours(log: pd.DataFrame, index: pd.DatetimeIndex) -> np.ndarray:
    """Minutes between each day's first batch start and last batch end: when people are on site."""
    days = log.assign(day=log["start"].dt.normalize()).groupby("day").agg(first=("start", "min"), last=("end", "max"))
    first = days["first"].reindex(index.normalize())
    last = days["last"].reindex(index.normalize())
    return ((index >= first.to_numpy()) & (index < last.to_numpy())).astype(bool)


def idle_levels(results) -> pd.Series:
    """Typical kW of each machine during working hours while its line is idle."""
    features, estimate = results.test_features, results.estimate
    on_site = working_hours(results.log, estimate.index)
    levels = {}
    for machine in results.machines.itertuples():
        if machine.line in (SHARED, BUILDING):
            idle = features["lines_active"] == 0
        else:
            idle = features[f"{machine.line}_active"] == 0
        sample = estimate.loc[idle.to_numpy() & on_site, machine.id]
        levels[machine.id] = float(sample.median()) if len(sample) else 0.0
    return pd.Series(levels)


def batch_extra_load(results, batch, idle: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Extra kW (and its sd) a batch adds above idle, minute by minute, across its line's machines."""
    machines = list(results.machines["id"])
    minutes = slice(batch.start, batch.end - pd.Timedelta(minutes=1))
    weights = allocation_weights(results.test_features.loc[minutes], results.machines, batch.line)[machines]
    extra = (weights * (results.estimate.loc[minutes, machines] - idle[machines])).clip(lower=0).sum(axis=1)
    sd = (weights * results.estimate_sd.loc[minutes, machines]).sum(axis=1)
    return extra, sd


@dataclass
class ShiftPlan:
    description: str
    batches_moved: int
    kwh_moved: float
    kwh_moved_sd: float
    before: Bill
    after: Bill
    conflicts: int          # moved batches that would overlap another batch on the same line
    outside_hours: int      # moved batches that start outside today's working hours
    dropped: int            # moved past the end of the data window
    load_before: pd.Series
    load_after: pd.Series

    @property
    def monthly_saving(self) -> float:
        return self.before.monthly_cost - self.after.monthly_cost

    @property
    def monthly_saving_sd(self) -> float:
        """Band on the saving: energy price gap times the uncertainty of the moved kWh."""
        if self.kwh_moved <= 0:
            return 0.0
        energy_part = (self.before.energy_cost - self.after.energy_cost) * DAYS_PER_MONTH / self.before.days
        return abs(energy_part) * self.kwh_moved_sd / self.kwh_moved

    def summary(self) -> dict:
        return {
            "change": self.description,
            "batches_moved": int(self.batches_moved),
            "kwh_moved_per_week": round(float(self.kwh_moved)),
            "monthly_saving": round(float(self.monthly_saving)),
            "monthly_saving_plus_minus_90pct": round(float(Z90 * self.monthly_saving_sd)),
            "monthly_bill_before": round(float(self.before.monthly_cost)),
            "monthly_bill_after": round(float(self.after.monthly_cost)),
            "peak_kw_before": round(float(self.before.peak_kw), 1),
            "peak_kw_after": round(float(self.after.peak_kw), 1),
            "batches_that_clash_with_other_batches": int(self.conflicts),
            "batches_needing_staff_outside_current_hours": int(self.outside_hours),
            "batches_dropped_past_end_of_data": int(self.dropped),
            "currency": self.before.tariff.currency,
        }


def plan_shift(results, tariff: Tariff, line: str, product: str = "", hours: float = 0.0) -> ShiftPlan:
    """Move every batch of `line` (optionally only `product`) by `hours` and re-price the week."""
    log = results.log
    index = results.meter.index
    window = log[(log["start"] >= index[0]) & (log["end"] <= index[-1])]
    chosen = window[(window["line"] == line) & ((window["product"] == product) if product else True)]
    if chosen.empty:
        known = sorted(window.loc[window["line"] == line, "product"].unique())
        raise ValueError(f"No batches for line {line!r}{' / ' + product if product else ''}. Products on that line: {known}")

    idle = idle_levels(results)
    on_site = pd.Series(working_hours(log, index), index=index)
    offset = pd.Timedelta(minutes=round(hours * 60))
    load_before = results.meter.copy()
    load_after = load_before.copy()
    kwh = var_sd = 0.0
    conflicts = outside = dropped = 0
    others = window[(window["line"] == line) & ~window.index.isin(chosen.index)]

    for batch in chosen.itertuples():
        extra, sd = batch_extra_load(results, batch, idle)
        new_start, new_end = batch.start + offset, batch.end + offset
        load_after.loc[extra.index] -= extra.to_numpy()
        if new_end > index[-1] or new_start < index[0]:
            dropped += 1
            continue
        target = pd.date_range(new_start, periods=len(extra), freq="1min")
        load_after.loc[target] += extra.to_numpy()
        kwh += extra.sum() / 60
        var_sd += sd.sum() / 60
        if ((others["start"] < new_end) & (others["end"] > new_start)).any():
            conflicts += 1
        if not on_site.get(new_start, False):
            outside += 1

    product_text = f"{product} batches" if product else f"line {line}"
    direction = "later" if hours >= 0 else "earlier"
    amount = f"{abs(hours):g} hour" + ("" if abs(hours) == 1 else "s")
    return ShiftPlan(
        description=f"Start {product_text} {amount} {direction}",
        batches_moved=len(chosen) - dropped,
        kwh_moved=kwh,
        kwh_moved_sd=var_sd,
        before=bill(load_before, tariff),
        after=bill(load_after.clip(lower=0), tariff),
        conflicts=conflicts,
        outside_hours=outside,
        dropped=dropped,
        load_before=load_before,
        load_after=load_after.clip(lower=0),
    )


def best_shift(results, tariff: Tariff, hours=(-3, -2, -1, 1, 2, 3)) -> ShiftPlan | None:
    """The most valuable whole-line schedule change that doesn't clash with other batches."""
    best = None
    for line in sorted(results.log["line"].unique()):
        for h in hours:
            plan = plan_shift(results, tariff, line, hours=h)
            if plan.conflicts == 0 and plan.dropped == 0 and plan.monthly_saving > 0:
                if best is None or plan.monthly_saving > best.monthly_saving:
                    best = plan
                    best.args = {"line": line, "hours": h}   # so the app can redraw this plan
    return best


def top_actions(results, tariff: Tariff) -> list[dict]:
    """What to do first, in plain terms, ranked by money. No AI involved: straight from the numbers."""
    actions = []
    for machine in results.anomalies["machine"].unique():
        fix = plan_fix_waste(results, tariff, machine)
        name = results.machines.set_index("id").loc[machine, "name"]
        actions.append({
            "kind": "repair", "machine": machine,
            "title": f"Fix the {name.lower()}",
            "why": f"It has been using {fix['excess_kw']:.1f} kW more than normal at night, when nothing is scheduled.",
            "monthly_saving": fix["monthly_saving"], "plus_minus": fix["monthly_saving_plus_minus_90pct"],
        })
    shift = best_shift(results, tariff)
    if shift:
        summary = shift.summary()
        catch = (f" {summary['batches_needing_staff_outside_current_hours']} batches would start outside today's hours."
                 if summary["batches_needing_staff_outside_current_hours"] else "")
        actions.append({
            "kind": "schedule", "machine": "",
            "title": shift.description,
            "why": f"Moves {summary['kwh_moved_per_week']:,} kWh a week into cheaper hours, with no clashes.{catch}",
            "monthly_saving": summary["monthly_saving"], "plus_minus": summary["monthly_saving_plus_minus_90pct"],
            "shift": getattr(shift, "args", None),
        })
    if len(results.sensor_check):
        machine = results.sensor_check["machine"].iloc[0]
        name = results.machines.set_index("id").loc[machine, "name"]
        budget = results.budget
        before, after = budget["recommended"].iloc[0], budget["recommended"].iloc[1]
        actions.append({
            "kind": "sensor", "machine": machine,
            "title": f"Put a meter on the {name.lower()}",
            "why": f"It's the machine MeterZero is least sure about. One meter there lifts accuracy from {before:.0%} to {after:.0%}.",
            "monthly_saving": 0, "plus_minus": 0,
        })
    return sorted(actions, key=lambda a: -a["monthly_saving"])


# --------------------------------------------------------------------------- waste fixes


def plan_fix_waste(results, tariff: Tariff, machine: str) -> dict:
    """What fixing a flagged machine is worth: its excess draw, all day, at the average price."""
    alerts = results.anomalies[results.anomalies["machine"] == machine]
    if alerts.empty:
        flagged = sorted(results.anomalies["machine"].unique())
        raise ValueError(f"No waste alert for {machine!r}. Machines with alerts: {flagged or 'none'}")
    excess_kw = float(alerts["excess kW"].mean())
    spread = float(alerts["excess kW"].std()) if len(alerts) > 1 else 0.3 * excess_kw
    average_price = float(tariff.price_by_hour().mean())
    monthly_kwh = excess_kw * 24 * DAYS_PER_MONTH
    return {
        "machine": machine,
        "excess_kw": round(excess_kw, 2),
        "monthly_kwh_wasted": round(monthly_kwh),
        "monthly_saving": round(monthly_kwh * average_price),
        "monthly_saving_plus_minus_90pct": round(Z90 * spread * 24 * DAYS_PER_MONTH * average_price),
        "yearly_saving": round(monthly_kwh * average_price * 12),
        "currency": tariff.currency,
        "assumes": "the excess runs around the clock until repaired, priced at the average tariff",
    }
