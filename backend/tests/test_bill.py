import json
from pathlib import Path

import pytest

from meterzero import bill
from meterzero.savings import Tariff

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "bills" / "np" / "2026-03.json"   # a Nepal-style kVA bill


@pytest.fixture
def reading():
    return bill.BillReading.model_validate(json.loads(SAMPLE.read_text()))


def test_prices_come_from_the_bill(reading):
    tariff = bill.tariff_from_bill(reading)
    prices = {name: price for name, _, _, price in tariff.bands}
    assert prices == {"off-peak": 7.0, "normal": 10.5, "peak": 12.5}
    assert tariff.demand_charge == 280.0 and tariff.currency == "Rs "


def test_missing_band_rates_fall_back_to_the_average(reading):
    partial = reading.model_copy(update={"rate_peak": 0, "rate_normal": 0, "rate_offpeak": 0, "demand_rate": 0})
    tariff = bill.tariff_from_bill(partial, Tariff())
    average = reading.energy_charge / reading.kwh_total
    assert all(price == pytest.approx(average) for *_, price in tariff.bands)
    assert tariff.demand_charge == pytest.approx(reading.demand_charge / reading.max_demand_kva)


def test_split_by_machine_adds_up_to_the_bill(small_factory, reading):
    _, _, results = small_factory
    split = bill.split_by_machine(results, reading, bill.tariff_from_bill(reading))
    assert split["total"].sum() == pytest.approx(reading.total_amount)
    assert split["share"].sum() == pytest.approx(1.0)
    assert (split["total"] > 0).all()


def test_split_by_product_includes_energy_that_made_nothing(small_factory, reading):
    _, _, results = small_factory
    products = bill.split_by_product(results, reading)
    assert products["amount"].sum() == pytest.approx(reading.total_amount)
    assert "Idle & overhead" in products.index


def test_check_against_meter_reports_a_daily_comparison(small_factory, reading):
    _, _, results = small_factory
    check = bill.check_against_meter(results, reading, bill.tariff_from_bill(reading))
    assert check["bill_kwh_per_day"] == pytest.approx(reading.kwh_total / reading.days)
    assert abs(check["difference"]) < 0.5   # same simulated plant, different weeks
    assert set(check["bill_share"]) == {"peak", "normal", "off-peak"}


def kinds(findings, tone):
    return {f["kind"] for f in findings if f["tone"] == tone}


def test_bill_check_catches_an_overcharge(small_factory, reading):
    _, _, results = small_factory
    padded = reading.model_copy(update={"energy_charge": reading.energy_charge + 5000, "total_amount": reading.total_amount + 5000})
    findings = bill.check_bill(results, padded, bill.tariff_from_bill(padded))
    overcharge = next(f for f in findings if f["kind"] == "arithmetic")
    assert overcharge["tone"] == "bad" and overcharge["amount"] == pytest.approx(5000, abs=50)
    assert findings[0] is overcharge   # problems come first


def test_bill_check_flags_a_power_factor_surcharge(small_factory, reading):
    _, _, results = small_factory
    low = reading.model_copy(update={"power_factor": 0.82, "power_factor_penalty": 9000, "total_amount": reading.total_amount + 9000})
    findings = bill.check_bill(results, low, bill.tariff_from_bill(low))
    assert "power_factor" in kinds(findings, "bad")
    assert "total" not in {f["kind"] for f in findings}   # the surcharge explains the total


def test_a_clean_bill_has_no_problems(small_factory, reading):
    _, _, results = small_factory
    findings = bill.check_bill(results, reading, bill.tariff_from_bill(reading))
    assert not kinds(findings, "bad")
    assert "arithmetic" in kinds(findings, "ok")
