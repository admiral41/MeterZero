"""Build any plant: a library of machine types, a plant layout, and a simulator for it.

A plant is a JSON spec: rooms on a floor, production lines with their products, and
machines placed in rooms. Each machine has a type from the library below, which
decides how it draws power (motors that follow the product, thermostatic heaters,
load/unload compressors, ovens that ramp then hold, lights that follow the shift...).

`simulate_plant` turns a spec into the same four CSV files the real-data loader
reads, so MeterZero trains on a user-designed plant exactly as it would on a real one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from .simulate import START, thermostat

SHARED, BUILDING = "shared", "building"


# --------------------------------------------------------------------------- the machine library


@dataclass(frozen=True)
class MachineType:
    id: str
    label: str
    description: str
    serves: str           # "line": one production line · "shared": every line · "building": the site
    default_kw: float
    size: tuple[float, float, float]   # width, depth, height on the floor (metres-ish)
    shape: str            # how the 3D view draws it


LIBRARY = {t.id: t for t in [
    MachineType("injection_press", "Injection moulding press", "Barrel heaters plus a hydraulic pump that works harder for bigger parts.", "line", 20, (4.6, 1.8, 1.4), "press"),
    MachineType("cnc_machine", "CNC machine", "A spindle that cuts for most of each part cycle, then idles while parts are swapped.", "line", 16, (2.6, 2.2, 1.6), "cabinet"),
    MachineType("conveyor", "Conveyor", "Runs steadily while its line is producing.", "line", 3, (5.0, 0.8, 0.6), "conveyor"),
    MachineType("mixer", "Mixer / motor drive", "A motor in bursts during production: mixers, sewing lines, grinders.", "line", 11, (1.6, 1.6, 1.4), "tank"),
    MachineType("welder", "Welding station", "Short, heavy bursts while the line runs.", "line", 12, (1.4, 1.4, 1.5), "cabinet"),
    MachineType("thermo_heater", "Thermostatic heater", "Cycles on and off to hold a temperature: dryers, tanks, proofers.", "line", 9, (1.3, 1.3, 1.9), "tower"),
    MachineType("batch_oven", "Batch oven / furnace", "Heats up at full power, then a thermostat holds the temperature.", "line", 45, (4.6, 3.0, 2.0), "oven"),
    MachineType("parts_washer", "Parts washer", "Tank heater all shift, spray pump in bursts during batches.", "line", 10, (2.2, 1.6, 1.1), "cabinet"),
    MachineType("air_compressor", "Air compressor", "Loads and unloads to keep pressure; demand grows with busy lines.", "shared", 22, (2.0, 1.4, 1.3), "compressor"),
    MachineType("chiller", "Process chiller", "Refrigeration that cycles harder when lines are busy and afternoons are warm.", "shared", 15, (1.8, 1.8, 1.5), "chiller"),
    MachineType("cold_room", "Cold room / freezer", "Cycles day and night to stay cold; works harder when it's warm.", "shared", 8, (3.0, 2.4, 2.2), "room"),
    MachineType("pump", "Pump / fan", "Runs steadily through the shift.", "shared", 7.5, (1.2, 0.9, 0.9), "pump"),
    MachineType("hvac", "Air conditioning / HVAC", "Follows the outside temperature.", "building", 12, (2.0, 1.2, 1.2), "hvac"),
    MachineType("lighting", "Lighting", "On while the plant is staffed, a little at night.", "building", 6, (1.0, 1.0, 0.3), "lights"),
    MachineType("office", "Offices and sockets", "Computers, kettles, chargers: wanders through the day.", "building", 4, (2.2, 1.2, 0.7), "desk"),
]}


# --------------------------------------------------------------------------- the plant spec


class Product(BaseModel):
    name: str
    load: float = Field(1.0, description="How hard it works the line's machines (1 = normal)")
    rate: float = Field(100, description="Units made per hour")


class Line(BaseModel):
    id: str
    name: str
    products: list[Product]


class Room(BaseModel):
    id: str
    name: str
    x: float
    y: float
    w: float
    d: float


class MachineSpec(BaseModel):
    id: str
    name: str
    type: str
    line: str = Field(description="A line id, 'shared' or 'building'")
    rated_kw: float
    x: float
    y: float
    rotation: float = 0.0


class Fault(BaseModel):
    machine: str
    start_day: int = Field(description="Day (counting from 0) the fault starts")
    kind: str = "leak"


class PlantSpec(BaseModel):
    id: str
    name: str
    description: str = ""
    reference: bool = False         # the built-in demo plant, whose data comes from simulate.py
    days: int = 28
    seed: int = 1
    shift_start: int = 6
    shift_end: int = 22
    saturday_end: int = 14          # 0 = closed on Saturdays
    floor_w: float = 26
    floor_d: float = 16
    panel_x: float = 1.5            # where the main meter / distribution panel stands
    panel_y: float = 1.5
    cable_y: float | None = None    # the cable tray runs along this line (default: middle of the floor)
    rooms: list[Room]
    lines: list[Line]
    machines: list[MachineSpec]
    fault: Fault | None = None

    def problems(self) -> list[str]:
        """Everything that would stop a simulation, in plain words."""
        issues = []
        lines = {line.id for line in self.lines}
        ids = [m.id for m in self.machines]
        if len(set(ids)) != len(ids):
            issues.append("Two machines share the same id.")
        if not self.machines:
            issues.append("Add at least one machine.")
        if not self.lines or not any(line.products for line in self.lines):
            issues.append("Add at least one production line with a product.")
        for m in self.machines:
            kind = LIBRARY.get(m.type)
            if kind is None:
                issues.append(f"{m.name}: unknown machine type '{m.type}'.")
                continue
            if kind.serves == "line" and m.line not in lines:
                issues.append(f"{m.name} needs a production line.")
            if m.rated_kw <= 0:
                issues.append(f"{m.name} needs a rated power above 0 kW.")
        if not any(LIBRARY.get(m.type) and LIBRARY[m.type].serves == "line" for m in self.machines):
            issues.append("Add at least one production machine (press, CNC, oven...).")
        if self.days < 14:
            issues.append("Simulate at least 14 days, so there's enough to learn from and test on.")
        return issues


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "machine"


# --------------------------------------------------------------------------- simulating a spec


def shift_of(spec: PlantSpec, weekday: int) -> tuple[int, int] | None:
    if weekday < 5:
        return spec.shift_start, spec.shift_end
    if weekday == 5 and spec.saturday_end > spec.shift_start:
        return spec.shift_start, spec.saturday_end
    return None


def plan_batches(spec: PlantSpec, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for day in range(spec.days):
        date = START + pd.Timedelta(days=day)
        hours = shift_of(spec, date.dayofweek)
        if hours is None:
            continue
        shift_end = date + pd.Timedelta(hours=hours[1])
        for line in spec.lines:
            if not line.products or rng.random() < 0.08:  # occasional maintenance day
                continue
            t = date + pd.Timedelta(hours=hours[0], minutes=int(rng.integers(30, 50)))
            while t + pd.Timedelta(minutes=60) < shift_end:
                end = min(t + pd.Timedelta(minutes=int(rng.integers(80, 240))), shift_end)
                product = line.products[int(rng.integers(len(line.products)))]
                rows.append({"line": line.id, "product": product.name, "start": t, "end": end,
                             "units": int(product.rate * (end - t) / pd.Timedelta(hours=1) * rng.uniform(0.85, 1.05))})
                t = end + pd.Timedelta(minutes=int(rng.integers(15, 45)))
    log = pd.DataFrame(rows, columns=["line", "product", "start", "end", "units"]).sort_values("start")
    log = log.reset_index(drop=True)
    log.insert(0, "batch_id", [f"B{i:04d}" for i in range(1, len(log) + 1)])
    return log


@dataclass
class LineArrays:
    active: np.ndarray
    load: np.ndarray       # product load relative to the heaviest product on the line (0..1)
    cycle: np.ndarray      # minutes per unit
    elapsed: np.ndarray    # minutes since the batch started, -1 while idle


def line_arrays(spec: PlantSpec, log: pd.DataFrame, index: pd.DatetimeIndex) -> dict[str, LineArrays]:
    arrays = {}
    for line in spec.lines:
        heaviest = max((p.load for p in line.products), default=1.0)
        products = {p.name: p for p in line.products}
        n = len(index)
        a = LineArrays(np.zeros(n, bool), np.zeros(n), np.zeros(n), np.full(n, -1.0))
        for batch in log[log["line"] == line.id].itertuples():
            i, j = index.searchsorted(batch.start), index.searchsorted(batch.end)
            product = products[batch.product]
            a.active[i:j] = True
            a.load[i:j] = product.load / heaviest
            a.cycle[i:j] = 60 / max(product.rate, 1e-6)
            a.elapsed[i:j] = np.arange(j - i)
        arrays[line.id] = a
    return arrays


def simulate_plant(spec: PlantSpec) -> dict[str, pd.DataFrame]:
    """Minute-by-minute power for every machine in the spec, plus the main meter and production log."""
    rng = np.random.default_rng(spec.seed)
    n = spec.days * 24 * 60
    index = pd.date_range(START, periods=n, freq="1min", name="timestamp")
    log = plan_batches(spec, rng)
    lines = line_arrays(spec, log, index)

    hour = index.hour + index.minute / 60
    starts = np.array([(shift_of(spec, d) or (0, 0))[0] for d in range(7)])[index.dayofweek]
    ends = np.array([(shift_of(spec, d) or (0, 0))[1] for d in range(7)])[index.dayofweek]
    in_shift = (hour >= starts) & (hour < ends)
    shift_minute = np.where(in_shift, (hour - starts) * 60, -1)
    days = (index.normalize() - index[0].normalize()).days
    weather = np.cumsum(rng.normal(0, 0.06, spec.days + 1))
    ambient = np.clip(0.5 + 0.3 * np.sin(2 * np.pi * (hour - 9) / 24) + weather[days], 0, 1)
    any_active = np.mean([a.active for a in lines.values()], axis=0) if lines else np.zeros(n)
    fault_from = START + pd.Timedelta(days=spec.fault.start_day) if spec.fault else None

    power = {}
    no_fault = np.zeros(n)
    for m in spec.machines:
        kind = LIBRARY[m.type]
        line = lines.get(m.line)
        faulty = fault_from is not None and spec.fault.machine == m.id
        draw = MACHINE_BEHAVIOUR[m.type](
            n=n, rng=rng, kw=m.rated_kw, line=line, in_shift=in_shift, shift_minute=shift_minute,
            ambient=ambient, any_active=any_active, lines=lines,
            fault=(index >= fault_from).astype(float) if faulty else no_fault,
        )
        if kind.serves == "line" and line is None:
            draw = np.zeros(n)
        power[m.id] = np.clip(draw + rng.normal(0, 0.02 * m.rated_kw, n) * (draw > 0.05 * m.rated_kw), 0, None)

    machines = pd.DataFrame(power, index=index)
    total = machines.sum(axis=1)
    meter = total + unmetered_load(n, rng, level=0.03 * float(total.mean())) + rng.normal(0, 0.3, n)
    return {
        "meter": meter.rename("power_kw").round(3).to_frame(),
        "submeters": machines.round(3),
        "production_log": log,
        "machines": pd.DataFrame([{"id": m.id, "name": m.name, "line": m.line, "kind": LIBRARY[m.type].label}
                                  for m in spec.machines]),
    }


def unmetered_load(n: int, rng: np.random.Generator, level: float) -> np.ndarray:
    """Small loads nobody listed (sockets, a fridge, a charger): wanders around `level`, never drifts away."""
    walk = np.empty(n)
    walk[0] = 0.0
    shocks = rng.normal(0, 0.05 * level + 0.05, n)
    for t in range(1, n):
        walk[t] = 0.98 * walk[t - 1] + shocks[t]
    return np.clip(level + walk, 0, None)


# --------------------------------------------------------------------------- how each type draws power


def _press(n, rng, kw, line, in_shift, shift_minute, **_):
    p = np.where(in_shift, 0.3 * kw, 0.01 * kw)
    p = np.where(in_shift & (shift_minute < 35), 1.0 * kw, p)
    if line is not None:
        purge = np.where(line.elapsed < 10, 1.15, 1.0)
        p = np.where(line.active, kw * (0.4 + 0.5 * line.load) * purge, p)
    return p


def _cnc(n, rng, kw, line, in_shift, **_):
    p = np.where(in_shift, 0.15 * kw, 0.02 * kw)
    if line is not None:
        cycle = np.maximum(line.cycle, 1e-9)
        cutting = np.where(((line.elapsed % cycle) / cycle) < 0.7, 1.0, 0.25)
        p = np.where(line.active, kw * (0.2 + 0.8 * line.load * cutting), p)
    return p


def _conveyor(n, rng, kw, line, in_shift, **_):
    p = np.where(in_shift, 0.1 * kw, 0.0)
    return np.where(line.active, 0.9 * kw, p) if line is not None else p


def _mixer(n, rng, kw, line, in_shift, **_):
    p = np.where(in_shift, 0.05 * kw, 0.0)
    if line is None:
        return p
    bursts = rng.random(n) < 0.55
    return np.where(line.active, np.where(bursts, kw * (0.5 + 0.5 * line.load), 0.15 * kw), p)


def _welder(n, rng, kw, line, in_shift, **_):
    p = np.where(in_shift, 0.08 * kw, 0.0)
    if line is None:
        return p
    arcs = rng.random(n) < 0.35
    return np.where(line.active, np.where(arcs, kw * (0.6 + 0.4 * line.load), 0.1 * kw), p)


def _thermo_heater(n, rng, kw, line, in_shift, fault, **_):
    demand = np.where(in_shift, 0.2, 0.0) + (0.45 * line.active * line.load if line is not None else 0) + 0.2 * fault
    return kw * thermostat(demand, rng, step=0.10) + 0.04 * kw * in_shift


def _batch_oven(n, rng, kw, line, in_shift, **_):
    if line is None:
        return np.where(in_shift, 0.01 * kw, 0.0)
    ramp = line.active & (line.elapsed < 25)
    hold = 0.85 * kw * thermostat(np.where(line.active & ~ramp, 0.3 + 0.15 * line.load, 0.0), rng, step=0.2)
    fans = np.where(line.active, 0.07 * kw, np.where(in_shift, 0.01 * kw, 0.0))
    return fans + np.where(ramp, 0.93 * kw, hold)


def _parts_washer(n, rng, kw, line, in_shift, **_):
    active = line.active if line is not None else np.zeros(n, bool)
    tank = 0.4 * kw * thermostat(np.where(in_shift, 0.35, 0.0) + 0.1 * active, rng, step=0.15)
    spray = 0.6 * kw * np.sqrt(line.load) * (active & (line.elapsed % 20 < 5)) if line is not None else 0
    return tank + spray + 0.03 * kw * in_shift


def _compressor(n, rng, kw, line, in_shift, any_active, fault, **_):
    air = np.where(in_shift, 0.08, 0.02) + 0.5 * any_active + 0.15 * fault  # busy lines and leaks need more air
    loaded = thermostat(np.clip(air, 0, 1), rng, step=0.25)
    last = np.maximum.accumulate(np.where(loaded, np.arange(n), -10**9))
    return np.where(loaded, kw, np.where(np.arange(n) - last < 10, 0.35 * kw, 0.02 * kw))


def _chiller(n, rng, kw, line, in_shift, ambient, any_active, fault, **_):
    cooling = np.where(in_shift, 0.15 + 0.25 * ambient, 0.03) + 0.35 * any_active + 0.2 * fault
    return 0.08 * kw + 0.92 * kw * thermostat(np.clip(cooling, 0, 1), rng, step=0.12)


def _cold_room(n, rng, kw, line, in_shift, ambient, fault, **_):
    demand = 0.3 + 0.25 * ambient + 0.05 * in_shift + 0.25 * fault  # e.g. a door left open
    return 0.05 * kw + 0.95 * kw * thermostat(np.clip(demand, 0, 1), rng, step=0.08)


def _pump(n, rng, kw, line, in_shift, **_):
    return np.where(in_shift, 0.85 * kw, 0.05 * kw)


def _hvac(n, rng, kw, line, in_shift, ambient, **_):
    return np.where(in_shift, kw * (0.3 + 0.6 * ambient), 0.15 * kw * ambient)


def _lighting(n, rng, kw, line, in_shift, **_):
    return np.where(in_shift, kw, 0.15 * kw)


def _office(n, rng, kw, line, in_shift, **_):
    wander = np.empty(n)
    wander[0] = 0.0
    shocks = rng.normal(0, 0.04, n)
    for t in range(1, n):
        wander[t] = 0.97 * wander[t - 1] + shocks[t]
    return np.clip(np.where(in_shift, 0.6 * kw, 0.2 * kw) + wander * kw, 0.05 * kw, None)


def left_on(behaviour):
    """For machines without a thermostat, a fault means being left running after the shift."""
    def wrapped(n, rng, kw, in_shift, fault, **kwargs):
        return behaviour(n=n, rng=rng, kw=kw, in_shift=in_shift, **kwargs) + 0.3 * kw * fault * ~in_shift
    return wrapped


MACHINE_BEHAVIOUR = {
    "injection_press": left_on(_press), "cnc_machine": left_on(_cnc), "conveyor": left_on(_conveyor),
    "mixer": left_on(_mixer), "welder": left_on(_welder), "thermo_heater": _thermo_heater,
    "batch_oven": left_on(_batch_oven), "parts_washer": left_on(_parts_washer), "air_compressor": _compressor,
    "chiller": _chiller, "cold_room": _cold_room, "pump": left_on(_pump), "hvac": left_on(_hvac),
    "lighting": left_on(_lighting), "office": left_on(_office),
}
assert set(MACHINE_BEHAVIOUR) == set(LIBRARY), "every machine type needs a behaviour"


# --------------------------------------------------------------------------- templates and storage


def load_spec(path: Path) -> PlantSpec:
    return PlantSpec.model_validate_json(path.read_text(encoding="utf-8"))


def save_spec(spec: PlantSpec, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(spec.model_dump_json(indent=1), encoding="utf-8")


def write_tables(tables: dict[str, pd.DataFrame], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    tables["meter"].to_csv(out / "meter.csv")
    tables["submeters"].to_csv(out / "submeters.csv")
    tables["production_log"].to_csv(out / "production_log.csv", index=False)
    tables["machines"].to_csv(out / "machines.csv", index=False)
