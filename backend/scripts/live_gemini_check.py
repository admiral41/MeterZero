"""Run the app's AI features against the real Gemini API and write a report.

    .venv\\Scripts\\python backend\\scripts\\live_gemini_check.py

Needs a key: put GEMINI_API_KEY in backend/.env (see .env.example) or set it in the shell.
It calls the same API routes the web app uses (chat, the weekly review, the summary, reading a
bill photo), checks every number in each answer against the figures the tools returned, and
writes artifacts/live_gemini_report.md. Successful runs are also saved as recordings
(artifacts/gemini_runs), which the app shows when Gemini isn't connected.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from meterzero.agent import DEFAULT_MODEL, gemini_model, gemini_status, make_client  # noqa: E402
from server.env import load_env  # noqa: E402
from server.main import app  # noqa: E402

REPORT = ROOT / "artifacts" / "live_gemini_report.md"
PLANT = "demo"
NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*\.?\d*")


def numbers_in(value) -> list[float]:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    found = []
    for match in NUMBER.findall(text):
        try:
            found.append(float(match.replace(",", "")))
        except ValueError:
            pass
    return found


def traceable(number: float, sources: list[float]) -> bool:
    """True if the number matches a tool output, allowing for the rounding people do."""
    return any(source and abs(number - source) <= max(0.02 * abs(source), 0.51 if abs(source) >= 1 else 0.005)
               for source in sources)


def unverified_numbers(text: str, calls: list[dict]) -> tuple[int, list[float]]:
    sources = [n for call in calls for n in numbers_in(call["result"]) + numbers_in(call["args"])]
    claimed = [n for n in numbers_in(text) if not (1990 <= n <= 2100) and abs(n) >= 1]
    return len(claimed), [n for n in claimed if not traceable(n, sources)]


def streamed(client: TestClient, path: str, body: dict | None = None) -> dict:
    """POST to a streaming AI route and return its final event."""
    final: dict = {}
    with client.stream("POST", path, json=body or {}) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith("data: "):
                event = json.loads(line[6:])
                if event["type"] in ("done", "error"):
                    final = event
    if final.get("type") != "done":
        raise RuntimeError(final.get("text", "no answer"))
    return final


class Report:
    def __init__(self):
        self.sections: list[str] = []
        self.failures: list[str] = []

    def step(self, title: str, action) -> None:
        start = time.time()
        try:
            body = action()
        except Exception as error:
            self.failures.append(title)
            self.sections.append(f"## ❌ {title}\n\n{type(error).__name__}: {str(error)[:600]}\n")
            print(f"  ❌ {title}: {error}")
            return
        seconds = time.time() - start
        self.sections.append(f"## ✅ {title}\n\n*{seconds:.1f} s*\n\n{body}\n")
        print(f"  ✅ {title} ({seconds:.1f}s)")
        self.write()

    def write(self, note: str = "") -> None:
        REPORT.parent.mkdir(exist_ok=True)
        header = (f"# Live Gemini check\n\nModel: `{os.environ.get('GEMINI_MODEL', DEFAULT_MODEL)}`  \n"
                  f"Run at: {time.strftime('%Y-%m-%d %H:%M')}  \n"
                  f"Result: {note or ('all passed' if not self.failures else 'FAILED: ' + ', '.join(self.failures))}\n\n"
                  "Numbers marked *not found in tool output* may be legitimately derived (e.g. a yearly figure "
                  "from a monthly one); review them by hand.\n\n")
        REPORT.write_text(header + "\n---\n\n".join(self.sections), encoding="utf-8")


def answer(result: dict) -> str:
    text, calls = result.get("text") or result.get("report", ""), result.get("tool_calls", [])
    claimed, unverified = unverified_numbers(text, calls)
    tools = "\n".join(f"- `{c['tool']}({json.dumps(c['args'], default=str)})`" for c in calls) or "- (none)"
    return (f"{len(calls)} tool call(s), {claimed} numbers in the answer, not found in tool output: {unverified or 'none'}\n\n"
            f"**Tools called**\n{tools}\n\n**Answer**\n\n{text}")


def main() -> int:
    load_env()
    report = Report()
    if gemini_status() is not None:
        report.write("NOT RUN. No GEMINI_API_KEY in backend/.env or the shell (or Vertex AI settings).")
        print("No Gemini key. Put GEMINI_API_KEY in backend/.env (copy .env.example), then run again.")
        return 2

    print(f"Running live checks against {gemini_model()}...")

    def connect():
        gemini = make_client()  # keep a reference: the SDK closes a client once it's garbage-collected
        reply = gemini.models.generate_content(model=gemini_model(), contents="Reply with the word OK.")
        if not reply.text:
            raise RuntimeError("Gemini returned an empty reply")
        return "Gemini answered."

    report.step("Connecting to Gemini", connect)
    if report.failures:
        report.write()
        return 1

    with TestClient(app) as client:
        base = f"/api/plants/{PLANT}"
        report.step("Chat: what to fix first", lambda: answer(streamed(
            client, f"{base}/ai/ask", {"question": "What should I fix first this week, and what is it worth?", "conversation": "live-check"})))
        report.step("Chat: a follow-up in the same conversation", lambda: answer(streamed(
            client, f"{base}/ai/ask", {"question": "And what would that save in a year?", "conversation": "live-check"})))
        report.step("Weekly review (the auditor)", lambda: answer(streamed(client, f"{base}/ai/review")))
        report.step("Weekly summary", lambda: answer(streamed(client, f"{base}/ai/briefing")))

        def read_bill():
            month = client.get(f"{base}/bills").json()[-2]   # February: the overcharged one
            response = client.post(f"{base}/ai/read/bill", data={"sample": "true", "month": month["month"]})
            response.raise_for_status()
            read, truth = response.json(), month["reading"]
            fields = ["kwh_total", "kwh_peak", "energy_charge", "demand_charge", "total_amount", "max_demand_kva"]
            wrong = [f for f in fields if abs(float(read.get(f, 0)) - float(truth[f])) > max(1, 0.005 * float(truth[f]))]
            if wrong:
                raise RuntimeError(f"Read these fields wrong: {', '.join(wrong)}")
            return f"All {len(fields)} key fields of the {month['month']} bill read correctly."

        report.step("Reading a bill photo", read_bill)

    report.write()
    print(f"\nReport: {REPORT}")
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
