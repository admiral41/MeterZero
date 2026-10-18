"""The web API, end to end: plants, views, prices, paperwork, AI streaming, and designing + training a plant."""
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fake_gemini import FakeClient


@pytest.fixture
def client(small_factory, tmp_path, monkeypatch):
    data_dir, results_path, _ = small_factory
    monkeypatch.setenv("METERZERO_DATA", str(data_dir))
    monkeypatch.setenv("METERZERO_RESULTS", str(results_path))
    monkeypatch.setenv("METERZERO_RUNS", str(tmp_path / "runs"))
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI"):
        monkeypatch.delenv(name, raising=False)

    import server.ai
    import server.common
    import server.main
    import server.paperwork
    import server.prices
    from server.store import Store

    store = Store(tmp_path)
    for module in (server.main, server.ai, server.common, server.paperwork, server.prices):
        monkeypatch.setattr(module, "store", store)
    return TestClient(server.main.app)


def test_library_templates_and_plants(client):
    assert len(client.get("/api/library").json()) == 15
    assert {t["id"] for t in client.get("/api/templates").json()} == {"demo", "bakery", "garment", "blank"}
    plants = client.get("/api/plants").json()
    assert plants[0]["id"] == "demo" and plants[0]["trained"] and plants[0]["reference"]


def test_demo_plant_views(client):
    plant = client.get("/api/plants/demo").json()
    assert len(plant["machines"]) == 8 and plant["machines"][-1]["id"] == "other"

    timeline = client.get(f"/api/plants/demo/timeline?day={plant['default_day']}").json()
    assert len(timeline["meter"]) == timeline["minutes"] == 1440
    assert set(timeline["machines"]) == {m["id"] for m in plant["machines"]}
    series = timeline["machines"]["press"]
    assert len(series["kw"]) == len(series["state"]) == 1440
    assert all(lo <= kw + 0.06 and kw <= hi + 0.06 for lo, kw, hi in zip(series["low"], series["kw"], series["high"]))

    overview = client.get("/api/plants/demo/overview").json()
    assert overview["kpis"]["energy_kwh"] > 0 and overview["actions"] and overview["morning"]["lines"]
    assert overview["flows"]["nodes"][0]["name"] == "Main meter"

    accuracy = client.get("/api/plants/demo/accuracy").json()
    assert accuracy["ladder"][-1]["accuracy"] > accuracy["ladder"][0]["accuracy"]
    assert client.get("/api/plants/demo/shift?line=C&hours=-1").json()["batches_moved"] > 0
    assert client.get("/api/plants/demo/repairs").json()[0]["machine"] == "compressor"
    assert client.get("/api/plants/demo/explain/press").json()["final_kwh"] > 0
    assert client.get("/api/plants/demo/explain/teleporter").status_code == 404


def test_prices_and_the_bill(client):
    prices = client.get("/api/plants/demo/prices").json()
    bands = [[b["name"], b["start"], b["end"], b["price"] * 2] for b in prices["bands"]]
    doubled = client.put("/api/plants/demo/prices", json={"bands": bands, "demand_charge": 8, "currency": "$"}).json()
    assert doubled["bands"][0]["price"] == pytest.approx(prices["bands"][0]["price"] * 2)

    sample = json.loads((Path(__file__).resolve().parents[1] / "samples" / "bills" / "np" / "2026-03.json").read_text(encoding="utf-8"))
    split = client.post("/api/plants/demo/bill?apply=true", json=sample).json()
    assert split["applied"] and sum(m["amount"] for m in split["by_machine"]) == pytest.approx(sample["total_amount"], rel=1e-3)
    assert client.get("/api/plants/demo/prices").json()["currency"] == "Rs "
    assert {f["kind"] for f in split["findings"]} >= {"arithmetic", "demand"}


