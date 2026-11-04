#!/usr/bin/env python3
"""Plot real Mininet latency, delivery, loss, and jitter measurements."""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", nargs="+", default=["results/raw/d2_mininet.csv"])
    parser.add_argument("--output", default="results/graphs/d2_summary.png")
    args = parser.parse_args()

    data = pd.concat(
        (pd.read_csv(path) for path in args.input), ignore_index=True
    )
    summary = data.groupby("condition").agg(
        average_latency_ms=("latency_ms", "mean"),
        delivery_percent=("delivery_percent", "mean"),
        packet_loss_percent=("packet_loss_percent", "mean"),
        jitter_ms=("jitter_ms", "mean"),
    )
    axes = summary.plot.bar(
        subplots=True,
        layout=(2, 2),
        figsize=(10, 7),
        legend=False,
        title=[
            "Average alert delivery latency (ms)",
            "Packet delivery (%)",
            "Packet loss (%)",
            "Jitter (ms)",
        ],
        ylabel="Value",
    )
    axes[0, 0].figure.tight_layout()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    axes[0, 0].figure.savefig(output, dpi=150)
    print(f"Wrote graph to {output}")


if __name__ == "__main__":
    main()
