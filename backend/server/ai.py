"""Gemini endpoints: chat, the savings review, the weekly summary (streamed step by step), and reading photos.

Steps stream to the browser as server-sent events while Gemini works, so the UI can
show each lookup as it happens. The API key comes from the X-Gemini-Key header (the
user's own key, kept in their browser) or from the server's environment.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
from collections import OrderedDict
from pathlib import Path

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from meterzero import bill as bill_module
from meterzero import replay, vision
from meterzero.agent import EnergyAgent, gemini_model, gemini_status, make_client, transcribe
from meterzero.data import OTHER

from .store import store

router = APIRouter(prefix="/api")
log = logging.getLogger("meterzero")
SAMPLES = Path(__file__).resolve().parents[1] / "samples"
SAMPLE_FILES = {"logbook": "logbook_2026-03-26.jpg", "bill": "bills/us/2026-03.jpg", "nameplate": "nameplate_compressor.jpg"}
CHATS: "OrderedDict[str, EnergyAgent]" = OrderedDict()


def client_for(key: str | None):
    if key:
        return make_client(key)
    if gemini_status() is None:
        return make_client()
    raise HTTPException(401, "Connect Gemini: add your API key in Settings.")


def plant_results(plant_id: str):
    results = store.results(plant_id)
    if results is None:
        raise HTTPException(409, "This plant hasn't been trained yet.")
    return results


def describe(call: dict, names: dict[str, str]) -> str:
    """One plain sentence per lookup, with the headline number it returned."""
    tool, args, out = call["tool"], call["args"], call["result"]
    args = args if isinstance(args, dict) else {}
    if isinstance(out, dict) and "error" in out:
        return f"Tried something that didn't fit: {out['error']}"
    m = names.get(str(args.get("machine", "")), str(args.get("machine", ""))).lower()
    simple = {
        "get_factory_overview": lambda: f"Read the plant overview: {out['site_energy_kwh']:,.0f} kWh this week",
        "get_anomalies": lambda: f"Checked for waste: {len(out.get('alerts', []))} found",
        "get_sensor_recommendation": lambda: f"Checked where MeterZero is least sure: the {out['ranking'][0]['machine'].lower()}",
        "get_product_energy": lambda: f"Looked up energy per item for {len(out['products'])} product(s)",
        "get_morning_check": lambda: f"Read the morning check for {out['day']}",
        "get_energy_without_production": lambda: f"Looked at energy that made nothing: {out['total_kwh']:,.0f} kWh",
        "estimate_cost_and_carbon": lambda: "Worked out cost and CO2 per machine and per item",
        "get_overnight_history": lambda: f"Looked at the {out['machine'].lower()} night by night",
        "get_hourly_profile": lambda: f"Looked at the {out['machine'].lower()} hour by hour",
        "get_daily_profile": lambda: f"Looked at {out['day']}: {out['site_kwh']:,.0f} kWh",
        "get_tariff_breakdown": lambda: "Checked the electricity prices and when energy is bought",
        "plan_fix_waste": lambda: f"Priced a repair: saves {out['currency']}{out['monthly_saving']:,.0f} a month",
        "plan_schedule_shift": lambda: (f"Tried “{out['change']}”: {'saves' if out['monthly_saving'] >= 0 else 'costs'} "
                                        f"{out['currency']}{abs(out['monthly_saving']):,.0f} a month"
                                        + (" (clashes with other batches)" if out["batches_that_clash_with_other_batches"] else "")),
    }
    try:
        return simple[tool]() if tool in simple else f"Looked at the {m or tool.replace('_', ' ')}"
    except (KeyError, IndexError, TypeError):
        return f"Used {tool.replace('_', ' ')}"


def explain_failure(error: Exception) -> str:
    """Gemini's errors in plain words for the browser; the full error goes to the server log."""
    log.warning("Gemini call failed: %s", error)
    text = str(error)
    if "API key not valid" in text or "UNAUTHENTICATED" in text or "PERMISSION_DENIED" in text:
        return "Gemini rejected the API key. Check GEMINI_API_KEY in backend/.env, or the key in Settings."
    if "RESOURCE_EXHAUSTED" in text or "429" in text:
        return "Gemini's usage limit was reached. Wait a minute and try again."
    if "NOT_FOUND" in text and "model" in text.lower():
        return "That Gemini model isn't available to this key. Set GEMINI_MODEL in backend/.env."
    return f"Gemini couldn't finish ({type(error).__name__})."


def stream(work, names: dict[str, str]):
    """Run `work(on_tool_call)` in a thread and stream each tool call, then the result, as SSE."""
    events: queue.Queue = queue.Queue()

    def on_call(call: dict) -> None:
        events.put({"type": "step", "text": describe(call, names), "tool": call["tool"]})

    def run() -> None:
        try:
            events.put({"type": "done", **work(on_call)})
        except Exception as error:
            events.put({"type": "error", "text": explain_failure(error)})
        events.put(None)

    threading.Thread(target=run, daemon=True).start()

    def generate():
        while (event := events.get()) is not None:
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def names_for(results) -> dict[str, str]:
    names = dict(zip(results.machines["id"], results.machines["name"]))
    names[OTHER] = "Other loads"
    return names