def test_bill_history_finds_the_planted_problems(client):
    months = {m["month"]: m for m in client.get("/api/plants/demo/bills").json()}
    assert len(months) == 6
    assert months["2026-02"]["problems"] and months["2026-02"]["recoverable"] > 0   # overcharged
    assert months["2025-12"]["problems"]                                           # power factor surcharge
    assert not months["2026-03"]["problems"]
    assert client.get(months["2026-02"]["image"]).status_code == 200


def test_regions_set_prices_currency_and_bills(client):
    assert {r["id"] for r in client.get("/api/regions").json()} >= {"us", "ca", "jp", "np"}
    prices = client.put("/api/plants/demo/region", json={"region": "jp"}).json()
    assert prices["currency"] == "¥" and prices["region"] == "jp" and prices["demand_unit"] == "kW"
    bills = client.get("/api/plants/demo/bills").json()
    assert bills[0]["reading"]["currency"] == "JPY" and "/jp/" in bills[0]["image"]
    client.put("/api/plants/demo/region", json={"region": "us"})
    assert client.put("/api/plants/demo/region", json={"region": "mars"}).status_code == 404


def test_logbook_page_is_checked_and_priced(client, small_factory):
    _, _, results = small_factory
    day = results.log[results.log["start"] >= results.meter.index[0]].iloc[0]["start"].normalize()
    batches = results.log[(results.log["start"] >= day) & (results.log["start"] < day + __import__("pandas").Timedelta(days=1))]
    rows = [{"line": b.line, "product": b.product.lower(), "start": f"{b.start:%H:%M}", "end": f"{b.end:%H:%M}", "units": int(b.units)}
            for b in batches.itertuples()]
    out = client.post("/api/plants/demo/logbook", json={"date": f"{day:%Y-%m-%d}", "rows": rows}).json()
    assert out["problems"] == [] and len(out["batches"]) == len(rows)
    assert all(c["read from photo"] == "✓" for c in out["check"])


def test_ai_needs_a_key_then_streams_steps(client, small_factory, monkeypatch):
    assert client.post("/api/plants/demo/ai/review").status_code == 401
    import server.ai

    _, _, results = small_factory
    monkeypatch.setattr(server.ai, "make_client", lambda key=None: FakeClient(results.log))
    response = client.post("/api/plants/demo/ai/review", headers={"X-Gemini-Key": "fake"})
    events = [json.loads(line[5:]) for line in response.text.splitlines() if line.startswith("data:")]
    assert any(e["type"] == "step" for e in events)
    done = events[-1]
    assert done["type"] == "done" and done["findings"]["findings"]
    assert client.get("/api/plants/demo/ai/saved/investigation").status_code == 200

    answer = client.post("/api/plants/demo/ai/ask", json={"question": "Anything wasting energy?"}, headers={"X-Gemini-Key": "fake"})
    assert '"type": "done"' in answer.text


def test_reference_plant_is_read_only(client):
    spec = client.get("/api/plants/demo/spec").json()["spec"]
    assert client.put("/api/plants/demo/spec", json=spec).status_code == 403
    assert client.delete("/api/plants/demo").status_code == 403


def test_design_simulate_and_train_a_new_plant(client):
    created = client.post("/api/plants", json={"template": "garment", "name": "Test garments"}).json()
    plant_id = created["id"]
    assert client.get(f"/api/plants/{plant_id}").status_code == 409  # not trained yet

    created["days"] = 16
    created["machines"] = created["machines"][:6]
    saved = client.put(f"/api/plants/{plant_id}/spec", json=created).json()
    assert saved["problems"] == []

    client.post(f"/api/plants/{plant_id}/train")
    deadline = time.time() + 240
    while time.time() < deadline:
        job = client.get(f"/api/plants/{plant_id}/job").json()
        if job["state"] in ("done", "failed"):
            break
        time.sleep(1)
    assert job["state"] == "done", job
    plant = client.get(f"/api/plants/{plant_id}").json()
    assert len(plant["machines"]) == 7  # six machines + unmetered loads
    assert client.get(f"/api/plants/{plant_id}/timeline").status_code == 200
    assert client.delete(f"/api/plants/{plant_id}").status_code == 200
