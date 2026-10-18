"""Load factory data from four CSV files and line it up on a 1-minute grid.

    meter.csv            timestamp, power_kw           the single main meter
    submeters.csv        timestamp, <machine id>, ...  per-machine kW (ground truth)
    production_log.csv   batch_id, line, product, start, end, units
    machines.csv         id, name, line, kind          line is "shared" for utilities

Sub-meter readings are only used to train on the past and to score on the hidden
test period. At prediction time the model sees the main meter and the log.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

OTHER = "other"  # everything on the main meter that isn't one of the listed machines


@dataclass
class FactoryData:
    meter: pd.Series          # kW, minute index
    submeters: pd.DataFrame   # kW per machine, same index
    log: pd.DataFrame
    machines: pd.DataFrame

    @property
    def machine_ids(self) -> list[str]:
        return list(self.machines["id"])

    @property
    def lines(self) -> list[str]:
        return sorted(self.log["line"].unique())

    def targets(self) -> pd.DataFrame:
        """Sub-meters plus the unmetered remainder, so the columns add up to the meter."""
        targets = self.submeters.copy()
        targets[OTHER] = self.meter - self.submeters.sum(axis=1)
        return targets


@dataclass
class TimeSplit:
    train: pd.DatetimeIndex
    val: pd.DatetimeIndex   # used for calibration and for choosing sensors
    test: pd.DatetimeIndex  # never touched until scoring


def load_factory(data_dir: str | Path, freq: str = "1min") -> FactoryData:
    data_dir = Path(data_dir)
    meter = _read_timeseries(data_dir / "meter.csv", freq)["power_kw"]
    submeters = _read_timeseries(data_dir / "submeters.csv", freq)
    machines = pd.read_csv(data_dir / "machines.csv")
    log = (
        pd.read_csv(data_dir / "production_log.csv", parse_dates=["start", "end"])
        .sort_values("start")
        .reset_index(drop=True)
    )

    missing = set(machines["id"]) - set(submeters.columns)
    if missing:
        raise ValueError(f"submeters.csv has no column for: {sorted(missing)}")

    index = meter.index.intersection(submeters.index)
    return FactoryData(meter.loc[index], submeters.loc[index, machines["id"]], log, machines)


def _read_timeseries(path: Path, freq: str) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["timestamp"], index_col="timestamp").sort_index()
    frame = frame.resample(freq).mean()
    # Bridge short dropouts; anything longer is left out rather than invented.
    return frame.interpolate(limit=5).dropna()


def split_by_day(index: pd.DatetimeIndex, val_days: int = 4, test_days: int = 7) -> TimeSplit:
    """Split on whole days, oldest first. Never shuffle: neighbouring minutes leak."""
    days = index.normalize().unique()
    if len(days) <= val_days + test_days:
        raise ValueError(f"need more than {val_days + test_days} days of data, got {len(days)}")
    val_start, test_start = days[-(val_days + test_days)], days[-test_days]
    return TimeSplit(
        train=index[index < val_start],
        val=index[(index >= val_start) & (index < test_start)],
        test=index[index >= test_start],
    )
