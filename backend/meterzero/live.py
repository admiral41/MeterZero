"""What happens during the plant's day, for the digital twin's event feed.

The demo replays the test week minute by minute, as if it were happening now. The events are what a
supervisor would want to hear about: batches starting and finishing, price changes, and waste alerts.
"""
from __future__ import annotations

import pandas as pd

from .savings import Tariff

OFF_KW = 0.6  # below this a machine is effectively switched off


def events_between(results, start: pd.Timestamp, end: pd.Timestamp, tariff: Tariff) -> list[tuple[pd.Timestamp, str]]:
    """Things a supervisor would want to hear about, newest first: batches, price changes, waste."""
    events = []
    log = results.log
    for batch in log[(log["start"] > start) & (log["start"] <= end)].itertuples():
        events.append((batch.start, f"Line {batch.line} started {batch.product}"))
    for batch in log[(log["end"] > start) & (log["end"] <= end)].itertuples():
        events.append((batch.end, f"Line {batch.line} finished {batch.product} ({batch.units:,} made)"))

    bands = tariff.band_of_hour()
    prices = tariff.price_by_hour()
    hour = (start.floor("h") + pd.Timedelta(hours=1))
    while hour <= end:
        if bands[hour.hour] != bands[(hour - pd.Timedelta(hours=1)).hour]:
            events.append((hour, f"Electricity is now {bands[hour.hour]} price ({tariff.currency}{prices[hour.hour]:.2f}/kWh)"))
        hour += pd.Timedelta(hours=1)

    names = dict(zip(results.machines["id"], results.machines["name"]))
    for alert in results.anomalies.to_dict("records"):
        moment = alert["night"] - pd.Timedelta(hours=1)  # the night starts at 23:00 the evening before
        if start < moment <= end:
            events.append((moment, f"{names[alert['machine']]} is using {alert['observed kW']:.1f} kW at night, "
                                   f"usually {alert['usual kW']:.1f} kW"))
    return sorted(events, key=lambda e: e[0], reverse=True)
