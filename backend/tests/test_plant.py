import numpy as np
import pytest

from meterzero import anomalies, plant, templates
from meterzero.plant import LIBRARY, MACHINE_BEHAVIOUR, MachineSpec


def test_every_machine_type_has_a_behaviour_and_draws_sensible_power():
    spec = templates.blank()
    spec.days = 14
    spec.machines = [MachineSpec(id=t.id, name=t.label, type=t.id,
                                 line="A" if t.serves == "line" else t.serves, rated_kw=t.default_kw, x=2 + i, y=3)
                     for i, t in enumerate(LIBRARY.values())]
    tables = plant.simulate_plant(spec)
    power = tables["submeters"]
    assert set(power.columns) == set(LIBRARY) == set(MACHINE_BEHAVIOUR)
    assert (power >= 0).all().all()
    for kind in LIBRARY.values():
        series = power[kind.id]
        assert series.max() > 0.2 * kind.default_kw, f"{kind.id} never gets going"
        assert series.max() < 1.6 * kind.default_kw, f"{kind.id} draws far above its rating"
    np.testing.assert_allclose(tables["meter"]["power_kw"].mean(), power.sum(axis=1).mean(), rtol=0.1)


@pytest.mark.parametrize("name", ["demo", "bakery", "garment"])
def test_templates_are_valid(name):
    spec = templates.TEMPLATES[name]()
    assert spec.problems() == []
    for m in spec.machines:
        assert 0 <= m.x <= spec.floor_w and 0 <= m.y <= spec.floor_d, f"{m.id} is off the floor"


def test_problems_are_reported_in_plain_words():
    spec = templates.blank()
    assert any("production machine" in p for p in spec.problems())
    spec.machines = [MachineSpec(id="oven", name="Oven", type="batch_oven", line="Z", rated_kw=40, x=1, y=1),
                     MachineSpec(id="oven", name="Oven 2", type="teleporter", line="A", rated_kw=0, x=1, y=1)]
    text = " ".join(spec.problems())
    assert "same id" in text and "needs a production line" in text and "unknown machine type" in text


def test_a_fault_raises_the_machines_night_time_draw():
    spec = templates.garment()
    spec.days = 16
    spec.fault.start_day = 10
    power = plant.simulate_plant(spec)["submeters"][["compressor"]]
    nights = anomalies.overnight_kw(power)["compressor"]
    before, after = nights.iloc[2:9].mean(), nights.iloc[11:].mean()
    assert after > before * 2


def test_simulated_plant_round_trips_through_the_loader(tmp_path):
    from meterzero.data import load_factory

    spec = templates.bakery()
    spec.days = 14
    plant.write_tables(plant.simulate_plant(spec), tmp_path)
    data = load_factory(tmp_path)
    assert data.machine_ids == [m.id for m in spec.machines]
    assert set(data.log["line"]) <= {line.id for line in spec.lines}
    assert set(data.machines.loc[data.machines["line"] == "building", "id"]) == {"hvac", "lights", "office"}
