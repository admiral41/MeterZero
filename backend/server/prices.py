"""Prices and regions: the plant's time-of-use tariff, and presets for each country."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from meterzero import regions, savings

from . import views
from .common import results_or_409
from .store import store

router = APIRouter(prefix="/api")


@router.get("/plants/{plant_id}/prices")
def get_prices(plant_id: str):
    return views.prices(results_or_409(plant_id), store.tariff(plant_id))


class Prices(BaseModel):
    bands: list[tuple[str, int, int, float]]
    demand_charge: float
    currency: str


@router.put("/plants/{plant_id}/prices")
def put_prices(plant_id: str, body: Prices):
    current = store.tariff(plant_id)
    store.set_tariff(plant_id, savings.Tariff(bands=list(body.bands), demand_charge=body.demand_charge, currency=body.currency,
                                              region=current.region, co2_kg_per_kwh=current.co2_kg_per_kwh,
                                              demand_unit=current.demand_unit))
    return views.prices(results_or_409(plant_id), store.tariff(plant_id))


@router.get("/regions")
def list_regions():
    return regions.describe()


class RegionChoice(BaseModel):
    region: str


@router.put("/plants/{plant_id}/region")
def set_region(plant_id: str, body: RegionChoice):
    """Switch the plant to a region's typical prices, currency, demand unit and grid emissions."""
    if body.region not in regions.REGIONS:
        raise HTTPException(404, "No such region.")
    store.set_tariff(plant_id, regions.region(body.region).tariff())
    return views.prices(results_or_409(plant_id), store.tariff(plant_id))
