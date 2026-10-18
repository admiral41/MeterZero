"""Command line entry point.

    python -m meterzero simulate          write a simulated factory to data/
    python -m meterzero train             train, score, and save results for the app
    python -m meterzero all               both, in order
"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import pipeline, simulate

BACKEND = Path(__file__).resolve().parents[1]


def cmd_simulate(args) -> None:
    tables = simulate.simulate(args.days, args.seed)
    simulate.write(tables, args.data)
    print(f"Wrote {args.days} days of 1-minute data to {args.data}/ "
          f"({len(tables['machines'])} machines, {len(tables['production_log'])} batches)")


def cmd_train(args) -> None:
    results = pipeline.run(args.data)
    pipeline.save(results, args.out)
    pipeline.print_summary(results)
    print(f"\nSaved to {args.out}. Start the API with:  uvicorn server.main:app --reload --port 8000")


def main() -> None:
    parser = argparse.ArgumentParser(prog="meterzero")
    parser.add_argument("command", choices=["simulate", "train", "all"])
    parser.add_argument("--data", type=Path, default=BACKEND / "data")
    parser.add_argument("--out", type=Path, default=BACKEND / "artifacts" / "results.pkl")
    parser.add_argument("--days", type=int, default=28, help="simulate: days of data")
    parser.add_argument("--seed", type=int, default=7, help="simulate: random seed")
    args = parser.parse_args()

    if args.command in ("simulate", "all"):
        cmd_simulate(args)
    if args.command in ("train", "all"):
        cmd_train(args)


main()
