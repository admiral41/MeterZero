"""Energy per batch and per unit, built on top of the per-machine estimates.

A batch on line A is charged for line A's own machines over its run time, plus a
share of the shared utilities (compressor, chiller). Shared loads are split
evenly across whichever lines are running at that minute.

Batch uncertainty treats the per-minute errors as fully correlated, which is the
pessimistic bound (errors on the same machine do drift together). That bound is
then scaled on validation batches so the 90% band covers about 90%.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

SHARED = "shared"      # utilities that serve every line (compressor, chiller)
BUILDING = "building"  # lights, HVAC, offices: never charged to a product


def allocation_weights(features: pd.DataFrame, machines: pd.DataFrame, line: str) -> pd.DataFrame:
    """Share of each machine's power that belongs to `line`, minute by minute."""
    running = features[f"{line}_active"]
    shared_share = running / features["lines_active"].replace(0, np.nan)
    weights = {}
    for machine in machines.itertuples():
        if machine.line == line:
            weights[machine.id] = pd.Series(1.0, index=features.index)
        elif machine.line == SHARED:
            weights[machine.id] = shared_share.fillna(0)
        else:
            weights[machine.id] = pd.Series(0.0, index=features.index)
    return pd.DataFrame(weights)


def batch_energy(
    log: pd.DataFrame,
    features: pd.DataFrame,
    machines: pd.DataFrame,
    estimate: pd.DataFrame,
    sd: pd.DataFrame,
    truth: pd.DataFrame,
) -> pd.DataFrame:
    """kWh per batch: estimated, its standard deviation, and the true value."""
    index = features.index
    in_window = log[(log["start"] >= index[0]) & (log["end"] <= index[-1])]
    weights = {line: allocation_weights(features, machines, line) for line in in_window["line"].unique()}
    columns = list(machines["id"])

    rows = []
    for batch in in_window.itertuples():
        minutes = slice(batch.start, batch.end - pd.Timedelta(minutes=1))
        w = weights[batch.line].loc[minutes, columns]
        rows.append({
            "batch_id": batch.batch_id,
            "line": batch.line,
            "product": batch.product,
            "start": batch.start,
            "end": batch.end,
            "units": batch.units,
            "estimated kWh": (w * estimate.loc[minutes, columns]).to_numpy().sum() / 60,
            "sd kWh": (w * sd.loc[minutes, columns]).to_numpy().sum() / 60,
            "true kWh": (w * truth.loc[minutes, columns]).to_numpy().sum() / 60,
        })
    return pd.DataFrame(rows)


def conformal_scale(z: pd.Series, level: float = 0.9) -> float:
    """Scale for unit-normal bands from validation z-scores, using the split-conformal
    quantile so it still covers `level` when there are only a few dozen samples."""
    z = np.sort(z.dropna().to_numpy())
    rank = min(int(np.ceil((len(z) + 1) * level)), len(z))
    return float(z[rank - 1] / norm.ppf(0.5 + level / 2))


def calibrate_batch_sd(batches: pd.DataFrame, level: float = 0.9) -> float:
    z = (batches["true kWh"] - batches["estimated kWh"]).abs() / batches["sd kWh"]
    return conformal_scale(z, level)


def calibrate_daily_sd(truth: pd.DataFrame, estimate: pd.DataFrame, sd: pd.DataFrame, level: float = 0.9) -> float:
    """Same idea for machine-days: scale the fully-correlated daily band so it covers `level`."""
    days = truth.index.normalize()
    error = (estimate.groupby(days).sum() - truth.groupby(days).sum()).abs()
    band = sd.groupby(days).sum()
    return conformal_scale((error / band.clip(lower=1e-9)).stack(), level)


def energy_flows(log, features, machines, estimate) -> pd.DataFrame:
    """kWh from each machine into each product (by batch allocation), plus what's left over.

    The leftover is "idle & overhead": warm-ups, holding temperature between batches,
    nights and weekends. It's often the most actionable slice.
    """
    columns = list(machines["id"])
    index = features.index
    in_window = log[(log["start"] >= index[0]) & (log["end"] <= index[-1])]
    weights = {line: allocation_weights(features, machines, line) for line in in_window["line"].unique()}

    flows: dict[tuple[str, str], float] = {}
    for batch in in_window.itertuples():
        minutes = slice(batch.start, batch.end - pd.Timedelta(minutes=1))
        kwh = (weights[batch.line].loc[minutes, columns] * estimate.loc[minutes, columns]).sum() / 60
        for machine, value in kwh.items():
            if value > 0:
                flows[machine, batch.product] = flows.get((machine, batch.product), 0.0) + float(value)

    rows = [{"machine": m, "destination": p, "kWh": v} for (m, p), v in flows.items()]
    allocated = pd.DataFrame(rows).groupby("machine")["kWh"].sum() if rows else pd.Series(dtype=float)
    building = set(machines.loc[machines["line"] == BUILDING, "id"])
    for machine in columns:
        leftover = estimate[machine].sum() / 60 - allocated.get(machine, 0.0)
        if leftover > 0:
            destination = "Building" if machine in building else "Idle & overhead"
            rows.append({"machine": machine, "destination": destination, "kWh": float(leftover)})
    return pd.DataFrame(rows)


def product_summary(batches: pd.DataFrame) -> pd.DataFrame:
    """kWh per unit for each product, with a 90% band."""
    grouped = batches.groupby(["line", "product"])
    units = grouped["units"].sum()
    summary = pd.DataFrame({
        "batches": grouped.size(),
        "units": units,
        "estimated kWh/unit": grouped["estimated kWh"].sum() / units,
        # Batches are summed, so their (pessimistically correlated) errors add up too.
        "± kWh/unit (90%)": norm.ppf(0.95) * grouped["sd kWh"].sum() / units,
        "true kWh/unit": grouped["true kWh"].sum() / units,
    })
    summary["error %"] = 100 * (summary["estimated kWh/unit"] / summary["true kWh/unit"] - 1)
    return summary.reset_index()
