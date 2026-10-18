import numpy as np
import pandas as pd
import pytest

from meterzero import sensors, simulate
from meterzero.data import OTHER, load_factory, split_by_day
from meterzero.evaluate import disaggregation_accuracy, interval_coverage
from meterzero.models import fit_interval_scale, reconcile


def toy_priors(n=500, seed=0):
    rng = np.random.default_rng(seed)
    index = pd.date_range("2026-01-01", periods=n, freq="1min")
    truth = pd.DataFrame({
        "quiet": rng.normal(5, 0.1, n),
        "noisy": rng.normal(20, 4.0, n),
        OTHER: rng.normal(10, 1.0, n),
    }, index=index)
    mean = pd.DataFrame({"quiet": 5.0, "noisy": 20.0, OTHER: 10.0}, index=index)
    sd = pd.DataFrame({"quiet": 0.1, "noisy": 4.0, OTHER: 1.0}, index=index)
    return truth.sum(axis=1), truth, mean, sd


def test_reconciled_estimates_add_up_to_the_meter():
    meter, _, mean, sd = toy_priors()
    estimate, _ = reconcile(meter, mean, sd)
    np.testing.assert_allclose(estimate.sum(axis=1), meter, atol=1e-6)


def test_reconciled_estimates_stay_non_negative_and_still_add_up():
    meter, _, mean, sd = toy_priors()
    low_meter = meter * 0 + 6.0  # far below the guesses: the noisy load would go negative
    estimate, estimate_sd = reconcile(low_meter, mean, sd)
    assert (estimate >= 0).all().all()
    np.testing.assert_allclose(estimate.sum(axis=1), low_meter, atol=1e-6)
    assert (estimate_sd["noisy"] == 0).all()  # pinned at zero, so no longer uncertain


def test_reconcile_moves_the_least_certain_load_most():
    meter, _, mean, sd = toy_priors()
    estimate, _ = reconcile(meter + 5, mean, sd)
    shift = (estimate - mean).mean()
    assert shift["noisy"] > shift[OTHER] > shift["quiet"]


def test_metered_machine_is_pinned_and_certain():
    meter, truth, mean, sd = toy_priors()
    estimate, estimate_sd = reconcile(meter, mean, sd, {"noisy": truth["noisy"]})
    np.testing.assert_allclose(estimate["noisy"], truth["noisy"])
    assert (estimate_sd["noisy"] == 0).all()


def test_reconciling_beats_the_raw_guess():
    meter, truth, mean, sd = toy_priors()
    estimate, _ = reconcile(meter, mean, sd)
    assert disaggregation_accuracy(truth, estimate) > disaggregation_accuracy(truth, mean)


def test_calibration_fixes_overconfident_bands():
    _, truth, mean, sd = toy_priors(n=5000)
    too_narrow = sd / 3
    scaled = too_narrow * fit_interval_scale(truth, mean, too_narrow)
    assert interval_coverage(truth, mean, scaled, 0.9).mean() == pytest.approx(0.9, abs=0.02)


def test_recommender_picks_the_most_ambiguous_machine():
    _, _, _, sd = toy_priors()
    ranking = sensors.rank_sensors(sd, ["quiet", "noisy"])
    assert ranking["machine"].iloc[0] == "noisy"


def test_split_is_by_time_and_does_not_overlap():
    index = pd.date_range("2026-01-01", periods=20 * 24 * 60, freq="1min")
    split = split_by_day(index, val_days=3, test_days=5)
    assert split.train.max() < split.val.min() <= split.val.max() < split.test.min()
    assert len(split.train) + len(split.val) + len(split.test) == len(index)
    assert split.test.normalize().nunique() == 5


def test_simulated_data_round_trips_through_the_loader(tmp_path):
    simulate.write(simulate.simulate(days=3, seed=1), tmp_path)
    data = load_factory(tmp_path)

    assert len(data.meter) == 3 * 24 * 60
    assert list(data.submeters.columns) == data.machine_ids
    assert set(data.lines) == {"A", "B", "C"}
    # The unmetered remainder should be real, positive load, not a bookkeeping artefact.
    assert data.targets()[OTHER].mean() > 5
