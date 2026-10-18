# Demo script (about 5 minutes)

**The story:** a small factory pays one electricity bill and keeps its production log on paper.
MeterZero shows where every kilowatt-hour goes, finds a leak worth about $369 a month, catches an
overcharged bill, and Ask MeterZero (powered by Gemini) explains what to do first. Every figure can be
checked against hidden meters.

## Before you start (once)

```powershell
cd backend
..\.venv\Scripts\python -m meterzero all
..\.venv\Scripts\python scripts\make_samples.py
..\.venv\Scripts\python scripts\make_bills.py
copy .env.example .env        # put GEMINI_API_KEY in it
..\.venv\Scripts\python scripts\live_gemini_check.py
```

The live check runs every AI feature for real and **saves the results**. If the Wi-Fi fails during the
demo, the app shows those saved results, labelled with their date.

---

### 1 · Overview (~40 s)
> "One electricity bill, about $6,800 a month. MeterZero tells you where it went and what to do first."

Scroll to **Where every kWh went** (3D flow). Hover the red **Made nothing** stream:
> "12% of the electricity made nothing: warm-ups, idling, nights."

### 2 · Digital twin (~60 s), the wow moment
Press **Play**. Orbit with the mouse, fly with W A S D.
> "A simulation of the plant. Energy flows along the cables to each machine; lights follow the shift.
> Every machine's figure is worked out from that one main meter."

Click **Night** in the timeline. The air compressor turns red in the hierarchy; click it, press **F** to focus.
> "At night everything is off except the compressor, drawing far more than it should. That's a leak."

Press **Ask MeterZero about this**:
> "The assistant knows what I'm looking at. It checks the numbers and says what maintenance should look at."

### 3 · Bills & paperwork (~60 s)
> "Every factory has this bill. MeterZero checked six months of them."

Click **February**: *Energy charges don't add up*. Click **December**: *Low power factor surcharge*.
Press **Read this photo with Gemini** to show the photo being read live.
> "Gemini reads the bill; MeterZero checks every line against what it measured. Then it splits the bill
> by machine and by product."

### 4 · Find savings (~50 s)
Press **Run a Gemini review** and let the steps scroll by:
> "Gemini works like an energy auditor: it checks prices, prices the repair, tries schedule changes and
> drops the ones that clash with production."

### 5 · What if (~20 s)
> "Start line C two hours earlier: about $84 a month, no clashes, but five batches need someone in earlier."

### 6 · Accuracy (~15 s)
> "88% accurate from one meter, 95% with two extra meters, and it says which two."

### 7 · Plant designer (optional, ~30 s)
All plants → create a **Bakery** → Simulate & train. "Any plant, learned in about a minute."

---

## Likely questions

* **Is the data real?** A simulated plant with hidden meters on every machine, so every claim can be
  checked. Real data loads from four CSV files.
* **Why not let the AI work out the numbers?** A language model can't reliably split one electrical
  signal into machines; that needs a model checked against meters. Gemini reads paper, plans the review,
  compares options and explains, using only MeterZero's numbers.
* **Are the prices real?** Typical time-of-use rates for the chosen region (Settings → Region). Loading a
  real bill switches the app to its exact prices.
