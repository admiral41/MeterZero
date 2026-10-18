"""Ready-made plants to start from: the reference demo plant and two very different factories."""
from __future__ import annotations

from . import simulate
from .plant import Fault, Line, MachineSpec, PlantSpec, Product, Room

DEMO_ID = "demo"


def demo() -> PlantSpec:
    """The reference plant. Its data comes from simulate.py (the validated one); this adds the layout."""
    names = {m.id: m.name for m in simulate.MACHINES}
    place = {  # id: (type, line, rated kW, x, y)
        "press": ("injection_press", "A", 28, 10.5, 3.6), "dryer": ("thermo_heater", "A", 9, 14.2, 2.2),
        "cnc": ("cnc_machine", "B", 16, 19.6, 3.6), "washer": ("parts_washer", "B", 11, 23.6, 3.6),
        "oven": ("batch_oven", "C", 45, 10.0, 11.6), "compressor": ("air_compressor", "shared", 22, 17.0, 10.6),
        "chiller": ("chiller", "shared", 15, 19.3, 13.6),
    }
    return PlantSpec(
        id=DEMO_ID, name="Demo plastics & metal works", reference=True, days=28, panel_x=2.5, panel_y=3.0, cable_y=7.0,
        description="The reference plant: three production lines, shared compressed air and chilled water, "
                    "and a compressed-air leak that starts in the last week.",
        rooms=[Room(id="electrical", name="Electrical room", x=0, y=0, w=5, d=6),
               Room(id="moulding", name="Moulding hall", x=5, y=0, w=11, d=7),
               Room(id="machining", name="Machining hall", x=16, y=0, w=10, d=7),
               Room(id="storage", name="Storage", x=0, y=6, w=5, d=10),
               Room(id="finishing", name="Finishing", x=5, y=7, w=10, d=9),
               Room(id="utility", name="Utility room", x=15, y=7, w=6, d=9),
               Room(id="office", name="Office", x=21, y=7, w=5, d=9)],
        lines=[Line(id=line, name={"A": "Moulding", "B": "Machining", "C": "Finishing"}[line],
                    products=[Product(name=p, load=load, rate=rate) for p, (load, rate) in products.items()])
               for line, products in simulate.PRODUCTS.items()],
        machines=[MachineSpec(id=mid, name=names[mid], type=t, line=line, rated_kw=kw, x=x, y=y)
                  for mid, (t, line, kw, x, y) in place.items()],
        fault=Fault(machine="compressor", start_day=simulate.LEAK_DAY),
    )


def bakery() -> PlantSpec:
    return PlantSpec(
        id="bakery", name="Industrial bakery", panel_x=18.5, panel_y=9.2, cable_y=7.5,
        description="Bread and pastry lines with big ovens, a cold store that runs day and night, "
                    "and a cold-room door that starts getting left open.",
        floor_w=24, floor_d=16,
        rooms=[Room(id="mixing", name="Mixing room", x=0, y=0, w=8, d=7),
               Room(id="bake", name="Bake hall", x=8, y=0, w=16, d=8),
               Room(id="cold", name="Cold store", x=0, y=7, w=7, d=9),
               Room(id="packing", name="Packing", x=7, y=8, w=10, d=8),
               Room(id="utility", name="Utilities", x=17, y=8, w=4, d=8),
               Room(id="office", name="Office", x=21, y=8, w=3, d=8)],
        lines=[Line(id="B", name="Bread", products=[Product(name="White loaf", load=1.0, rate=420),
                                                    Product(name="Wholemeal loaf", load=1.25, rate=300)]),
               Line(id="P", name="Pastry", products=[Product(name="Croissant", load=1.0, rate=650),
                                                     Product(name="Celebration cake", load=1.5, rate=90)])],
        machines=[
            MachineSpec(id="dough_mixer", name="Dough mixer", type="mixer", line="B", rated_kw=15, x=3, y=2.5),
            MachineSpec(id="pastry_mixer", name="Pastry mixer", type="mixer", line="P", rated_kw=7.5, x=5.5, y=5),
            MachineSpec(id="proofer", name="Proofing cabinet", type="thermo_heater", line="B", rated_kw=8, x=10, y=2),
            MachineSpec(id="tunnel_oven", name="Tunnel oven", type="batch_oven", line="B", rated_kw=60, x=14.5, y=3.5),
            MachineSpec(id="deck_oven", name="Deck oven", type="batch_oven", line="P", rated_kw=36, x=20.5, y=3.5),
            MachineSpec(id="packing_line", name="Packing conveyor", type="conveyor", line="B", rated_kw=4, x=12, y=12),
            MachineSpec(id="cold_store", name="Cold store", type="cold_room", line="shared", rated_kw=12, x=3.5, y=11.5),
            MachineSpec(id="compressor", name="Air compressor", type="air_compressor", line="shared", rated_kw=7.5, x=19, y=10.5),
            MachineSpec(id="hvac", name="Air conditioning", type="hvac", line="building", rated_kw=10, x=19, y=14),
            MachineSpec(id="lights", name="Lighting", type="lighting", line="building", rated_kw=6, x=12, y=15),
            MachineSpec(id="office", name="Office", type="office", line="building", rated_kw=3, x=22.5, y=12),
        ],
        fault=Fault(machine="cold_store", start_day=21, kind="door left open"),
    )


