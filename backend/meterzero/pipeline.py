"""Run the whole thing: load, train, reconcile, score, and save results for the dashboard."""
from __future__ import annotations

import pickle
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd

from . import anomalies, sensors
from . import batches as batch_energy
from .explain import top_drivers
from .data import load_factory, split_by_day
from .evaluate import coverage_curve, daily_coverage, interval_coverage, machine_report, summarize
from .features import build_features, production_state
from .models import MachinePriors, ScheduleBaseline, fit_interval_scale, reconcile


@dataclass
class Results:
    machines: pd.DataFrame
    log: pd.DataFrame
    test_features: pd.DataFrame

    # Test period, minute by minute
    meter: pd.Series
    truth: pd.DataFrame        # machines + "other"
    baseline: pd.DataFrame
    prior: pd.DataFrame        # learned guess before reconciliation
    prior_sd: pd.DataFrame
    estimate: pd.DataFrame     # final, meter-reconciled
    estimate_sd: pd.DataFrame  # calibrated

    # Scores
    ladder: pd.DataFrame
    per_machine: pd.DataFrame
    coverage: pd.DataFrame
    coverage_by_machine: pd.Series

    # Products
    batches: pd.DataFrame
    products: pd.DataFrame

    # Sensors
    sensor_check: pd.DataFrame
    budget: pd.DataFrame

    # Alerts and explanations
    anomalies: pd.DataFrame
    overnight: pd.DataFrame
    drivers: dict
    daily_sd_scale: float      # turns summed minute bands into honest machine-day bands
    daily_coverage: float

    # Kept so new production logs (e.g. read from a photo) can be pushed through the model
    flows: pd.DataFrame
    priors: MachinePriors
    feature_columns: list[str]
    interval_scale: pd.Series
    batch_sd_scale: float

    @property
    def machine_ids(self) -> list[str]:
        return list(self.machines["id"])


def run(data_dir: str | Path = "data", val_days: int = 4, test_days: int = 7, verbose: bool = True,
        progress: Callable[[str], None] | None = None, fast: bool = False) -> Results:
    """`progress` gets a short message at each stage, for showing training progress in a UI.
    `fast` trains lighter models (for trying out a plant design in under a minute)."""
    say = progress or (print if verbose else (lambda *_: None))
    started = time.perf_counter()

    data = load_factory(data_dir)
    machines = data.machine_ids
    split = split_by_day(data.meter.index, val_days, test_days)
    say(f"Loaded {len(data.meter):,} minutes: {len(split.train):,} train / "
        f"{len(split.val):,} val / {len(split.test):,} test")

    X = build_features(data.meter, data.log)
    state = production_state(data.log, data.meter.index)
    targets = data.targets()
    train, val, test = split.train, split.val, split.test

    say("Training per-machine models...")
    baseline = ScheduleBaseline().fit(state[train], targets.loc[train, machines])
    priors = MachinePriors(max_iter=120 if fast else 250).fit(X.loc[train], targets.loc[train])

    val_mean, val_sd = priors.predict(X.loc[val])
    test_mean, test_sd = priors.predict(X.loc[test])

    val_post, val_post_sd = reconcile(data.meter[val], val_mean, val_sd)
    test_post, test_post_sd = reconcile(data.meter[test], test_mean, test_sd)

    # Widen or tighten the bands so they're honest on validation, then apply to test.
    scale = fit_interval_scale(targets.loc[val], val_post, val_post_sd)
    test_post_sd = test_post_sd * scale
    val_post_sd = val_post_sd * scale

    truth = targets.loc[test]
    baseline_test = baseline.predict(state[test])
    ladder = pd.DataFrame([
        summarize("1. Schedule baseline", truth[machines], baseline_test),
        summarize("2. Learned model (log + meter)", truth[machines], test_mean),
        summarize("3. + Meter reconciliation", truth[machines], test_post),
    ])

    say("Batch energy and sensor placement...")
    val_batches = batch_energy.batch_energy(
        data.log, X.loc[val], data.machines, val_post, val_post_sd, targets.loc[val]
    )
    test_batches = batch_energy.batch_energy(
        data.log, X.loc[test], data.machines, test_post, test_post_sd, truth
    )
    batch_scale = batch_energy.calibrate_batch_sd(val_batches)
    test_batches["sd kWh"] *= batch_scale

    daily_scale = batch_energy.calibrate_daily_sd(targets.loc[val], val_post, val_post_sd)
    plan = sensors.greedy_plan(val_sd, machines)
    results = Results(
        machines=data.machines,
        log=data.log,
        test_features=X.loc[test],
        meter=data.meter[test],
        truth=truth,
        baseline=baseline_test,
        prior=test_mean,
        prior_sd=test_sd,
        estimate=test_post,
        estimate_sd=test_post_sd,
        ladder=ladder,
        per_machine=machine_report(truth[machines], test_post),
        coverage=coverage_curve(truth[machines], test_post[machines], test_post_sd[machines]),
        coverage_by_machine=interval_coverage(truth, test_post, test_post_sd, 0.9),
        batches=test_batches,
        products=batch_energy.product_summary(test_batches),
        sensor_check=sensors.single_sensor_check(
            val_sd, data.meter[test], test_mean, test_sd, truth, machines
        ),
        budget=sensors.budget_curve(plan, data.meter[test], test_mean, test_sd, truth, machines,
                                    n_random=10 if fast else 30),
        anomalies=anomalies.find_anomalies(val_post, test_post, machines, truth),
        overnight=anomalies.overnight_profile(val_post, test_post, machines, truth),
        drivers=top_drivers(priors, X.loc[val], targets.loc[val], sample=800 if fast else 2000),
        daily_sd_scale=daily_scale,
        daily_coverage=daily_coverage(truth[machines], test_post[machines], test_post_sd[machines], daily_scale),
        flows=batch_energy.energy_flows(data.log, X.loc[test], data.machines, test_post),
        priors=priors,
        feature_columns=list(X.columns),
        interval_scale=scale,
        batch_sd_scale=batch_scale,
    )
    say(f"Done in {time.perf_counter() - started:.0f}s")
    return results


def reestimate(results: Results, log: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Re-run the trained model over the test week with a different production log.

    Used when a logbook page is read from a photo: swap that day's batches in and see
    what the model makes of them. Returns (estimate, calibrated sd).
    """
    X = build_features(results.meter, log).reindex(columns=results.feature_columns, fill_value=0.0)
    mean, sd = results.priors.predict(X)
    estimate, estimate_sd = reconcile(results.meter, mean, sd)
    return estimate, estimate_sd * results.interval_scale


def save(results: Results, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump(results, f)


def load(path: str | Path) -> Results:
    with Path(path).open("rb") as f:
        return pickle.load(f)


def print_summary(results: Results) -> None:
    pd.set_option("display.width", 120)
    print("\nModel ladder (test period, never seen in training):")
    print(results.ladder.round(3).to_string(index=False))

    print("\nPer machine (final model):")
    print(results.per_machine.round(2).to_string())

    print("\nConfidence bands, claimed vs actual coverage:")
    print(results.coverage.round(3).to_string(index=False))

    print("\nWhere to measure next (chosen on validation, checked on test):")
    print(results.sensor_check.round(2).to_string(index=False))

    print("\nAccuracy vs number of sensors:")
    print(results.budget.round(3).to_string(index=False))

    print("\nAnomalies flagged in the test week:")
    if results.anomalies.empty:
        print("  none")
    else:
        numbers = results.anomalies.select_dtypes("number").columns
        print(results.anomalies.round(dict.fromkeys(numbers, 2)).to_string(index=False))
