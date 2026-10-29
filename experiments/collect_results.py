#!/usr/bin/env python3
"""Collect a small, reproducible UDP latency/loss data set.

This local experiment uses the same protocol as the application and does not
require Mininet.  It is useful for validating the measurement pipeline before
running the full topology demo.
"""

import argparse
import csv
import os
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import protocol


def run_trial(count, drop_every):
    if count < 1:
        raise ValueError("count must be at least 1")
    if drop_every < 0:
        raise ValueError("drop_every cannot be negative")
    received = []
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    server.settimeout(1)
    client.settimeout(1)
    address = server.getsockname()

    def receive():
        for _ in range(count):
            try:
                data, peer = server.recvfrom(4096)
            except socket.timeout:
                return
            message = protocol.decode(data)
            if drop_every and message.seq % drop_every == 0:
                continue
            received.append((message.seq, time.time() - message.timestamp))
            server.sendto(protocol.make_ack(message.seq, "experiment"), peer)

    thread = threading.Thread(target=receive, daemon=True)
    thread.start()
    for seq in range(1, count + 1):
        client.sendto(protocol.make_alert(seq, "experiment"), address)
    thread.join(timeout=max(2, count * 0.1))
    client.close()
    server.close()
    return received


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="results/raw/d2_results.csv")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--drop-every", type=int, default=0)
    parser.add_argument("--condition", default="baseline")
    args = parser.parse_args()

    rows = run_trial(args.count, args.drop_every)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["condition", "sequence", "latency_ms", "delivered"])
        delivered = {seq: latency for seq, latency in rows}
        for seq in range(1, args.count + 1):
            writer.writerow([
                args.condition,
                seq,
                f"{delivered[seq] * 1000:.3f}" if seq in delivered else "",
                int(seq in delivered),
            ])
    print(f"Wrote {args.count} samples to {output}")


if __name__ == "__main__":
    main()
