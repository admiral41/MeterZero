"""Gemini tools, agent, Detective and Vision, exercised through a fake client (no network)."""
import json

import pandas as pd
import pytest
from google.genai import types

from fake_gemini import FakeClient
from meterzero import replay
from meterzero.agent import EnergyAgent, EnergyTools, Findings, gemini_status
from meterzero.vision import (LogbookPage, LogbookRow, compare_with_system_log, energy_from_page,
                              nameplate_check, page_to_log, product_catalog, Nameplate)


def first_day(results) -> str:
    return f"{results.meter.index[0]:%Y-%m-%d}"


def busiest_day(results) -> pd.Timestamp:
    log = results.log
    window = log[log["start"] >= results.meter.index[0]]
    return window.groupby(window["start"].dt.normalize()).size().idxmax()


def call_all(tools: EnergyTools, day: str) -> dict:
    args = {
        "get_machine_energy": ("Air compressor",), "explain_estimate": ("chiller", day),
        "get_daily_profile": (day,), "get_product_energy": ("Shaft",), "get_hourly_profile": ("press", day),
        "get_overnight_history": ("compressor",), "plan_schedule_shift": ("C", -1.0),
        "plan_fix_waste": ("compressor",), "get_morning_check": (day,),
    }
    return {f.__name__: f(*args.get(f.__name__, ())) for f in tools.functions()}


# --------------------------------------------------------------------------- tools


def test_every_tool_returns_json_and_has_a_gemini_schema(small_factory):
    _, _, results = small_factory
    tools = EnergyTools(results)
    outputs = call_all(tools, first_day(results))
    json.dumps(outputs)
    assert len(tools.functions()) == 15
    for function in tools.functions():
        declaration = types.FunctionDeclaration.from_callable_with_api_option(callable=function)
        assert declaration.name == function.__name__ and declaration.description

    assert outputs["get_anomalies"]["alerts"][0]["machine"] == "Air compressor"
    assert outputs["plan_fix_waste"]["monthly_saving"] > 0
    assert {"monthly_saving", "batches_that_clash_with_other_batches"} <= set(outputs["plan_schedule_shift"])


def test_tools_never_leak_ground_truth(small_factory):
    _, _, results = small_factory
    text = json.dumps(call_all(EnergyTools(results), first_day(results))).lower()
    assert "true" not in text and "actual" not in text


def test_tools_reject_bad_input_with_a_helpful_message(small_factory):
    _, _, results = small_factory
    tools = EnergyTools(results)
    with pytest.raises(ValueError, match="Known:"):
        tools.get_machine_energy("teleporter")
    with pytest.raises(ValueError, match="between"):
        tools.get_daily_profile("1999-01-01")
    with pytest.raises(ValueError, match="Products on that line"):
        tools.plan_schedule_shift("A", 1.0, product="Spaceship")
    with pytest.raises(ValueError, match="No waste alert"):
        tools.plan_fix_waste("press")


# --------------------------------------------------------------------------- agent


def test_agent_logs_and_streams_tool_calls_and_survives_errors(small_factory):
    _, _, results = small_factory
    streamed = []
    agent = EnergyAgent(results, client=FakeClient(results.log), model="test", on_tool_call=streamed.append)
    reply = agent.ask("Anything wasting energy?")

    assert "Air compressor" in reply.text
    assert [c["tool"] for c in reply.tool_calls] == [c["tool"] for c in streamed]
    assert reply.tool_calls[-1]["tool"] == "get_machine_energy" and "error" in reply.tool_calls[-1]["result"]


def test_detective_returns_structured_findings(small_factory):
    _, _, results = small_factory
    agent = EnergyAgent(results, client=FakeClient(results.log), model="test", max_tool_calls=25)
    investigation = agent.investigate()

    assert isinstance(investigation.findings, Findings)
    assert investigation.findings.findings[0].kind == "waste"
    tools_used = {c["tool"] for c in investigation.tool_calls}
    assert {"get_tariff_breakdown", "plan_schedule_shift", "plan_fix_waste"} <= tools_used


