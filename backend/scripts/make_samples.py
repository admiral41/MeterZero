"""Make demo photos: a handwritten logbook page and a machine nameplate (bills: make_bills.py).

    .venv\\Scripts\\python scripts\\make_samples.py

The logbook page is written from the simulated plant's real production log for one
test-week day, in a handwriting font, with the mess real logbooks have: abbreviations,
a crossed-out time, uneven writing, paper texture and a slight tilt. Because the rows
come from the system log, the app can score how well Gemini read the page.

The nameplate uses a made-up brand. You can also photograph a real page or plate.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "samples"
FONTS = Path("C:/Windows/Fonts")
DAY = pd.Timestamp("2026-03-26")

SCRAWL = {  # how a tired supervisor writes product names
    "Cap-S": ["Cap S", "cap-s", "Caps S"],
    "Housing-M": ["Housing M", "Hsg-M", "housing m"],
    "Crate-L": ["Crate L", "crate-L", "Crt L"],
    "Shaft": ["Shaft", "shaft", "Shft"],
    "Bracket": ["Bracket", "Brkt", "bracket"],
    "Flange": ["Flange", "flange", "Flng"],
    "Cure-Std": ["Cure std", "Cure-Std", "cure STD"],
    "Cure-Long": ["Cure long", "Cure-L0ng", "cure lng"],
}


def font(names: list[str], size: int) -> ImageFont.FreeTypeFont:
    for name in names:
        path = FONTS / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size)


def photo_finish(image: Image.Image, angle: float, seed: int) -> Image.Image:
    """Tilt, uneven lighting and sensor noise, so it looks photographed rather than rendered."""
    rng = np.random.default_rng(seed)
    image = image.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=(58, 52, 46))
    pixels = np.asarray(image).astype(float)
    h, w = pixels.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    light = 1.0 - 0.18 * (((xx - w * 0.35) / w) ** 2 + ((yy - h * 0.3) / h) ** 2)
    pixels = pixels * light[..., None] + rng.normal(0, 4, pixels.shape)
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))


def logbook_page(log: pd.DataFrame, seed: int = 4) -> Image.Image:
    rng = random.Random(seed)
    rows = log[(log["start"] >= DAY) & (log["start"] < DAY + pd.Timedelta(days=1))].sort_values(["line", "start"])
    width, height = 1400, 220 + 78 * (len(rows) + 2)
    page = Image.new("RGB", (width, height), (246, 241, 226))
    draw = ImageDraw.Draw(page)

    for y in range(200, height, 78):  # ruled lines and a red margin
        draw.line([(40, y), (width - 40, y)], fill=(170, 195, 220), width=2)
    draw.line([(120, 30), (120, height - 20)], fill=(222, 120, 120), width=3)

    printed = font(["arialbd.ttf", "arial.ttf"], 34)
    hand = font(["Inkfree.ttf", "segoepr.ttf", "comic.ttf"], 40)
    hand_big = font(["Inkfree.ttf", "segoepr.ttf", "comic.ttf"], 48)
    draw.text((150, 40), "PRODUCTION LOG", font=printed, fill=(40, 40, 60))
    draw.text((780, 40), "Date:", font=printed, fill=(40, 40, 60))
    draw.text((900, 30), DAY.strftime("%d/%m/%Y"), font=hand_big, fill=(20, 40, 120))

    columns = {"Line": 150, "Product": 290, "Start": 640, "End": 820, "Qty": 1000, "Sign": 1170}
    for title, x in columns.items():
        draw.text((x, 140), title, font=printed, fill=(40, 40, 60))

    crossed = rng.randrange(len(rows))
    for i, batch in enumerate(rows.itertuples()):
        y = 225 + 78 * i + rng.randint(-6, 6)
        ink = (rng.randint(10, 40), rng.randint(30, 60), rng.randint(110, 150))

        def write(x, text, jitter=8):
            draw.text((x + rng.randint(-jitter, jitter), y + rng.randint(-4, 4)), text, font=hand, fill=ink)

        write(columns["Line"] + 20, batch.line)
        write(columns["Product"], rng.choice(SCRAWL.get(batch.product, [batch.product])))
        start, end = batch.start.strftime("%H:%M"), batch.end.strftime("%H:%M")
        if i == crossed:  # a wrong start time, struck through, with the correction squeezed in
            wrong = (batch.start - pd.Timedelta(minutes=30)).strftime("%H:%M")
            x = columns["Start"]
            draw.text((x, y - 14), wrong, font=hand, fill=ink)
            draw.line([(x - 4, y + 10), (x + 105, y + 2)], fill=ink, width=4)
            draw.text((x + 18, y + 26), start, font=font(["Inkfree.ttf", "comic.ttf"], 30), fill=ink)
        else:
            write(columns["Start"], start)
        write(columns["End"], end)
        write(columns["Qty"], f"{batch.units}")
        write(columns["Sign"], rng.choice(["RK", "S.T", "rk", "AM"]))

    return photo_finish(page, angle=rng.uniform(-2.5, 2.5), seed=seed)


def nameplate() -> Image.Image:
    width, height = 1100, 640
    plate = Image.new("RGB", (width, height), (176, 180, 184))
    noise = np.random.default_rng(1).normal(0, 6, (height, width, 1))
    brushed = np.clip(np.asarray(plate).astype(float) + noise, 0, 255).astype(np.uint8)
    plate = Image.fromarray(brushed).filter(ImageFilter.BoxBlur(1))
    draw = ImageDraw.Draw(plate)
    draw.rounded_rectangle([20, 20, width - 20, height - 20], radius=24, outline=(70, 72, 76), width=6)
    for x, y in [(55, 55), (width - 55, 55), (55, height - 55), (width - 55, height - 55)]:
        draw.ellipse([x - 14, y - 14, x + 14, y + 14], fill=(120, 122, 126), outline=(60, 60, 60), width=2)

    title = font(["bahnschrift.ttf", "arialbd.ttf"], 52)
    label = font(["bahnschrift.ttf", "arial.ttf"], 34)
    value = font(["consolab.ttf", "arialbd.ttf"], 36)
    ink = (28, 30, 34)
    draw.text((90, 60), "MZ DEMO AIR SYSTEMS", font=title, fill=ink)
    draw.text((90, 125), "Rotary Screw Air Compressor", font=label, fill=ink)
    fields = [("Model", "SC-22 VS"), ("Serial No.", "2019-0457-11"), ("Motor", "22 kW / 30 HP"),
              ("Voltage", "400 V  3~  50 Hz"), ("Current", "41 A"), ("Max. pressure", "8 bar"),
              ("Year", "2019")]
    for i, (name, text) in enumerate(fields):
        y = 200 + 56 * i
        draw.text((90, y), name, font=label, fill=ink)
        draw.text((430, y), text, font=value, fill=ink)
    return photo_finish(plate, angle=-3.5, seed=7)


def main() -> int:
    log_path = ROOT / "data" / "production_log.csv"
    if not log_path.exists():
        print("Run `python -m meterzero all` first, so the logbook page matches the simulated plant.")
        return 1
    log = pd.read_csv(log_path, parse_dates=["start", "end"])
    OUT.mkdir(exist_ok=True)
    logbook_page(log).save(OUT / "logbook_2026-03-26.jpg", quality=88)
    nameplate().save(OUT / "nameplate_compressor.jpg", quality=88)
    print(f"Wrote the logbook page and nameplate to {OUT}. Bills: scripts/make_bills.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
