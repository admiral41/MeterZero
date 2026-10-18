"""Turn the main meter and the production log into per-minute model inputs.

Two kinds of signal go in:
  * what the log says the factory is doing (which line runs which product, and for how long)
  * what the meter looks like around that minute (level, short-term swings, steps)

The rolling windows are centred because this is after-the-fact disaggregation, not
forecasting: looking a few minutes ahead in the *meter* is fair game.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

IDLE = "idle"


def line_activity(log: pd.DataFrame, line: str, index: pd.DatetimeIndex) -> pd.DataFrame:
    n = len(index)
    product = np.full(n, IDLE, dtype=object)
    since_start = np.full(n, -1.0)
    until_end = np.full(n, -1.0)

    for batch in log[log["line"] == line].itertuples():
        i, j = index.searchsorted(batch.start), index.searchsorted(batch.end)
        product[i:j] = batch.product
        since_start[i:j] = np.arange(j - i)
        until_end[i:j] = np.arange(j - i)[::-1]

    return pd.DataFrame(
        {"product": product, "since_start": since_start, "until_end": until_end}, index=index
    )


def production_state(log: pd.DataFrame, index: pd.DatetimeIndex) -> pd.Series:
    """One label per minute, e.g. "A:Cap-S | B:idle | C:Cure-Long"."""
    parts = [
        line + ":" + line_activity(log, line, index)["product"].astype(str)
        for line in sorted(log["line"].unique())
    ]
    return pd.concat(parts, axis=1).agg(" | ".join, axis=1)


def build_features(meter: pd.Series, log: pd.DataFrame) -> pd.DataFrame:
    index = meter.index
    features = {}

    active_columns = []
    for line in sorted(log["line"].unique()):
        activity = line_activity(log, line, index)
        active = (activity["product"] != IDLE).astype(float)
        features[f"{line}_active"] = active
        features[f"{line}_since_start"] = activity["since_start"].clip(upper=600)
        features[f"{line}_until_end"] = activity["until_end"].clip(upper=600)
        for product in sorted(log.loc[log["line"] == line, "product"].unique()):
            features[f"{line}_{product}"] = (activity["product"] == product).astype(float)
        active_columns.append(active)

    features["lines_active"] = sum(active_columns)
    features["hour"] = pd.Series(index.hour + index.minute / 60, index=index)
    features["weekday"] = pd.Series(index.dayofweek, index=index).astype(float)

    features["meter_kw"] = meter
    features["meter_step"] = meter.diff().fillna(0)
    for window in (5, 15, 61):
        rolling = meter.rolling(window, center=True, min_periods=1)
        features[f"meter_mean_{window}"] = rolling.mean()
        features[f"meter_std_{window}"] = rolling.std().fillna(0)
    features["meter_above_daily_min"] = meter - meter.groupby(index.normalize()).transform("min")

    return pd.DataFrame(features, index=index)
