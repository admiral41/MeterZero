"""MeterZero API and web app.

    uvicorn server.main:app --reload            # API on :8000, serves the built web app from web/dist

During frontend development run `npm run dev` in web/ as well; Vite proxies /api here.
"""
from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from meterzero import replay, savings, templates
from meterzero.plant import LIBRARY, PlantSpec

from . import views
from .ai import router as ai_router
from .common import results_or_409
from .env import load_env
from .paperwork import router as paperwork_router
from .prices import router as prices_router
from .store import store

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Load the demo plant and work out its action list in the background, so the first page is quick."""
    def warm_up():
        try:
            results = store.results(templates.DEMO_ID)
            cached_actions(templates.DEMO_ID, results, store.tariff(templates.DEMO_ID))
        except Exception:
            pass  # the page will compute it on demand instead
    threading.Thread(target=warm_up, daemon=True).start()
    yield


load_env()
app = FastAPI(title="MeterZero", version="2.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=2000)
app.include_router(ai_router)
app.include_router(prices_router)
app.include_router(paperwork_router)
# The built React app: next to the backend in the container (static/), or in ../frontend/dist when developing.
_HERE = Path(__file__).resolve().parents[1]
WEB = next((p for p in (_HERE / "static", _HERE.parent / "frontend" / "dist") if p.exists()), _HERE / "static")




# --------------------------------------------------------------------------- plants and the designer


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/library")
def library():
    return [asdict(t) for t in LIBRARY.values()]


@app.get("/api/templates")
def template_list():
    return [{"id": key, "name": (s := make()).name, "description": s.description, "machines": len(s.machines)}
            for key, make in templates.TEMPLATES.items()]


@app.get("/api/plants")
def plants():
    return store.list()


class NewPlant(BaseModel):
    template: str = "blank"
    name: str = ""


@app.post("/api/plants")
def create(body: NewPlant):
    if body.template not in templates.TEMPLATES:
        raise HTTPException(400, "Unknown template.")
    return store.create(body.template, body.name).model_dump()


@app.get("/api/plants/{plant_id}/spec")
def get_spec(plant_id: str):
    try:
        spec = store.spec(plant_id)
    except KeyError:
        raise HTTPException(404, "No such plant.")
    return {"spec": spec.model_dump(), "problems": spec.problems()}


@app.put("/api/plants/{plant_id}/spec")
def put_spec(plant_id: str, body: dict):
    try:
        spec = PlantSpec.model_validate({**body, "id": plant_id})
        store.save(spec)
    except ValidationError as error:
        raise HTTPException(422, str(error))
    except PermissionError as error:
        raise HTTPException(403, str(error))
    return {"spec": spec.model_dump(), "problems": spec.problems()}


@app.delete("/api/plants/{plant_id}")
def delete(plant_id: str):
    try:
        store.delete(plant_id)
    except PermissionError as error:
        raise HTTPException(403, str(error))
    return {"deleted": plant_id}


@app.post("/api/plants/{plant_id}/train")
def train(plant_id: str):
    try:
        job = store.train(plant_id)
    except KeyError:
        raise HTTPException(404, "No such plant.")
    except ValueError as error:
        raise HTTPException(422, str(error))
    return asdict(job)


@app.get("/api/plants/{plant_id}/job")
def job(plant_id: str):
    current = store.jobs.get(plant_id)
    return asdict(current) if current else {"plant_id": plant_id, "state": "none", "steps": []}


# --------------------------------------------------------------------------- a trained plant


@app.get("/api/plants/{plant_id}")
def plant(plant_id: str):
    return views.plant_payload(results_or_409(plant_id), store.spec(plant_id))


@app.get("/api/plants/{plant_id}/timeline")
def timeline(plant_id: str, day: str | None = None):
    return views.timeline(results_or_409(plant_id), store.spec(plant_id), store.tariff(plant_id), day)


@app.get("/api/plants/{plant_id}/overview")
def overview(plant_id: str, day: str | None = None):
    results = results_or_409(plant_id)
    spec, tariff = store.spec(plant_id), store.tariff(plant_id)
    review = replay.load(f"{plant_id}/investigation")
    return {
        "name": spec.name, "kpis": views.kpis(results, tariff), "actions": cached_actions(plant_id, results, tariff),
        "morning": views.morning(results, tariff, day), "flows": views.flows(results, spec),
        "machines": views.machine_energy(results, spec), "repairs": views.repairs(results, tariff, spec),
        "review": review and {"headline": review["payload"]["findings"]["headline"], "recorded_at": review["recorded_at"]},
        "period": [f"{results.meter.index[0]:%Y-%m-%d}", f"{results.meter.index[-1]:%Y-%m-%d}"],
    }


_ACTIONS: dict[tuple, list] = {}


def cached_actions(plant_id: str, results, tariff: savings.Tariff) -> list[dict]:
    key = (plant_id, id(results), repr(tariff))
    if key not in _ACTIONS:
        _ACTIONS[key] = savings.top_actions(results, tariff)
    return _ACTIONS[key]


@app.get("/api/plants/{plant_id}/accuracy")
def accuracy(plant_id: str):
    return views.accuracy(results_or_409(plant_id), store.spec(plant_id))



@app.get("/api/plants/{plant_id}/shift")
def shift(plant_id: str, line: str, hours: float, product: str = ""):
    try:
        return views.shift(results_or_409(plant_id), store.tariff(plant_id), line, product, hours)
    except ValueError as error:
        raise HTTPException(422, str(error))


@app.get("/api/plants/{plant_id}/repairs")
def repairs(plant_id: str):
    return views.repairs(results_or_409(plant_id), store.tariff(plant_id), store.spec(plant_id))


@app.get("/api/plants/{plant_id}/overnight/{machine}")
def overnight(plant_id: str, machine: str):
    return views.overnight(results_or_409(plant_id), machine)


@app.get("/api/plants/{plant_id}/explain/{machine}")
def explain(plant_id: str, machine: str, day: str | None = None):
    results = results_or_409(plant_id)
    if machine not in results.estimate.columns:
        raise HTTPException(404, "No such machine.")
    return views.explain(results, machine, day)


# --------------------------------------------------------------------------- paperwork

# --------------------------------------------------------------------------- the web app


if WEB.exists():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        file = WEB / path
        return FileResponse(file if path and file.is_file() else WEB / "index.html")
