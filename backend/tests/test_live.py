import pandas as pd

from meterzero import live, savings


def busy_minute(results) -> pd.Timestamp:
    log = results.log
    window = log[(log["start"] >= results.meter.index[0]) & (log["line"] == "A")]
    batch = window.iloc[0]
    return batch["start"] + (batch["end"] - batch["start"]) / 2


def test_events_are_newest_first_and_mention_batches_and_prices(small_factory):
    _, _, results = small_factory
    t = busy_minute(results)
    events = live.events_between(results, t - pd.Timedelta(hours=12), t + pd.Timedelta(hours=12), savings.Tariff())
    times = [when for when, _ in events]
    assert times == sorted(times, reverse=True)
    text = " ".join(e for _, e in events)
    assert "started" in text and "price" in text


def test_waste_alerts_appear_at_the_start_of_the_night(small_factory):
    _, _, results = small_factory
    night = results.anomalies["night"].iloc[0]
    events = live.events_between(results, night - pd.Timedelta(hours=2), night, savings.Tariff())
    assert any("at night" in text and when == night - pd.Timedelta(hours=1) for when, text in events)