def garment() -> PlantSpec:
    return PlantSpec(
        id="garment", name="Garment factory", panel_x=13.2, panel_y=9.0, cable_y=8.0,
        description="Cutting and two sewing lines, steam pressing, and lots of lighting and air conditioning. "
                    "A compressed-air leak starts in the last week.",
        floor_w=26, floor_d=16,
        rooms=[Room(id="cutting", name="Cutting room", x=0, y=0, w=8, d=8),
               Room(id="sewing", name="Sewing floor", x=8, y=0, w=18, d=8),
               Room(id="press", name="Pressing & finishing", x=0, y=8, w=12, d=8),
               Room(id="utility", name="Utilities", x=12, y=8, w=7, d=8),
               Room(id="office", name="Office", x=19, y=8, w=7, d=8)],
        lines=[Line(id="C", name="Cutting", products=[Product(name="Shirt panels", load=1.0, rate=500),
                                                      Product(name="Jacket panels", load=1.4, rate=250)]),
               Line(id="S1", name="Sewing line 1", products=[Product(name="Shirt", load=1.0, rate=90)]),
               Line(id="S2", name="Sewing line 2", products=[Product(name="Jacket", load=1.3, rate=35)])],
        machines=[
            MachineSpec(id="cutter", name="Automatic cutter", type="cnc_machine", line="C", rated_kw=12, x=4, y=4),
            MachineSpec(id="sewing_1", name="Sewing line 1", type="mixer", line="S1", rated_kw=9, x=13, y=2.5),
            MachineSpec(id="sewing_2", name="Sewing line 2", type="mixer", line="S2", rated_kw=9, x=13, y=5.5),
            MachineSpec(id="line_conveyor", name="Line conveyor", type="conveyor", line="S1", rated_kw=3, x=20, y=4),
            MachineSpec(id="steam_boiler", name="Steam boiler (irons)", type="thermo_heater", line="S2", rated_kw=24, x=4, y=12),
            MachineSpec(id="finishing", name="Finishing tunnel", type="batch_oven", line="S1", rated_kw=18, x=9, y=12),
            MachineSpec(id="compressor", name="Air compressor", type="air_compressor", line="shared", rated_kw=15, x=15.5, y=10.5),
            MachineSpec(id="hvac", name="Air conditioning", type="hvac", line="building", rated_kw=22, x=15.5, y=14),
            MachineSpec(id="lights", name="Lighting", type="lighting", line="building", rated_kw=12, x=20, y=1.5),
            MachineSpec(id="office", name="Office", type="office", line="building", rated_kw=4, x=22.5, y=12),
        ],
        fault=Fault(machine="compressor", start_day=22),
    )


def blank() -> PlantSpec:
    return PlantSpec(
        id="new_plant", name="My plant", description="Start from an empty floor.", panel_x=19.5, panel_y=1.5, cable_y=10.0,
        rooms=[Room(id="hall", name="Production hall", x=0, y=0, w=18, d=10),
               Room(id="utility", name="Utilities", x=18, y=0, w=8, d=10),
               Room(id="office", name="Office", x=18, y=10, w=8, d=6),
               Room(id="store", name="Store", x=0, y=10, w=18, d=6)],
        lines=[Line(id="A", name="Line A", products=[Product(name="Product 1", load=1.0, rate=100)])],
        machines=[],
    )


TEMPLATES = {"demo": demo, "bakery": bakery, "garment": garment, "blank": blank}
