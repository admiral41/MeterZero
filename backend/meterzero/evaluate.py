"""Scoring: how close are the estimates, and are the confidence bands honest?"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm


def disaggregation_accuracy(truth: pd.DataFrame, estimate: pd.DataFrame) -> float:
    """Kolter & Johnson's estimated accuracy: 1 - total |error| / (2 * total true energy).

    1.0 is perfect. Assigning every watt to the wrong machine scores 0.
    """
    error = np.abs(estimate[truth.columns].to_numpy() - truth.to_numpy()).sum()
    return 1 - error / (2 * truth.to_numpy().sum())


def machine_report(truth: pd.DataFrame, estimate: pd.DataFrame) -> pd.DataFrame:
    error = estimate[truth.columns] - truth
    true_kwh, est_kwh = truth.sum() / 60, estimate[truth.columns].sum() / 60
    return pd.DataFrame({
        "MAE (kW)": error.abs().mean(),
        "NDE": (error**2).sum() / (truth**2).sum(),  # normalised disaggregation error
        "true kWh": true_kwh,
        "estimated kWh": est_kwh,
        "energy error %": 100 * (est_kwh - true_kwh) / true_kwh,
    })


def summarize(name: str, truth: pd.DataFrame, estimate: pd.DataFrame) -> dict:
    report = machine_report(truth, estimate)
    return {
        "model": name,
        "accuracy": disaggregation_accuracy(truth, estimate),
        "mean MAE (kW)": report["MAE (kW)"].mean(),
        "mean |energy error| %": report["energy error %"].abs().mean(),
    }


def interval_coverage(truth, mean, sd, level: float) -> pd.Series:
    """Share of true values inside the central `level` interval, per column."""
    half_width = norm.ppf(0.5 + level / 2) * sd
    return ((truth - mean).abs() <= half_width).mean()


def daily_coverage(truth, mean, sd, scale: float, level: float = 0.9) -> float:
    """Share of machine-days whose true kWh falls inside the (scaled) daily band."""
    days = truth.index.normalize()
    error = (mean.groupby(days).sum() - truth.groupby(days).sum()).abs() / 60
    band = norm.ppf(0.5 + level / 2) * scale * sd.groupby(days).sum() / 60
    return float((error <= band).to_numpy().mean())


def coverage_curve(truth, mean, sd, levels=(0.5, 0.6, 0.7, 0.8, 0.9, 0.95)) -> pd.DataFrame:
    rows = [
        {"claimed": level, "actual": interval_coverage(truth, mean, sd, level).mean()}
        for level in levels
    ]
    return pd.DataFrame(rows)
