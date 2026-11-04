#!/usr/bin/env python3
"""Measure emergency delivery through the live Mininet topology.

Run this from hAdmin after the topology, server, subscribers, and congestion
traffic are running. The server log supplies real ACK latency and delivery
evidence; no artificial packet loss is injected.
"""

import argparse
import csv
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import protocol


ALERT_RE = re.compile(r"ALERT seq=(\d+) sent to (\d+) subscribers")
ACK_RE = re.compile(
    r"ACK seq=(\d+) received from ([^ ]+) \(latency=([0-9.]+)ms\)"
)


def read_new_lines(path, offset):
    with open(path, encoding="utf-8") as handle:
        handle.seek(offset)
        lines = handle.readlines()
        return handle.tell(), lines


def wait_for_alert(path, offset, timeout):
    deadline = time.monotonic() + timeout
    lines = []
    while time.monotonic() < deadline:
        offset, new_lines = read_new_lines(path, offset)
        lines.extend(new_lines)
        for line in lines:
            match = ALERT_RE.search(line)
            if match:
                return offset, int(match.group(1)), int(match.group(2)), lines
        time.sleep(0.05)
    raise TimeoutError("The server did not log the alert before the timeout")


def collect_alert(
    sock, server, log_path, offset, message, expected, timeout
):
    sock.sendto(protocol.make_alert(0, message), server)
    offset, sequence, logged_expected, lines = wait_for_alert(
        log_path, offset, timeout
    )
    expected = logged_expected or expected
    deadline = time.monotonic() + timeout
    acks = {}
    # The alert and ACK lines can be written in one file read. Do not lose
    # those ACKs by starting the next read at the returned file offset.
    def collect_acks(candidate_lines):
        for line in candidate_lines:
            match = ACK_RE.search(line)
            if match and int(match.group(1)) == sequence:
                acks[match.group(2)] = float(match.group(3))

    collect_acks(lines)
    while time.monotonic() < deadline and len(acks) < expected:
        offset, new_lines = read_new_lines(log_path, offset)
        collect_acks(new_lines)
        time.sleep(0.05)
    latencies = list(acks.values())
    average = sum(latencies) / len(latencies) if latencies else None
    jitter = None
    if len(latencies) > 1:
        jitter = sum(
            abs(current - previous)
            for previous, current in zip(latencies, latencies[1:])
        ) / (len(latencies) - 1)
    delivered = len(latencies)
    return (
        offset,
        {
            "sequence": sequence,
            "latency_ms": average,
            "delivered": delivered,
            "expected_subscribers": expected,
            "delivery_percent": delivered * 100 / expected if expected else 0,
            "packet_loss_percent": (
                (expected - delivered) * 100 / expected if expected else 100
            ),
            "jitter_ms": jitter,
        },
    )


def configure_qos(enabled):
    command = [sys.executable, "experiments/setup_qos.py"]
    if not enabled:
        command.append("--disable")
    subprocess.run(command, check=True)


def run_condition(
    condition, count, sock, server, log_path, expected, timeout, message
):
    configure_qos(condition == "proposed")
    with open(log_path, encoding="utf-8") as handle:
        offset = handle.seek(0, 2)
    rows = []
    previous_latency = None
    for index in range(count):
        offset, row = collect_alert(
            sock,
            server,
            log_path,
            offset,
            f"{message} [{condition} {index + 1}]",
            expected,
            timeout,
        )
        if previous_latency is not None and row["latency_ms"] is not None:
            row["jitter_ms"] = abs(row["latency_ms"] - previous_latency)
        previous_latency = row["latency_ms"]
        row["condition"] = condition
        rows.append(row)
        time.sleep(0.2)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", choices=["baseline", "proposed"])
    parser.add_argument("--comparison", action="store_true")
    parser.add_argument("--server", default="10.0.0.1")
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument("--log", default="/tmp/gui-d2-server.log")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--expected-subscribers", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=4)
    parser.add_argument("--message", default="D2 EMERGENCY TEST")
    parser.add_argument("--output", default="results/raw/d2_mininet.csv")
    args = parser.parse_args()
    if not args.comparison and not args.condition:
        parser.error("--condition or --comparison is required")
    if args.count < 1 or args.expected_subscribers < 1:
        parser.error("count and expected subscribers must be positive")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        conditions = ["baseline", "proposed"] if args.comparison else [args.condition]
        rows = []
        for condition in conditions:
            rows.extend(
                run_condition(
                    condition,
                    args.count,
                    sock,
                    (args.server, args.port),
                    args.log,
                    args.expected_subscribers,
                    args.timeout,
                    args.message,
                )
            )
    finally:
        sock.close()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "condition",
        "sequence",
        "latency_ms",
        "delivered",
        "expected_subscribers",
        "delivery_percent",
        "packet_loss_percent",
        "jitter_ms",
    ]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} real Mininet samples to {output}")


if __name__ == "__main__":
    main()