def test_gemini_status_reads_the_environment(monkeypatch):
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI"):
        monkeypatch.delenv(name, raising=False)
    assert gemini_status() is not None
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    assert gemini_status() is None


def test_replay_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("METERZERO_RUNS", str(tmp_path))
    assert replay.load("investigation") is None
    replay.save("investigation", {"report": "x"}, "test-model")
    record = replay.load("investigation")
    assert record["payload"] == {"report": "x"} and record["model"] == "test-model"


# --------------------------------------------------------------------------- vision


def messy_page(results, day: pd.Timestamp) -> LogbookPage:
    log = results.log
    batches = log[(log["start"] >= day) & (log["start"] < day + pd.Timedelta(days=1))]
    scrawl = {"Flange": "Flng", "Bracket": "Brkt", "Housing-M": "hsg-m", "Cure-Long": "cure lng"}
    rows = [LogbookRow(line=b.line.lower(), product=scrawl.get(b.product, b.product.upper()),
                       start=f"{b.start:%H:%M}", end=f"{b.end:%H:%M}", units=b.units) for b in batches.itertuples()]
    return LogbookPage(date=f"{day:%Y-%m-%d}", rows=rows)


def test_handwritten_variants_map_to_known_products(small_factory):
    _, _, results = small_factory
    day = busiest_day(results)
    log, problems = page_to_log(messy_page(results, day), product_catalog(results.log))

    assert problems == []
    check = compare_with_system_log(log, results.log)
    assert (check["read from photo"] == "✓").all()


def test_bad_rows_are_reported_not_guessed(small_factory):
    _, _, results = small_factory
    page = LogbookPage(date="2026-03-16", rows=[
        LogbookRow(line="Z", product="Shaft", start="08:00", end="09:00", units=5),
        LogbookRow(line="B", product="Teapot", start="08:00", end="09:00", units=5),
        LogbookRow(line="B", product="Shaft", start="10:00", end="09:00", units=5),
        LogbookRow(line="B", product="Shaft", start="ten", end="11:00", units=5),
    ])
    log, problems = page_to_log(page, product_catalog(results.log))
    assert log.empty and len(problems) == 4


def test_a_misread_time_shows_up_as_missed_and_extra(small_factory):
    _, _, results = small_factory
    day = busiest_day(results)
    page = messy_page(results, day)
    page.rows[0].start = (pd.Timestamp(f"{page.date} {page.rows[0].start}") - pd.Timedelta(minutes=30)).strftime("%H:%M")
    log, _ = page_to_log(page, product_catalog(results.log))
    check = compare_with_system_log(log, results.log)
    assert (check["read from photo"] == "✗ missed").sum() == 1
    assert check["read from photo"].str.startswith("✗ extra").sum() == 1


def test_energy_from_the_page_matches_the_system_log_estimate(small_factory):
    _, _, results = small_factory
    day = busiest_day(results)
    log, _ = page_to_log(messy_page(results, day), product_catalog(results.log))
    from_page = energy_from_page(results, log)
    stored = results.batches[results.batches["start"].dt.normalize() == day]

    assert len(from_page) == len(stored)
    assert from_page["estimated kWh"].sum() == pytest.approx(stored["estimated kWh"].sum(), rel=0.02)
    assert (from_page["sd kWh"] > 0).all()


def test_logbook_and_nameplate_reading_through_the_client(small_factory):
    from meterzero.vision import read_logbook, read_nameplate

    _, _, results = small_factory
    day = busiest_day(results)
    client = FakeClient(results.log, day=f"{day:%Y-%m-%d}")
    page = read_logbook(client, b"jpeg", "image/jpeg", product_catalog(results.log), model="test")
    assert page.date == f"{day:%Y-%m-%d}" and page.rows
    plate = read_nameplate(client, b"jpeg", "image/jpeg", model="test")
    assert plate.rated_power_kw == 22.0


@pytest.mark.parametrize("peak, expected", [(20.0, "✓ Consistent"), (30.0, "above"), (3.0, "oversized")])
def test_nameplate_cross_check(peak, expected):
    plate = Nameplate(machine_type="screw compressor", rated_power_kw=22.0)
    assert expected in nameplate_check(plate, peak)
