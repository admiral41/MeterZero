"""Plants, their trained results, their prices, and background training jobs.

The reference demo plant uses the validated data in data/ and artifacts/results.pkl.
Every other plant is a spec the user designed (or copied from a template); training it
simulates its data and runs the same MeterZero pipeline, in a background thread.
"""
from __future__ import annotations

import json
import os
import threading
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path

from meterzero import pipeline, plant, simulate, templates
from meterzero.savings import Tariff

ROOT = Path(os.environ.get("METERZERO_HOME", Path(__file__).resolve().parents[1]))


@dataclass
class Job:
    plant_id: str
    state: str = "queued"          # queued → simulating → training → done | failed
    steps: list[str] = field(default_factory=list)
    started: float = field(default_factory=time.time)
    finished: float | None = None
    error: str = ""

    def say(self, message: str) -> None:
        self.steps.append(message)


class Store:
    def __init__(self, root: Path = ROOT):
        self.root = root
        self.plants_dir = root / "plants"
        self.artifacts = root / "artifacts"
        self._results: dict[str, tuple[float, pipeline.Results]] = {}
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    # -- specs -------------------------------------------------------------------

    def spec_path(self, plant_id: str) -> Path:
        return self.plants_dir / f"{plant_id}.json"

    def results_path(self, plant_id: str) -> Path:
        if plant_id == templates.DEMO_ID:
            return Path(os.environ.get("METERZERO_RESULTS", self.artifacts / "results.pkl"))
        return self.artifacts / "plants" / plant_id / "results.pkl"

    def data_dir(self, plant_id: str) -> Path:
        if plant_id == templates.DEMO_ID:
            return Path(os.environ.get("METERZERO_DATA", self.root / "data"))
        return self.artifacts / "plants" / plant_id / "data"

    def spec(self, plant_id: str) -> plant.PlantSpec:
        if plant_id == templates.DEMO_ID:
            return templates.demo()
        path = self.spec_path(plant_id)
        if not path.exists():
            raise KeyError(plant_id)
        return plant.load_spec(path)

    def list(self) -> list[dict]:
        ids = [templates.DEMO_ID] + sorted(p.stem for p in self.plants_dir.glob("*.json") if not p.stem.endswith(".tariff"))
        rows = []
        for plant_id in ids:
            try:
                spec = self.spec(plant_id)
            except Exception:
                continue
            job = self.jobs.get(plant_id)
            rows.append({
                "id": spec.id, "name": spec.name, "description": spec.description, "reference": spec.reference,
                "machines": len(spec.machines), "lines": len(spec.lines),
                "trained": self.results_path(plant_id).exists(),
                "training": bool(job and job.state not in ("done", "failed")),
            })
        return rows

    def save(self, spec: plant.PlantSpec) -> plant.PlantSpec:
        if spec.id == templates.DEMO_ID:
            raise PermissionError("The reference demo plant can't be changed. Save it as a copy.")
        spec.reference = False
        plant.save_spec(spec, self.spec_path(spec.id))
        return spec

    def create(self, template: str, name: str) -> plant.PlantSpec:
        spec = templates.TEMPLATES[template]()
        spec.reference = False
        spec.name = name or spec.name
        base = plant.slug(spec.name)
        plant_id, n = base, 2
        while plant_id == templates.DEMO_ID or self.spec_path(plant_id).exists():
            plant_id, n = f"{base}_{n}", n + 1
        spec.id = plant_id
        return self.save(spec)

    def delete(self, plant_id: str) -> None:
        if plant_id == templates.DEMO_ID:
            raise PermissionError("The reference demo plant can't be deleted.")
        for path in (self.spec_path(plant_id), self.tariff_path(plant_id), self.results_path(plant_id)):
            path.unlink(missing_ok=True)
        self._results.pop(plant_id, None)

    # -- results -----------------------------------------------------------------

    def results(self, plant_id: str) -> pipeline.Results | None:
        path = self.results_path(plant_id)
        if not path.exists():
            if plant_id == templates.DEMO_ID:
                self._train_demo()
            else:
                return None
        mtime = path.stat().st_mtime
        cached = self._results.get(plant_id)
        if cached and cached[0] == mtime:
            return cached[1]
        with self._lock:
            results = pipeline.load(path)
            self._results[plant_id] = (mtime, results)
        return results

    def _train_demo(self) -> None:
        data = self.data_dir(templates.DEMO_ID)
        if not (data / "meter.csv").exists():
            simulate.write(simulate.simulate(), data)
        pipeline.save(pipeline.run(data, verbose=False), self.results_path(templates.DEMO_ID))

    # -- prices ------------------------------------------------------------------

    def tariff_path(self, plant_id: str) -> Path:
        return self.plants_dir / f"{plant_id}.tariff.json"

    def tariff(self, plant_id: str) -> Tariff:
        path = self.tariff_path(plant_id)
        if not path.exists():
            return Tariff()
        raw = json.loads(path.read_text(encoding="utf-8"))
        defaults = Tariff()
        return Tariff(bands=[tuple(b) for b in raw["bands"]], demand_charge=raw["demand_charge"], currency=raw["currency"],
                      region=raw.get("region", defaults.region), co2_kg_per_kwh=raw.get("co2_kg_per_kwh", defaults.co2_kg_per_kwh),
                      demand_unit=raw.get("demand_unit", defaults.demand_unit))

    def set_tariff(self, plant_id: str, tariff: Tariff) -> None:
        self.plants_dir.mkdir(parents=True, exist_ok=True)
        self.tariff_path(plant_id).write_text(json.dumps(asdict(tariff), indent=1), encoding="utf-8")

    # -- training ----------------------------------------------------------------

    def train(self, plant_id: str) -> Job:
        spec = self.spec(plant_id)
        problems = spec.problems()
        if problems:
            raise ValueError(" ".join(problems))
        current = self.jobs.get(plant_id)
        if current and current.state not in ("done", "failed"):
            return current
        job = Job(plant_id)
        self.jobs[plant_id] = job
        threading.Thread(target=self._run_job, args=(job, spec), daemon=True).start()
        return job

    def _run_job(self, job: Job, spec: plant.PlantSpec) -> None:
        try:
            job.state = "simulating"
            job.say(f"Simulating {spec.days} days of {len(spec.machines)} machines, minute by minute")
            data = self.data_dir(spec.id)
            if spec.reference:
                simulate.write(simulate.simulate(spec.days, spec.seed), data)
            else:
                plant.write_tables(plant.simulate_plant(spec), data)
            job.state = "training"
            results = pipeline.run(data, verbose=False, fast=True, progress=job.say)
            path = self.results_path(spec.id)
            path.parent.mkdir(parents=True, exist_ok=True)
            pipeline.save(results, path)
            job.say(f"Accuracy on days it never saw: {results.ladder['accuracy'].iloc[-1]:.0%}")
            job.state = "done"
        except Exception as error:  # report it in the UI instead of dying silently
            job.state = "failed"
            job.error = f"{type(error).__name__}: {error}"
            job.say(traceback.format_exc(limit=3))
        finally:
            job.finished = time.time()


store = Store()
