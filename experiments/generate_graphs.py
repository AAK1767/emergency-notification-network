#!/usr/bin/env python3
"""Generate a latency/loss summary graph from collect_results.py output."""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", nargs="+", default=["results/raw/d2_results.csv"])
    parser.add_argument("--output", default="results/graphs/d2_summary.png")
    args = parser.parse_args()

    data = pd.concat((pd.read_csv(path) for path in args.input), ignore_index=True)
    summary = data.groupby("condition").agg(
        latency_ms=("latency_ms", "mean"),
        delivery_percent=("delivered", lambda values: values.mean() * 100),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    axes = summary.plot.bar(
        y=["latency_ms", "delivery_percent"],
        subplots=True,
        legend=False,
        title=["Mean latency (ms)", "Delivery rate (%)"],
    )
    axes[0].figure.tight_layout()
    axes[0].figure.savefig(output, dpi=150)
    print(f"Wrote graph to {output}")


if __name__ == "__main__":
    main()
