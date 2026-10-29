#!/usr/bin/env python3
"""Install two simple OVS queues on every port of selected switches."""

import argparse
import shutil
import subprocess
import sys


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True)


def configure_port(port, link_rate, emergency_rate):
    queue = run(
        "ovs-vsctl", "--", "--id=@q1", "create", "Queue",
        f"other-config:min-rate={emergency_rate}",
        f"other-config:max-rate={link_rate}",
    ).stdout.strip()
    qos = run(
        "ovs-vsctl", "--", "--id=@qos", "create", "QoS",
        "type=linux-htb", f"other-config:max-rate={link_rate}",
        f"queues:1={queue}",
    ).stdout.strip()
    run("ovs-vsctl", "set", "Port", port, f"qos={qos}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--switches", nargs="+", default=["s1", "s2", "s3", "s4"])
    parser.add_argument("--link-rate-mbps", type=int, default=10)
    parser.add_argument("--emergency-rate-mbps", type=int, default=8)
    args = parser.parse_args()

    if shutil.which("ovs-vsctl") is None:
        parser.error("ovs-vsctl was not found; run this on the Mininet/OVS host")
    if not 0 < args.emergency_rate_mbps <= args.link_rate_mbps:
        parser.error("emergency rate must be greater than 0 and at most the link rate")

    link_rate = args.link_rate_mbps * 1_000_000
    emergency_rate = args.emergency_rate_mbps * 1_000_000
    configured = 0
    for switch in args.switches:
        try:
            ports = run("ovs-vsctl", "list-ports", switch).stdout.splitlines()
            for port in ports:
                configure_port(port, link_rate, emergency_rate)
                configured += 1
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"QoS setup failed for {switch}: {exc}", file=sys.stderr)
            return 1
    print(f"Configured emergency queue 1 on {configured} OVS ports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
