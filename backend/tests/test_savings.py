import numpy as np
import pandas as pd
import pytest

from meterzero import savings
from meterzero.batches import energy_flows


def flat_load(kw: float, days: int = 7) -> pd.Series:
    index = pd.date_range("2026-01-05", periods=days * 1440, freq="1min")
    return pd.Series(kw, index=index)


def test_bands_cover_every_hour_once_including_across_midnight():
    tariff = savings.Tariff()
    prices = tariff.price_by_hour()
    assert (prices > 0).all()
    assert prices[23] == prices[0] == prices[4] == 0.08
    assert prices[17] == prices[22] == 0.20
    assert set(tariff.band_of_hour()) == {"off-peak", "normal", "peak"}


def test_bill_of_a_flat_load():
    tariff = savings.Tariff()
    bill = savings.bill(flat_load(10.0), tariff)
    average_price = tariff.price_by_hour().mean()
    assert bill.energy_kwh == pytest.approx(10 * 24 * 7)
    assert bill.energy_cost == pytest.approx(10 * 24 * 7 * average_price)
    assert bill.peak_kw == pytest.approx(10.0)
    assert bill.monthly_cost == pytest.approx(10 * 24 * 30 * average_price + 8.0 * 10, rel=1e-3)


def test_cost_by_band_adds_up():
    load = flat_load(5.0)
    table = savings.cost_by_band(load, savings.Tariff())
    assert table["kWh"].sum() == pytest.approx(load.sum() / 60)
    assert table.loc["normal", "share of kWh"] == pytest.approx(12 / 24)


def test_shifting_by_zero_changes_nothing(small_factory):
    _, _, results = small_factory
    plan = savings.plan_shift(results, savings.Tariff(), "C", hours=0)
    assert plan.monthly_saving == pytest.approx(0, abs=1e-6)
    assert plan.conflicts == 0 and plan.batches_moved > 0


def test_moving_load_into_cheaper_hours_saves_money(small_factory):
    _, _, results = small_factory
    # Make the evening very expensive and the morning nearly free: moving earlier must pay.
    tariff = savings.Tariff(bands=[("cheap", 0, 14, 0.01), ("dear", 14, 24, 1.0)], demand_charge=0)
    earlier = savings.plan_shift(results, tariff, "C", hours=-4)
    later = savings.plan_shift(results, tariff, "C", hours=4)
    assert earlier.monthly_saving > 0 > later.monthly_saving
    assert earlier.monthly_saving_sd >= 0
    assert earlier.after.energy_kwh == pytest.approx(earlier.before.energy_kwh, rel=0.02)


def test_waste_fix_is_priced_from_the_alert(small_factory):
    _, _, results = small_factory
    fix = savings.plan_fix_waste(results, savings.Tariff(), "compressor")
    excess = results.anomalies.loc[results.anomalies["machine"] == "compressor", "excess kW"].mean()
    assert fix["monthly_kwh_wasted"] == pytest.approx(excess * 24 * 30, rel=0.01)


def test_energy_flows_account_for_every_kwh(small_factory):
    _, _, results = small_factory
    flows = energy_flows(results.log, results.test_features, results.machines, results.estimate)
    per_machine = flows.groupby("machine")["kWh"].sum()
    expected = results.estimate[results.machine_ids].sum() / 60
    np.testing.assert_allclose(per_machine.reindex(expected.index).to_numpy(), expected.to_numpy(), rtol=1e-6)
