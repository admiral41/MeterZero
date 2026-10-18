"""Simulate a small factory: one main meter, seven sub-metered machines and a production log.

This stands in for the real 43-asset dataset until it is wired in. It gives us
ground truth to build and score against, and it writes exactly the four CSV files
that `meterzero.data.load_factory` reads. Swapping in real data later means
writing an exporter to that format, not touching the model.

    python -m meterzero simulate --days 28
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

START = pd.Timestamp("2026-03-02")  # a Monday


@dataclass(frozen=True)
class Machine:
    id: str
    name: str
    line: str  # "A", "B", "C", or "shared" for utilities that serve every line
    kind: str


MACHINES = [
    Machine("press", "Injection press", "A", "hydraulic pump + barrel heaters"),
    Machine("dryer", "Resin dryer", "A", "thermostatic heater"),
    Machine("cnc", "CNC mill", "B", "spindle motor"),
    Machine("washer", "Parts washer", "B", "tank heater + spray pump"),
    Machine("oven", "Curing oven", "C", "batch oven"),
    Machine("compressor", "Air compressor", "shared", "load/unload screw compressor"),
    Machine("chiller", "Process chiller", "shared", "cycling refrigeration"),
]

# Per line: product -> (load factor on the line's machines, units per hour)
PRODUCTS = {
    "A": {"Cap-S": (1.0, 900), "Housing-M": (1.3, 240), "Crate-L": (1.7, 60)},
    "B": {"Shaft": (0.8, 40), "Bracket": (1.0, 25), "Flange": (1.4, 12)},
    "C": {"Cure-Std": (1.0, 200), "Cure-Long": (1.25, 150)},
}

# Weekday -> (shift start hour, shift end hour). Sunday is closed.
SHIFTS = {0: (6, 22), 1: (6, 22), 2: (6, 22), 3: (6, 22), 4: (6, 22), 5: (6, 14)}


@dataclass
class LineState:
    active: np.ndarray   # a batch is running
    load: np.ndarray     # product load factor, 0 while idle
    cycle: np.ndarray    # minutes per unit, 0 while idle
    elapsed: np.ndarray  # minutes since the batch started, -1 while idle


def plan_batches(days: int, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for day in range(days):
        date = START + pd.Timedelta(days=day)
        if date.dayofweek not in SHIFTS:
            continue
        start_hour, end_hour = SHIFTS[date.dayofweek]
        shift_end = date + pd.Timedelta(hours=end_hour)

        for line, products in PRODUCTS.items():
            if rng.random() < 0.08:  # line down for maintenance today
                continue
            t = date + pd.Timedelta(hours=start_hour, minutes=int(rng.integers(30, 50)))
            while t + pd.Timedelta(minutes=60) < shift_end:
                length = rng.integers(150, 200) if line == "C" else rng.integers(80, 240)
                end = min(t + pd.Timedelta(minutes=int(length)), shift_end)
                product = str(rng.choice(list(products)))
                _, rate = products[product]
                hours = (end - t) / pd.Timedelta(hours=1)
                rows.append({
                    "line": line,
                    "product": product,
                    "start": t,
                    "end": end,
                    "units": int(rate * hours * rng.uniform(0.85, 1.05)),
                })
                t = end + pd.Timedelta(minutes=int(rng.integers(15, 45)))

    log = pd.DataFrame(rows).sort_values("start").reset_index(drop=True)
    log.insert(0, "batch_id", [f"B{i:04d}" for i in range(1, len(log) + 1)])
    return log


def line_state(log: pd.DataFrame, line: str, index: pd.DatetimeIndex) -> LineState:
    n = len(index)
    state = LineState(np.zeros(n, bool), np.zeros(n), np.zeros(n), np.full(n, -1.0))
    for batch in log[log["line"] == line].itertuples():
        i, j = index.searchsorted(batch.start), index.searchsorted(batch.end)
        load, rate = PRODUCTS[line][batch.product]
        state.active[i:j] = True
        state.load[i:j] = load
        state.cycle[i:j] = 60 / rate
        state.elapsed[i:j] = np.arange(j - i)
    return state


def thermostat(demand: np.ndarray, rng: np.random.Generator, step: float) -> np.ndarray:
    """On/off controller holding a level inside a band.

    `demand` is the fraction of the time the unit has to run to keep up (0 = switched
    off). A larger `step` means shorter on/off cycles. The random start level and a
    little jitter keep the cycles out of phase with everything else, which is exactly
    what makes these loads hard to tell apart from one meter.
    """
    on = np.zeros(len(demand), bool)
    level, running = rng.random(), False
    for t, d in enumerate(demand):
        if d <= 0:
            running = False
            level = max(level - 0.01, 0.0)  # cools down while off, so it has to recover later
            continue
        if level <= 0:
            running = True
        elif level >= 1:
            running = False
        level += (step if running else 0.0) - step * min(d, 1.0) + rng.normal(0, 0.02)
        on[t] = running
    return on


def shift_hours(index: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """Whether each minute is inside a shift, and how many minutes into it."""
    starts = np.array([SHIFTS.get(d, (0, 0))[0] for d in range(7)])[index.dayofweek]
    ends = np.array([SHIFTS.get(d, (0, 0))[1] for d in range(7)])[index.dayofweek]
    hour = index.hour + index.minute / 60
    in_shift = (hour >= starts) & (hour < ends)
    return in_shift, np.where(in_shift, (hour - starts) * 60, -1)


def ambient_temperature(index: pd.DatetimeIndex, rng: np.random.Generator) -> np.ndarray:
    """0..1 scale: cool nights, warm afternoons, and some day-to-day weather."""
    days = (index.normalize() - index[0].normalize()).days
    weather = np.cumsum(rng.normal(0, 0.06, days.max() + 1))
    hour = index.hour + index.minute / 60
    return np.clip(0.5 + 0.3 * np.sin(2 * np.pi * (hour - 9) / 24) + weather[days], 0, 1)


def simulate_machines(
    index, lines: dict[str, LineState], rng, leak_from: pd.Timestamp | None = None
) -> tuple[pd.DataFrame, np.ndarray]:
    """Per-machine kW for every minute, plus the unmetered remainder of the site.

    `leak_from` starts a compressed-air leak on that date: a real-world fault that
    wastes energy around the clock and that the anomaly check should catch.
    """
    n = len(index)
    in_shift, shift_minute = shift_hours(index)
    ambient = ambient_temperature(index, rng)
    a, b, c = lines["A"], lines["B"], lines["C"]

    def noise(sd):
        return rng.normal(0, sd, n)

    power = {}

    # Press: barrel heaters warm up at the start of the shift and hold temperature between
    # batches; the hydraulic pump adds load that grows with part size. The first minutes of a
    # batch are a purge, which runs a bit hotter.
    press = np.where(in_shift, 6.0, 0.2)
    press = np.where(in_shift & (shift_minute < 35), 24.0, press)
    purge = np.where(a.elapsed < 10, 1.2, 1.0)
    press = np.where(a.active, 8.0 + 10.0 * a.load * purge, press)
    power["press"] = press + noise(0.8) * (press > 1)

    # Dryer: a thermostatic heater. Runs harder when the press eats more resin.
    dryer_demand = np.where(in_shift, 0.2, 0.0) + 0.45 * a.active * a.load / 1.7
    power["dryer"] = 9.0 * thermostat(dryer_demand, rng, step=0.10) + 0.4 * in_shift + noise(0.15)

    # CNC: spindle cuts for most of each part cycle, then idles while the part is swapped.
    cycle = np.maximum(b.cycle, 1e-9)
    phase = (b.elapsed % cycle) / cycle
    cutting = np.where(phase < 0.7, 1.0, 0.25)
    cnc = np.where(in_shift, 2.5, 0.3)
    cnc = np.where(b.active, 3.0 + 13.0 * b.load * cutting, cnc)
    power["cnc"] = cnc + noise(0.6) * (cnc > 1)

    # Washer: tank heater holds temperature all shift; the spray pump fires every 20 minutes
    # during a batch to clean the parts that came off the mill.
    tank = 4.0 * thermostat(np.where(in_shift, 0.35, 0.0) + 0.1 * b.active, rng, step=0.15)
    spray = 6.5 * np.sqrt(b.load) * (b.active & (b.elapsed % 20 < 5))
    power["washer"] = tank + spray + 0.3 * in_shift + noise(0.2)

    # Oven: full power ramp to temperature, then a thermostat holds it; fans run throughout.
    ramp = c.active & (c.elapsed < 25)
    hold = 38.0 * thermostat(np.where(c.active & ~ramp, 0.35 * c.load, 0.0), rng, step=0.2)
    fans = np.where(c.active, 3.0, np.where(in_shift, 0.5, 0.1))
    power["oven"] = fans + np.where(ramp, 42.0, hold) + noise(0.3)

    # Compressor: air demand grows with the number of busy lines (plus leaks overnight). It
    # loads and unloads to hold pressure, and the motor stops after 10 idle minutes.
    air = np.where(in_shift, 0.08, 0.02) + 0.30 * a.active + 0.22 * b.active + 0.12 * c.active
    if leak_from is not None:
        air = air + 0.15 * (index >= leak_from)
    loaded = thermostat(air, rng, step=0.25)
    last_loaded = np.maximum.accumulate(np.where(loaded, np.arange(n), -10**9))
    unloaded_for = np.arange(n) - last_loaded
    compressor = np.where(loaded, 22.0, np.where(unloaded_for < 10, 8.0, 0.4))
    power["compressor"] = compressor + noise(0.5) * (compressor > 1)

    # Chiller: pumps run 24/7; the refrigeration compressor cycles harder when the press is
    # busy and on warm afternoons.
    cooling = np.where(in_shift, 0.15 + 0.25 * ambient, 0.03) + 0.3 * a.active * a.load / 1.7
    power["chiller"] = 1.2 + 14.0 * thermostat(cooling, rng, step=0.12) + noise(0.3)

    frame = pd.DataFrame(power, index=index).clip(lower=0)
    other = simulate_other_loads(index, in_shift, ambient, rng)
    return frame, other


def simulate_other_loads(index, in_shift, ambient, rng) -> np.ndarray:
    """Everything nobody meters: lights, HVAC, offices, and the forklift charger."""
    n = len(index)
    lighting = np.where(in_shift, 9.0, 1.5)
    hvac = 4.0 + 5.0 * ambient + rng.normal(0, 0.4, n)

    misc = np.empty(n)  # slow-wandering office and plug loads
    misc[0] = 3.0
    shocks = rng.normal(0, 0.15, n)
    for t in range(1, n):
        misc[t] = 3.0 + 0.98 * (misc[t - 1] - 3.0) + shocks[t]

    forklift = np.zeros(n)
    for _ in range(int(len(index) / (60 * 24 * 7) * 3)):  # about three charges a week
        start = rng.integers(0, n - 240)
        forklift[start:start + rng.integers(150, 240)] = 6.0

    return lighting + hvac + np.clip(misc, 0.5, None) + forklift


LEAK_DAY = 24  # the air leak starts on day 24 (Thursday of the last week); None to disable


def simulate(days: int = 28, seed: int = 7, leak_day: int | None = LEAK_DAY) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    index = pd.date_range(START, periods=days * 24 * 60, freq="1min", name="timestamp")
    log = plan_batches(days, rng)
    lines = {line: line_state(log, line, index) for line in PRODUCTS}
    leak_from = START + pd.Timedelta(days=leak_day) if leak_day is not None and leak_day < days else None
    machines, other = simulate_machines(index, lines, rng, leak_from)
    meter = machines.sum(axis=1) + other + rng.normal(0, 0.3, len(index))

    return {
        "meter": meter.rename("power_kw").round(3).to_frame(),
        "submeters": machines.round(3),
        "production_log": log,
        "machines": pd.DataFrame([vars(m) for m in MACHINES]),
    }


def write(tables: dict[str, pd.DataFrame], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    tables["meter"].to_csv(out / "meter.csv")
    tables["submeters"].to_csv(out / "submeters.csv")
    tables["production_log"].to_csv(out / "production_log.csv", index=False)
    tables["machines"].to_csv(out / "machines.csv", index=False)