@router.get("/ai/status")
def status(x_gemini_key: str | None = Header(default=None)):
    connected = bool(x_gemini_key) or gemini_status() is None
    return {"connected": connected, "model": gemini_model(), "source": "your key" if x_gemini_key else "server"}


@router.post("/plants/{plant_id}/ai/ask")
def ask(plant_id: str, body: dict, x_gemini_key: str | None = Header(default=None)):
    results = plant_results(plant_id)
    client = client_for(x_gemini_key)
    conversation = f"{plant_id}:{body.get('conversation', 'default')}"
    agent = CHATS.get(conversation)
    if agent is None:
        agent = EnergyAgent(results, client=client, tariff=store.tariff(plant_id))
        CHATS[conversation] = agent
        while len(CHATS) > 50:
            CHATS.popitem(last=False)

    def work(on_call):
        agent.on_tool_call = on_call
        reply = agent.ask(body["question"])
        return {"text": reply.text, "tool_calls": reply.tool_calls}

    return stream(work, names_for(results))


@router.post("/plants/{plant_id}/ai/review")
def review(plant_id: str, x_gemini_key: str | None = Header(default=None)):
    results = plant_results(plant_id)
    client = client_for(x_gemini_key)

    def work(on_call):
        agent = EnergyAgent(results, client=client, tariff=store.tariff(plant_id), on_tool_call=on_call, max_tool_calls=25)
        found = agent.investigate()
        payload = {"report": found.report, "findings": found.findings.model_dump(), "tool_calls": found.tool_calls}
        replay.save(f"{plant_id}/investigation", payload, gemini_model())
        return payload

    return stream(work, names_for(results))


@router.post("/plants/{plant_id}/ai/briefing")
def briefing(plant_id: str, x_gemini_key: str | None = Header(default=None)):
    results = plant_results(plant_id)
    client = client_for(x_gemini_key)

    def work(on_call):
        agent = EnergyAgent(results, client=client, tariff=store.tariff(plant_id), on_tool_call=on_call, max_tool_calls=15)
        reply = agent.briefing()
        payload = {"text": reply.text, "tool_calls": reply.tool_calls}
        replay.save(f"{plant_id}/briefing", payload, gemini_model())
        return payload

    return stream(work, names_for(results))


@router.get("/plants/{plant_id}/ai/saved/{kind}")
def saved(plant_id: str, kind: str):
    record = replay.load(f"{plant_id}/{kind}")
    if record is None:
        raise HTTPException(404, "Nothing saved yet.")
    return record


@router.post("/plants/{plant_id}/ai/read/{kind}")
async def read(plant_id: str, kind: str, file: UploadFile | None = File(default=None), sample: bool = Form(default=False),
               month: str = Form(default=""), x_gemini_key: str | None = Header(default=None)):
    if kind not in SAMPLE_FILES:
        raise HTTPException(404, f"Can't read '{kind}'.")
    if sample and kind == "bill" and month:
        path = SAMPLES / "bills" / store.tariff(plant_id).region / f"{month}.jpg"
        if not path.is_file():
            raise HTTPException(404, "No sample bill for that month.")
        image, mime = path.read_bytes(), "image/jpeg"
    elif sample:
        image, mime = (SAMPLES / SAMPLE_FILES[kind]).read_bytes(), "image/jpeg"
    elif file is not None:
        image, mime = await file.read(), file.content_type or "image/jpeg"
    else:
        raise HTTPException(400, "Send a photo, or ask for the sample.")
    client = client_for(x_gemini_key)
    try:
        if kind == "logbook":
            results = plant_results(plant_id)
            parsed = vision.read_logbook(client, image, mime, vision.product_catalog(results.log))
        elif kind == "bill":
            parsed = bill_module.read_bill(client, image, mime)
        else:
            parsed = vision.read_nameplate(client, image, mime)
    except Exception as error:
        raise HTTPException(502, f"Couldn't read the photo. {explain_failure(error)}")
    payload = parsed.model_dump()
    replay.save(f"{plant_id}/{kind}", payload, gemini_model())
    return payload


@router.post("/ai/transcribe")
async def hear(audio: UploadFile = File(...), x_gemini_key: str | None = Header(default=None)):
    client = client_for(x_gemini_key)
    try:
        return {"text": transcribe(client, await audio.read(), audio.content_type or "audio/webm")}
    except Exception as error:
        raise HTTPException(502, f"Couldn't make out the question. {explain_failure(error)}")


@router.get("/samples/{kind}")
def sample(kind: str):
    from fastapi.responses import FileResponse

    if kind not in SAMPLE_FILES:
        raise HTTPException(404, "No such sample.")
    return FileResponse(SAMPLES / SAMPLE_FILES[kind], media_type="image/jpeg")



@router.get("/samples/bills/{region}/{month}.jpg")
def sample_bill(region: str, month: str):
    from fastapi.responses import FileResponse

    path = SAMPLES / "bills" / region / f"{month}.jpg"
    if not (path.is_file() and path.parent.parent == SAMPLES / "bills"):
        raise HTTPException(404, "No such sample bill.")
    return FileResponse(path, media_type="image/jpeg")
