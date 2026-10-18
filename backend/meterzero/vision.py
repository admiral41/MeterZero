"""Gemini Vision onboarding: read the paper logbook and machine nameplates.

Many small plants keep the production log on paper. Without it MeterZero can't
say which product used the energy. So Gemini reads a photo of a logbook page into
structured rows. Each row is matched to the plant's known lines and products,
checked for impossible times, and then fed straight into the energy model.

Nameplates work the same way: a photo becomes rated power and machine type, which
we cross-check against the peak MeterZero actually sees for that machine.
"""
from __future__ import annotations

import difflib
import json

import pandas as pd
from pydantic import BaseModel, Field

from .agent import DEFAULT_MODEL, gemini_model


class LogbookRow(BaseModel):
    line: str = Field(description="Production line letter, e.g. A, B or C")
    product: str = Field(description="Product name as written")
    start: str = Field(description="Start time, 24h HH:MM")
    end: str = Field(description="End time, 24h HH:MM")
    units: int = Field(description="Units produced; 0 if not written")
    note: str = Field(default="", description="Anything unclear, crossed out or hard to read")


class LogbookPage(BaseModel):
    date: str = Field(description="Date of the page, YYYY-MM-DD")
    rows: list[LogbookRow]


class Nameplate(BaseModel):
    manufacturer: str = ""
    model: str = ""
    machine_type: str = Field(description="What the machine is, e.g. 'screw air compressor'")
    rated_power_kw: float = Field(description="Rated input power in kW; convert from HP or A×V if needed, 0 if absent")
    voltage_v: float = 0
    current_a: float = 0
    year: str = ""


LOGBOOK_PROMPT = """\
This is a photo of a handwritten factory production logbook page. Read every batch row.
Known lines and products: {catalog}
Use the closest known product name when the handwriting is a variant or abbreviation.
Times are 24-hour. If a value is crossed out, use the corrected value and mention it in `note`.
Do not invent rows that aren't on the page."""

NAMEPLATE_PROMPT = """\
This is a photo of an industrial machine's nameplate. Extract the fields.
If power is only given in HP, convert it (1 HP = 0.746 kW). If only volts and amps are given for a
3-phase machine, estimate kW = 1.732 × V × A × 0.85 / 1000."""


def _image_part(image: bytes, mime_type: str):
    from google.genai import types

    return types.Part.from_bytes(data=image, mime_type=mime_type)


def read_logbook(client, image: bytes, mime_type: str, catalog: dict[str, list[str]], model: str | None = None) -> LogbookPage:
    from google.genai import types

    response = client.models.generate_content(
        model=model or gemini_model(),
        contents=[_image_part(image, mime_type), LOGBOOK_PROMPT.format(catalog=json.dumps(catalog))],
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=LogbookPage, temperature=0
        ),
    )
    return response.parsed if isinstance(response.parsed, LogbookPage) else LogbookPage.model_validate_json(response.text)


def read_nameplate(client, image: bytes, mime_type: str, model: str | None = None) -> Nameplate:
    from google.genai import types

    response = client.models.generate_content(
        model=model or gemini_model(),
        contents=[_image_part(image, mime_type), NAMEPLATE_PROMPT],
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=Nameplate, temperature=0
        ),
    )
    return response.parsed if isinstance(response.parsed, Nameplate) else Nameplate.model_validate_json(response.text)


# --------------------------------------------------------------------------- turning a page into a log


def product_catalog(log: pd.DataFrame) -> dict[str, list[str]]:
    return {line: sorted(group["product"].unique()) for line, group in log.groupby("line")}


def _closest(value: str, options: list[str]) -> str | None:
    lowered = {o.lower(): o for o in options}
    match = difflib.get_close_matches(value.strip().lower(), list(lowered), n=1, cutoff=0.5)
    return lowered[match[0]] if match else None


