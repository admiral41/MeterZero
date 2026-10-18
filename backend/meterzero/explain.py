"""Plain-language answers to "why did it say that?".

Every final estimate splits exactly into two parts:

    final = learned guess (from the production log and meter shape)
          + its share of the meter gap (decided by how unsure that guess was)

On top of that, permutation importance tells us which inputs each machine's model
leans on most, translated into words a plant engineer would use.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

FEATURE_WORDS = [
    (r"^(\w)_active$", r"whether line \1 is running"),
    (r"^(\w)_since_start$", r"minutes since line \1's batch started"),
    (r"^(\w)_until_end$", r"minutes until line \1's batch ends"),
    (r"^(\w)_(.+)$", r"line \1 making \2"),
    (r"^lines_active$", "how many lines are running"),
    (r"^hour$", "time of day"),
    (r"^weekday$", "day of the week"),
    (r"^meter_kw$", "the meter reading itself"),
    (r"^meter_step$", "sudden steps in the meter"),
    (r"^meter_mean_(\d+)$", r"the meter's \1-minute average"),
    (r"^meter_std_(\d+)$", r"how much the meter swings over \1 minutes"),
    (r"^meter_above_daily_min$", "how far the meter is above its overnight low"),
]


def describe_feature(name: str) -> str:
    for pattern, words in FEATURE_WORDS:
        if re.match(pattern, name):
            return re.sub(pattern, words, name)
    return name


def top_drivers(priors, X: pd.DataFrame, targets: pd.DataFrame, n: int = 4, sample: int = 2000, seed: int = 0) -> dict[str, list[dict]]:
    """For each machine, the inputs whose shuffling hurts its model the most."""
    rows = X.sample(min(sample, len(X)), random_state=seed).index
    drivers = {}
    for column, model in priors.mean_models_.items():
        result = permutation_importance(
            model, X.loc[rows], targets.loc[rows, column],
            n_repeats=3, random_state=seed, scoring="neg_mean_absolute_error",
        )
        order = np.argsort(result.importances_mean)[::-1][:n]
        drivers[column] = [
            {"feature": X.columns[i], "meaning": describe_feature(X.columns[i]),
             "kW of error if removed": float(result.importances_mean[i])}
            for i in order
            if result.importances_mean[i] > 0
        ]
    return drivers


def decompose(prior: pd.DataFrame, prior_sd: pd.DataFrame, estimate: pd.DataFrame, machine: str) -> dict:
    """Split a machine's final energy over a window into learned guess + meter adjustment."""
    var = prior_sd**2
    weight = (var[machine] / var.sum(axis=1)).mean()
    learned = prior[machine].sum() / 60
    final = estimate[machine].sum() / 60
    return {
        "learned guess kWh": float(learned),
        "meter adjustment kWh": float(final - learned),
        "final kWh": float(final),
        "share of the meter gap it absorbs": float(weight),
    }


def production_context(log: pd.DataFrame, line: str, start, end) -> list[str]:
    batches = log[(log["line"] == line) & (log["end"] > start) & (log["start"] < end)]
    return [f"{b.product} {b.start:%H:%M}-{b.end:%H:%M} ({b.units} units)" for b in batches.itertuples()]


def explain_machine(results, machine: str, start, end) -> dict:
    window = slice(start, end - pd.Timedelta(minutes=1))
    info = results.machines.set_index("id").loc[machine] if machine in results.machine_ids else None
    parts = decompose(results.prior.loc[window], results.prior_sd.loc[window], results.estimate.loc[window], machine)
    total = results.estimate.loc[window].sum().sum() / 60
    explanation = {
        "machine": machine,
        "name": info["name"] if info is not None else "Other loads (unmetered)",
        "line": info["line"] if info is not None else "-",
        "kind": info["kind"] if info is not None else "lights, HVAC, offices, chargers",
        "share of site energy": parts["final kWh"] / total if total else 0.0,
        **parts,
        "90% band ± kWh": float(1.645 * results.daily_sd_scale * results.estimate_sd.loc[window, machine].sum() / 60),
        "top drivers": results.drivers.get(machine, []),
    }
    if info is not None and info["line"] != "shared":
        explanation["production"] = production_context(results.log, info["line"], start, end)
    return explanation
