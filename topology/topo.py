#!/usr/bin/env python3
"""
topo.py — Mininet topology for Emergency Notification Network.

Physical layout:
    hServer  ─── s1 ───┬── s2 ───┬─── s4 ─── hC1
                        │         │         └─── hC2
                        └── s3 ──-┘
                             │
                            hC3
    hAdmin ─── s1
    hNoise1 ── s2
    hNoise2 ── s3

Logical paths:
    Path A: s1 -> s2 -> s4
    Path B: s1 -> s3 -> s4       (alternate after s1-s2 link fails)

Usage:
    sudo mn --custom topology/topo.py --topo emergencytopo \
            --controller remote,ip=127.0.0.1,port=6653 \
            --switch ovsk,protocols=OpenFlow13 \
            --link tc
    or:
    sudo python3 topology/topo.py
    sudo python3 topology/topo.py --no-tc  # WSL kernels without traffic control
"""

import sys
import os
import time
import json
import argparse
from functools import partial

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import Link, TCLink
from mininet.log import setLogLevel
from mininet.cli import CLI


def load_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "config.json")
    with open(config_path) as f:
        return json.load(f)


class EmergencyTopo(Topo):
    """
    Redundant two-path topology for the Emergency Notification Network.

    Bandwidth and delay parameters are intentionally small to make
    congestion and latency effects observable.
    """

    def build(self, bw=10, delay="5ms", use_tc=True):
        """
        bw    : link bandwidth in Mbps
        delay : one-way propagation delay string (e.g. '5ms')
        """

        # ── Switches ─────────────────────────────────────────────────────
        s1 = self.addSwitch("s1", protocols="OpenFlow13", stp=True)
        s2 = self.addSwitch("s2", protocols="OpenFlow13", stp=True)
        s3 = self.addSwitch("s3", protocols="OpenFlow13", stp=True)
        s4 = self.addSwitch("s4", protocols="OpenFlow13", stp=True)

        # ── Hosts ─────────────────────────────────────────────────────────
        hServer = self.addHost("hServer", ip="10.0.0.1/24")
        hAdmin  = self.addHost("hAdmin",  ip="10.0.0.100/24")
        hC1     = self.addHost("hC1",     ip="10.0.0.2/24")
        hC2     = self.addHost("hC2",     ip="10.0.0.3/24")
        hC3     = self.addHost("hC3",     ip="10.0.0.4/24")
        hNoise1 = self.addHost("hNoise1", ip="10.0.0.11/24")
        hNoise2 = self.addHost("hNoise2", ip="10.0.0.12/24")

        link_opts = dict(bw=bw, delay=delay, use_htb=True) if use_tc else {}

        # ── Core links ────────────────────────────────────────────────────
        # Path A: s1 -> s2 -> s4
        self.addLink(s1, s2, **link_opts)
        self.addLink(s2, s4, **link_opts)

        # Path B: s1 -> s3 -> s4
        self.addLink(s1, s3, **link_opts)
        self.addLink(s3, s4, **link_opts)

        # ── Host links ────────────────────────────────────────────────────
        self.addLink(hServer, s1, **link_opts)
        self.addLink(hAdmin,  s1, **link_opts)
        self.addLink(hC1,     s4, **link_opts)
        self.addLink(hC2,     s4, **link_opts)
        self.addLink(hC3,     s3, **link_opts)

        # Noise hosts attached near bottleneck switches
        self.addLink(hNoise1, s2, **link_opts)
        self.addLink(hNoise2, s3, **link_opts)


topos = {"emergencytopo": EmergencyTopo}


# ─── Standalone runner ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run the Emergency Mininet topology")
    parser.add_argument(
        "--no-tc",
        action="store_true",
        help="Use plain links without bandwidth/delay qdiscs (for WSL kernels)",
    )
    parser.add_argument(
        "--pingall",
        action="store_true",
        help="Run Mininet pingall before opening the CLI",
    )
    args = parser.parse_args()

    setLogLevel("info")
    cfg = load_config()
    ctrl_cfg = cfg.get("controller", {})

    topo = EmergencyTopo(bw=10, delay="5ms", use_tc=not args.no_tc)
    net = Mininet(
        topo=topo,
        controller=RemoteController(
            "c0",
            ip=ctrl_cfg.get("ip", "127.0.0.1"),
            port=ctrl_cfg.get("openflow_port", 6653),
        ),
        switch=partial(OVSSwitch, stp=True, failMode="standalone"),
        link=Link if args.no_tc else TCLink,
        autoSetMacs=True,
    )
    net.start()

    print("\n=== Emergency Notification Network Topology started ===")
    print("hServer : 10.0.0.1")
    print("hAdmin  : 10.0.0.100")
    print("hC1     : 10.0.0.2")
    print("hC2     : 10.0.0.3")
    print("hC3     : 10.0.0.4")
    print("hNoise1 : 10.0.0.11")
    print("hNoise2 : 10.0.0.12")
    print("======================================================\n")
    print("Run 'pingall' at the Mininet prompt to verify connectivity.")
    print("Type 'exit' or Ctrl-D to stop.\n")

    print("== Waiting for controller connections ==")
    if not net.waitConnected(timeout=10):
        print("WARNING: One or more switches are not connected to the controller.")
    time.sleep(2)

    if args.pingall:
        print("== Running pingall ==")
        net.pingAll()
    else:
        print("== Skipping automatic pingall; CLI is ready ==")

    CLI(net)
    net.stop()


if __name__ == "__main__":
    main()
