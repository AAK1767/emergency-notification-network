#!/usr/bin/env python3
"""
run_demo.py — Quick D1 demo using Mininet xterm.

This script is run from the Mininet CLI or by running the topology standalone.
Use the Mininet CLI to launch processes on individual hosts.

Usage (from Mininet CLI):
    mininet> xterm hServer hC1 hC2 hC3

Then in each xterm:
    hServer:  python3 server/server.py
    hC1:      python3 client/client.py --id C1 --server 10.0.0.1 --port 9999
    hC2:      python3 client/client.py --id C2 --server 10.0.0.1 --port 9999
    hC3:      python3 client/client.py --id C3 --server 10.0.0.1 --port 9999

On hServer terminal, type an alert message and press Enter:
    FIRE IN BLOCK A

To test retransmission, stop a client while sending alerts.

This script automates the demo by running commands on Mininet hosts.
"""

import sys
import os
import time
import argparse
import shlex
from functools import partial

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import Link, TCLink
from mininet.log import setLogLevel
from mininet.cli import CLI

from topology.topo import EmergencyTopo


def run_demo(use_tc=True):
    setLogLevel("info")

    topo = EmergencyTopo(bw=10, delay="5ms", use_tc=use_tc)
    net = Mininet(
        topo=topo,
        controller=RemoteController("c0", ip="127.0.0.1", port=6653),
        switch=partial(OVSSwitch, stp=True, failMode="standalone"),
        link=TCLink if use_tc else Link,
        autoSetMacs=True,
    )
    # Give Mininet hosts a management/NAT path to the WSL or VM namespace,
    # where Ryu's REST API listens on port 8080.
    net.addNAT(name="nat0", ip="10.0.0.254/24", connect=True)
    net.start()
    net.get("nat0").configDefault()

    print("\n" + "=" * 60)
    print("  EMERGENCY NOTIFICATION NETWORK — D1 DEMO")
    print("=" * 60)

    hServer = net.get("hServer")
    hC1 = net.get("hC1")
    hC2 = net.get("hC2")
    hC3 = net.get("hC3")

    project_dir = os.path.dirname(os.path.abspath(__file__))
    # Use the same interpreter for Mininet hosts as for this launcher. This
    # keeps the system-Python demo consistent when started with sudo python3.
    python = sys.executable
    log_dir = f"/tmp/emergency-notification-demo-{os.getpid()}"
    os.makedirs(log_dir, exist_ok=True)
    server_log = os.path.join(log_dir, "server.log")
    client_logs = {
        "C1": os.path.join(log_dir, "C1.log"),
        "C2": os.path.join(log_dir, "C2.log"),
        "C3": os.path.join(log_dir, "C3.log"),
    }
    python_cmd = shlex.quote(python)
    project_cmd = shlex.quote(project_dir)

    # 0) Verify connectivity after allowing Mininet/OVS startup to converge
    print("\n[DEMO] Running pingall (startup convergence)...")
    net.pingAll()
    print("\n[DEMO] Running pingall again (final connectivity check)...")
    net.pingAll()

    # 1) Start the server
    print("\n[DEMO] Starting Emergency Server on hServer (10.0.0.1)...")
    hServer.cmd(
        f"cd {project_cmd} && {python_cmd} server/server.py "
        f"> {shlex.quote(server_log)} 2>&1 &"
    )
    time.sleep(2)

    # 2) Start clients
    print("[DEMO] Starting subscribers C1, C2, C3...")
    hC1.cmd(
        f"cd {project_cmd} && {python_cmd} client/client.py "
        f"--id C1 --server 10.0.0.1 --port 9999 "
        f"> {shlex.quote(client_logs['C1'])} 2>&1 &"
    )
    time.sleep(0.5)
    hC2.cmd(
        f"cd {project_cmd} && {python_cmd} client/client.py "
        f"--id C2 --server 10.0.0.1 --port 9999 "
        f"> {shlex.quote(client_logs['C2'])} 2>&1 &"
    )
    time.sleep(0.5)
    hC3.cmd(
        f"cd {project_cmd} && {python_cmd} client/client.py "
        f"--id C3 --server 10.0.0.1 --port 9999 "
        f"> {shlex.quote(client_logs['C3'])} 2>&1 &"
    )
    time.sleep(2)

    # 3) Send an alert from the admin host
    print("\n[DEMO] Sending emergency alert...")
    hAdmin = net.get("hAdmin")
    hAdmin.cmd(
        f"cd {project_cmd} && {python_cmd} server/send_alert.py "
        '--server 10.0.0.1 --port 9999 -m "FIRE IN BLOCK A" &'
    )
    time.sleep(1)

    print("\n[DEMO] Delivery logs:")
    print(hServer.cmd(f"cat {shlex.quote(server_log)}"))
    for client, host in (("C1", hC1), ("C2", hC2), ("C3", hC3)):
        print(f"[DEMO] {client} log:")
        print(host.cmd(f"cat {shlex.quote(client_logs[client])}"))

    # For the demo we drop into the Mininet CLI so the user can interact
    print("\n[DEMO] System ready. Use the Mininet CLI to interact.")
    print(f"[DEMO] Logs are also available under {log_dir}.")
    print("[DEMO] To send an alert, type at the hServer xterm.")
    print("[DEMO] To verify flows: sh ovs-ofctl dump-flows s1 -O OpenFlow13\n")

    CLI(net)
    net.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Emergency D1 demo")
    parser.add_argument(
        "--no-tc",
        action="store_true",
        help="Use plain links without bandwidth/delay qdiscs (for WSL kernels)",
    )
    run_demo(use_tc=not parser.parse_args().no_tc)
