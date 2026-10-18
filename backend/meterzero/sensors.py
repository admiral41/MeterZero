"""Where should the next sensor go?

The model already says how unsure it is about every machine at every minute.
Because the estimates are tied together by the meter, pinning one machine with a
real sensor also tightens the others. We can compute that effect in closed form,
without any ground truth, and pick the sensor that shrinks expected error the most.

The choice is made on the validation period. The test period is then used to
check it: actually "install" each sensor and measure the real error drop.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .evaluate import disaggregation_accuracy
from .models import reconcile

ABS_ERROR_PER_SD = np.sqrt(2 / np.pi)


def expected_error(prior_sd: pd.DataFrame, machines: list[str], metered: tuple[str, ...] = ()) -> float:
    """Expected mean absolute error (kW, summed over machines) after reconciling with the meter."""
    var = prior_sd**2
    free = [c for c in prior_sd.columns if c not in metered]
    pool = var[free].sum(axis=1).to_numpy()[:, None]
    post_var = var[free] - var[free] ** 2 / pool
    scored = [c for c in free if c in machines]
    return float((np.sqrt(post_var[scored].clip(lower=0)) * ABS_ERROR_PER_SD).sum(axis=1).mean())


def rank_sensors(prior_sd: pd.DataFrame, machines: list[str], metered: tuple[str, ...] = ()) -> pd.DataFrame:
    before = expected_error(prior_sd, machines, metered)
    rows = [
        {"machine": m, "expected error after (kW)": expected_error(prior_sd, machines, metered + (m,))}
        for m in machines
        if m not in metered
    ]
    ranking = pd.DataFrame(rows)
    ranking["expected reduction (kW)"] = before - ranking["expected error after (kW)"]
    return ranking.sort_values("expected reduction (kW)", ascending=False).reset_index(drop=True)


def greedy_plan(prior_sd: pd.DataFrame, machines: list[str]) -> list[str]:
    """Order in which to add sensors, one at a time, each the best given the ones before."""
    metered: tuple[str, ...] = ()
    while len(metered) < len(machines):
        metered += (rank_sensors(prior_sd, machines, metered)["machine"].iloc[0],)
    return list(metered)


def score_with_sensors(meter, prior_mean, prior_sd, truth, machines, metered) -> tuple[float, float]:
    """Install real sensors on `metered`, reconcile, and return (accuracy, mean MAE over all machines)."""
    readings = {m: truth[m] for m in metered}
    estimate, _ = reconcile(meter, prior_mean, prior_sd, readings)
    accuracy = disaggregation_accuracy(truth[machines], estimate[machines])
    mae = (estimate[machines] - truth[machines]).abs().mean().sum()
    return accuracy, mae


def single_sensor_check(val_sd, meter, prior_mean, prior_sd, truth, machines) -> pd.DataFrame:
    """Predicted gain (from validation, no ground truth) vs actual gain on the test period."""
    _, mae_none = score_with_sensors(meter, prior_mean, prior_sd, truth, machines, ())
    ranking = rank_sensors(val_sd, machines)
    ranking["actual reduction (kW)"] = [
        mae_none - score_with_sensors(meter, prior_mean, prior_sd, truth, machines, (m,))[1]
        for m in ranking["machine"]
    ]
    return ranking


def budget_curve(plan, meter, prior_mean, prior_sd, truth, machines, n_random=30, seed=0) -> pd.DataFrame:
    """Accuracy with 0..N sensors placed by the recommender vs placed at random."""
    rng = np.random.default_rng(seed)
    random_orders = [list(rng.permutation(machines)) for _ in range(n_random)]

    rows = []
    for k in range(len(machines) + 1):
        planned, _ = score_with_sensors(meter, prior_mean, prior_sd, truth, machines, tuple(plan[:k]))
        random_scores = [
            score_with_sensors(meter, prior_mean, prior_sd, truth, machines, tuple(order[:k]))[0]
            for order in random_orders[: 1 if k in (0, len(machines)) else n_random]
        ]
        rows.append({
            "sensors": k,
            "added": plan[k - 1] if k else "",
            "recommended": planned,
            "random": float(np.mean(random_scores)),
        })
    return pd.DataFrame(rows)
