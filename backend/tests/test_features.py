import numpy as np
import pandas as pd
import pytest

from meterzero import anomalies
from meterzero.batches import conformal_scale
from meterzero.data import OTHER
from meterzero.explain import decompose, describe_feature, explain_machine


# --------------------------------------------------------------------------- anomaly checks


def nights(days: int, kw: dict[str, list[float]]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=days * 24 * 60, freq="1min")
    frame = pd.DataFrame(index=index)
    for machine, per_day in kw.items():
        frame[machine] = np.repeat(per_day, 24 * 60)
    return frame


def test_overnight_jump_is_flagged_and_steady_machine_is_not():
    rng = np.random.default_rng(0)
    val = nights(5, {"compressor": 1 + rng.normal(0, 0.1, 5), "press": 0.3 + rng.normal(0, 0.05, 5)})
    test = nights(4, {"compressor": [1.0, 1.1, 5.0, 5.2], "press": [0.3, 0.3, 0.35, 0.3]})
    test.index = test.index + pd.Timedelta(days=5)

    alerts = anomalies.find_anomalies(val, test, ["compressor", "press"])
    assert set(alerts["machine"]) == {"compressor"}
    # Day 3 of the test starts at 00:00, so the first bad night is the morning of that day.
    assert alerts["night"].min() == test.index[0].normalize() + pd.Timedelta(days=2)
    assert alerts["kWh/day if it persists"].min() > 70


def test_partial_nights_at_the_edge_are_skipped():
    frame = nights(2, {"m": [1.0, 1.0]})
    assert frame.index[-1].normalize() + pd.Timedelta(days=1) not in anomalies.overnight_kw(frame).index


def test_alert_summary_and_description():
    alerts = pd.DataFrame({
        "night": pd.to_datetime(["2026-03-26", "2026-03-27"]), "machine": ["compressor"] * 2,
        "usual kW": [1.3, 1.3], "observed kW": [5.0, 6.0], "excess kW": [3.7, 4.7], "z": [8, 10],
        "kWh/day if it persists": [89.0, 113.0],
    })
    summary = anomalies.summarize_alerts(alerts)
    assert summary.iloc[0]["nights flagged"] == 2
    text = anomalies.describe(summary.iloc[0], "Air compressor")
    assert "Thursday 26 March" in text and "101 kWh wasted every day" in text


# --------------------------------------------------------------------------- calibration and explanation


def test_conformal_scale_recovers_a_known_spread():
    z = pd.Series(np.abs(np.random.default_rng(1).normal(0, 2.0, 20000)))
    assert conformal_scale(z) == pytest.approx(2.0, rel=0.05)


def test_conformal_scale_is_cautious_with_few_samples():
    z = pd.Series([0.1, 0.2, 0.3, 0.4, 5.0])
    # With five samples the 90% conformal rank is the largest one.
    assert conformal_scale(z) == pytest.approx(5.0 / 1.6448536, rel=1e-4)


def test_decomposition_adds_up():
    index = pd.date_range("2026-01-01", periods=60, freq="1min")
    prior = pd.DataFrame({"a": 10.0, "b": 5.0}, index=index)
    sd = pd.DataFrame({"a": 3.0, "b": 1.0}, index=index)
    final = prior + pd.DataFrame({"a": 0.9, "b": 0.1}, index=index)
    parts = decompose(prior, sd, final, "a")
    assert parts["learned guess kWh"] + parts["meter adjustment kWh"] == pytest.approx(parts["final kWh"])
    assert parts["share of the meter gap it absorbs"] == pytest.approx(0.9)


@pytest.mark.parametrize("name, words", [
    ("A_active", "whether line A is running"),
    ("B_Flange", "line B making Flange"),
    ("meter_mean_15", "the meter's 15-minute average"),
    ("lines_active", "how many lines are running"),
])
def test_feature_names_read_like_english(name, words):
    assert describe_feature(name) == words


# --------------------------------------------------------------------------- end to end


def test_pipeline_end_to_end(small_factory):
    _, _, results = small_factory
    machines = results.machine_ids
    ladder = results.ladder.set_index("model")["accuracy"]

    assert ladder.iloc[-1] > ladder.iloc[0], "final model should beat the schedule baseline"
    np.testing.assert_allclose(results.estimate.sum(axis=1), results.meter, atol=1e-6)
    assert 0.75 <= results.coverage_by_machine.mean() <= 0.98
    assert results.budget["recommended"].is_monotonic_increasing
    assert results.budget["recommended"].iloc[-1] == pytest.approx(1.0)
    assert set(results.drivers) == set(machines) | {OTHER}


def test_the_injected_leak_is_caught(small_factory):
    _, _, results = small_factory
    assert "compressor" in set(results.anomalies["machine"])
    assert (results.anomalies["true kW"] > results.anomalies["usual kW"]).all()


def test_explanations_cover_every_machine(small_factory):
    _, _, results = small_factory
    day = results.meter.index[0].normalize()
    for machine in results.machine_ids + [OTHER]:
        e = explain_machine(results, machine, day, day + pd.Timedelta(days=1))
        assert e["final kWh"] >= 0 and e["90% band ± kWh"] >= 0
