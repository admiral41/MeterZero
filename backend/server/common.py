"""Helpers shared by the API's route modules."""
from __future__ import annotations

from fastapi import HTTPException

from .store import store


def results_or_409(plant_id: str):
    try:
        store.spec(plant_id)
    except KeyError:
        raise HTTPException(404, "No such plant.")
    results = store.results(plant_id)
    if results is None:
        raise HTTPException(409, "This plant hasn't been simulated and trained yet.")
    return results
