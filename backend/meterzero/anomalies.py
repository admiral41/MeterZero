"""Flag machines whose overnight draw has jumped: leaks, stuck heaters, kit left on.

Energy auditors look for waste in the hours when nothing is scheduled to run,
because that's where it stands out from normal production swings. We do the same
on the per-machine estimates: for each machine, the average kW between 23:00 and
05:00 is compared with the nights of the validation week. A night far outside that
range, by enough kW to matter, gets flagged.

No sub-meter is needed. Ground truth is attached only so the dashboard can show
whether a flag was right.
"""
from __future__ import annotations

import pandas as pd

Z_THRESHOLD = 3.0
MIN_EXCESS_KW = 1.0
MIN_SPREAD_KW = 0.3  # a few validation nights can't pin the spread down tighter than this


def overnight_kw(power: pd.DataFrame) -> pd.DataFrame:
    """Average kW per machine between 23:00 and 05:00, labelled by the morning's date."""
    hours = power.index.hour
    night = power[(hours >= 23) | (hours < 5)]
    morning = (night.index + pd.Timedelta(hours=1)).normalize()  # 23:00 belongs to the next night
    grouped = night.groupby(morning)
    complete = grouped.size() >= 4 * 60  # skip nights cut off by the edge of the data
    return grouped.mean()[complete]


def find_anomalies(
    val_estimate: pd.DataFrame,
    test_estimate: pd.DataFrame,
    machines: list[str],
    test_truth: pd.DataFrame | None = None,
) -> pd.DataFrame:
    usual = overnight_kw(val_estimate[machines])
    centre, spread = usual.mean(), usual.std().fillna(0).clip(lower=MIN_SPREAD_KW)

    observed = overnight_kw(test_estimate[machines])
    truth = overnight_kw(test_truth[machines]) if test_truth is not None else None

    rows = []
    for night in observed.index:
        for machine in machines:
            excess = observed.at[night, machine] - centre[machine]
            z = excess / spread[machine]
            if z < Z_THRESHOLD or excess < MIN_EXCESS_KW:
                continue
            row = {
                "night": night,
                "machine": machine,
                "usual kW": centre[machine],
                "observed kW": observed.at[night, machine],
                "excess kW": excess,
                "z": z,
                "kWh/day if it persists": 24 * excess,
            }
            if truth is not None:
                row["true kW"] = truth.at[night, machine]
            rows.append(row)

    columns = ["night", "machine", "usual kW", "observed kW", "excess kW", "z", "kWh/day if it persists"]
    return pd.DataFrame(rows, columns=columns + (["true kW"] if truth is not None else []))


def overnight_profile(val_estimate, test_estimate, machines, test_truth=None) -> pd.DataFrame:
    """Long table of overnight kW per machine-night (validation + test), for plotting."""
    frames = {
        "estimated": pd.concat([overnight_kw(val_estimate[machines]), overnight_kw(test_estimate[machines])]),
    }
    if test_truth is not None:
        frames["actual"] = overnight_kw(test_truth[machines])
    long = pd.concat({name: f.stack() for name, f in frames.items()}, axis=1).reset_index()
    long.columns = ["night", "machine", *frames]
    long["period"] = long["night"].map(lambda d: "test" if d >= test_estimate.index[0].normalize() else "validation")
    return long


def summarize_alerts(alerts: pd.DataFrame) -> pd.DataFrame:
    """One line per machine: when it started, how bad, how many nights."""
    if alerts.empty:
        return alerts
    grouped = alerts.groupby("machine")
    return pd.DataFrame({
        "first night": grouped["night"].min(),
        "nights flagged": grouped.size(),
        "usual kW": grouped["usual kW"].first(),
        "observed kW": grouped["observed kW"].mean(),
        "kWh/day if it persists": grouped["kWh/day if it persists"].mean(),
    }).reset_index().sort_values("kWh/day if it persists", ascending=False)


def describe(alert: pd.Series, machine_name: str) -> str:
    return (
        f"Since {alert['first night']:%A %d %B}, the {machine_name.lower()} has been using "
        f"{alert['observed kW']:.1f} kW at night instead of its usual {alert['usual kW']:.1f} kW. "
        f"That's about {alert['kWh/day if it persists']:.0f} kWh wasted every day until it's fixed."
    )