def page_to_log(page: LogbookPage, catalog: dict[str, list[str]]) -> tuple[pd.DataFrame, list[str]]:
    """Validated production-log rows, plus human-readable problems with the ones we had to drop."""
    rows, problems = [], []
    day = pd.Timestamp(page.date).normalize()
    for i, row in enumerate(page.rows, start=1):
        line = row.line.strip().upper()[:1]
        if line not in catalog:
            problems.append(f"Row {i}: unknown line '{row.line}'")
            continue
        product = _closest(row.product, catalog[line])
        if product is None:
            problems.append(f"Row {i}: '{row.product}' isn't a known product on line {line}")
            continue
        try:
            start = day + pd.Timedelta(row.start + ":00")
            end = day + pd.Timedelta(row.end + ":00")
        except ValueError:
            problems.append(f"Row {i}: couldn't read the times '{row.start}'–'{row.end}'")
            continue
        if end <= start:
            problems.append(f"Row {i}: ends ({row.end}) before it starts ({row.start})")
            continue
        rows.append({"line": line, "product": product, "start": start, "end": end,
                     "units": max(int(row.units), 0), "note": row.note})

    log = pd.DataFrame(rows, columns=["line", "product", "start", "end", "units", "note"])
    for line, group in log.groupby("line"):
        ordered = group.sort_values("start")
        overlaps = (ordered["start"].iloc[1:].to_numpy() < ordered["end"].iloc[:-1].to_numpy()).sum()
        if overlaps:
            problems.append(f"Line {line}: {overlaps} batch(es) overlap the previous one; check the times")
    log.insert(0, "batch_id", [f"P{i:03d}" for i in range(1, len(log) + 1)])
    return log, problems


def compare_with_system_log(extracted: pd.DataFrame, system: pd.DataFrame, tolerance_min: int = 10) -> pd.DataFrame:
    """Match each system batch of that day to the photo rows: same line + product, times within tolerance."""
    if extracted.empty:
        return pd.DataFrame()
    day = extracted["start"].min().normalize()
    truth = system[(system["start"] >= day) & (system["start"] < day + pd.Timedelta(days=1))]
    tolerance = pd.Timedelta(minutes=tolerance_min)
    unused = set(extracted.index)
    rows = []
    for batch in truth.itertuples():
        match = None
        for i in sorted(unused):
            row = extracted.loc[i]
            if (row["line"] == batch.line and row["product"] == batch.product
                    and abs(row["start"] - batch.start) <= tolerance and abs(row["end"] - batch.end) <= tolerance):
                match = i
                break
        if match is not None:
            unused.discard(match)
        rows.append({
            "line": batch.line, "product": batch.product,
            "system start": batch.start.strftime("%H:%M"), "system end": batch.end.strftime("%H:%M"),
            "read from photo": "✓" if match is not None else "✗ missed",
            "units match": (match is not None and int(extracted.loc[match, "units"]) == int(batch.units)),
        })
    for i in sorted(unused):
        row = extracted.loc[i]
        rows.append({"line": row["line"], "product": row["product"], "system start": "-", "system end": "-",
                     "read from photo": f"✗ extra ({row['start']:%H:%M}-{row['end']:%H:%M})", "units match": False})
    return pd.DataFrame(rows)


def energy_from_page(results, extracted: pd.DataFrame) -> pd.DataFrame:
    """Swap the photographed day's batches into the log, re-run the model, and price every batch.

    Returns one row per batch read from the photo, with estimated kWh (± band) and kWh/unit.
    The true kWh over the same window comes from the hidden sub-meters, for checking only.
    """
    from .batches import batch_energy
    from .pipeline import reestimate

    day = extracted["start"].min().normalize()
    others = results.log[(results.log["start"] < day) | (results.log["start"] >= day + pd.Timedelta(days=1))]
    log = pd.concat([others, extracted.drop(columns=["note"], errors="ignore")]).sort_values("start")
    estimate, sd = reestimate(results, log)

    from .features import build_features

    features = build_features(results.meter, log).reindex(columns=results.feature_columns, fill_value=0.0)
    batches = batch_energy(extracted, features, results.machines, estimate, sd, results.truth)
    batches["sd kWh"] *= results.batch_sd_scale
    batches["kWh/unit"] = batches["estimated kWh"] / batches["units"].replace(0, float("nan"))
    return batches


def nameplate_check(plate: Nameplate, machine_peak_kw: float) -> str:
    if plate.rated_power_kw <= 0:
        return "No rated power on the plate, so there's nothing to cross-check."
    ratio = machine_peak_kw / plate.rated_power_kw
    if ratio > 1.15:
        return (f"⚠️ MeterZero sees peaks of {machine_peak_kw:.1f} kW, above the {plate.rated_power_kw:.1f} kW rating. "
                "Either the machine is overloaded or this load is mixed with another one.")
    if ratio < 0.3:
        return (f"MeterZero's peak ({machine_peak_kw:.1f} kW) is far below the {plate.rated_power_kw:.1f} kW rating: "
                "the machine is oversized for its job, or rarely runs at full load.")
    return f"✓ Consistent: rated {plate.rated_power_kw:.1f} kW, MeterZero sees peaks of {machine_peak_kw:.1f} kW ({ratio:.0%} of rating)."


__all__ = ["DEFAULT_MODEL", "LogbookPage", "LogbookRow", "Nameplate", "read_logbook", "read_nameplate",
           "product_catalog", "page_to_log", "compare_with_system_log", "nameplate_check"]
