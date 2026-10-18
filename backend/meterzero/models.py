"""The model ladder, from a spreadsheet-style baseline to meter-reconciled estimates.

1. ScheduleBaseline  typical power per machine for each production state.
2. MachinePriors     per-machine gradient boosting on log + meter features, with a
                     second model that predicts how wrong the first one tends to be.
3. reconcile()       forces the per-machine guesses to add up to the meter, moving
                     each one in proportion to how unsure it was.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import KFold, cross_val_predict

MIN_SD = 0.05  # kW; nothing is ever perfectly known


class ScheduleBaseline:
    """What you could do with a spreadsheet: median power per machine for each production
    state and hour of day. Rare combinations fall back to the state alone, then to overall."""

    MIN_SAMPLES = 30

    def fit(self, state: pd.Series, targets: pd.DataFrame) -> ScheduleBaseline:
        by_hour = targets.groupby([state.to_numpy(), state.index.hour])
        counts = by_hour.size()
        self.by_state_hour_ = by_hour.median()[counts >= self.MIN_SAMPLES]
        self.by_state_ = targets.groupby(state.to_numpy()).median()
        self.overall_ = targets.median()
        return self

    def predict(self, state: pd.Series) -> pd.DataFrame:
        keys = pd.MultiIndex.from_arrays([state.to_numpy(), state.index.hour])
        estimate = self.by_state_hour_.reindex(keys)
        estimate.index = state.index
        by_state = self.by_state_.reindex(state.to_numpy())
        by_state.index = state.index
        return estimate.fillna(by_state).fillna(self.overall_)


class MachinePriors:
    """For each machine: a model of mean power and a model of its typical error.

    The error model is trained on out-of-fold residuals (contiguous time blocks, no
    shuffling), so it learns how wrong the mean model is on data it hasn't seen.
    """

    def __init__(self, n_folds: int = 3, seed: int = 0, max_iter: int = 250):
        self.n_folds = n_folds
        self.template = HistGradientBoostingRegressor(
            max_iter=max_iter,
            learning_rate=0.06,
            max_leaf_nodes=31,
            min_samples_leaf=40,
            l2_regularization=1.0,
            early_stopping=False,
            random_state=seed,
        )

    def fit(self, X: pd.DataFrame, targets: pd.DataFrame) -> MachinePriors:
        folds = KFold(self.n_folds, shuffle=False)
        self.mean_models_, self.error_models_ = {}, {}
        for column in targets:
            y = targets[column].to_numpy()
            out_of_fold = cross_val_predict(clone(self.template), X, y, cv=folds)
            self.mean_models_[column] = clone(self.template).fit(X, y)
            self.error_models_[column] = clone(self.template).fit(X, np.abs(y - out_of_fold))
        return self

    def predict(self, X: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Mean and standard deviation in kW, one column per target."""
        mean = pd.DataFrame({c: m.predict(X) for c, m in self.mean_models_.items()}, index=X.index)
        # For a normal distribution, E|error| = sd * sqrt(2 / pi).
        sd = pd.DataFrame(
            {c: m.predict(X) * np.sqrt(np.pi / 2) for c, m in self.error_models_.items()},
            index=X.index,
        )
        return mean, sd.clip(lower=MIN_SD)


def reconcile(
    meter: pd.Series,
    mean: pd.DataFrame,
    sd: pd.DataFrame,
    metered: dict[str, pd.Series] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Condition independent Gaussian guesses on the fact that they must sum to the meter.

    With x_i ~ N(m_i, v_i) and the constraint sum(x) = meter, the posterior is

        x_i = m_i + (v_i / V) * (meter - sum(m))      var_i = v_i - v_i**2 / V,   V = sum(v)

    so the gap between the meter and the guesses goes mostly to whichever loads the
    model was least sure about. Machines with a real sensor (`metered`) are pinned to
    their reading and taken out of the pool first.

    Power can't be negative, so any load the update pushes below zero is pinned at
    zero and the gap is shared again among the rest. The result is non-negative and
    still adds up to the meter.
    """
    metered = metered or {}
    m, v = mean.to_numpy(float), (sd**2).to_numpy(float)
    total = meter.to_numpy(float)

    free = np.ones_like(m, dtype=bool)
    fixed = np.zeros_like(m)
    for j, column in enumerate(mean.columns):
        if column in metered:
            free[:, j] = False
            fixed[:, j] = np.asarray(metered[column], dtype=float)

    for _ in range(m.shape[1]):
        pool = np.where(free, v, 0).sum(axis=1)
        gap = total - np.where(free, m, fixed).sum(axis=1)
        share = np.divide(gap, pool, out=np.zeros_like(gap), where=pool > 0)
        post = np.where(free, m + v * share[:, None], fixed)
        negative = free & (post < 0)
        if not negative.any():
            break
        free &= ~negative  # pinned at zero; `fixed` is already 0 there

    safe_pool = np.where(pool > 0, pool, 1.0)[:, None]
    post_var = np.where(free, v - v**2 / safe_pool, 0.0)
    post_mean = pd.DataFrame(np.maximum(post, 0), index=mean.index, columns=mean.columns)
    post_sd = pd.DataFrame(np.sqrt(np.maximum(post_var, 0)), index=mean.index, columns=mean.columns)
    return post_mean, post_sd


def fit_interval_scale(truth: pd.DataFrame, mean: pd.DataFrame, sd: pd.DataFrame, level: float = 0.9) -> pd.Series:
    """Per-column factor so that `level` intervals cover `level` of the truth on held-out data."""
    # Divide by the sd exactly as it will be used; only guard against a true zero.
    z = ((truth - mean).abs() / sd.clip(lower=1e-9)).quantile(level)
    return z / norm.ppf(0.5 + level / 2)
