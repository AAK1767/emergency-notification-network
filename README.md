# Emergency Notification Network

A **UDP-based emergency notification system** deployed on **Mininet** with an **SDN controller (Ryu + OpenFlow 1.3)** that classifies, prioritizes, and dynamically manages emergency traffic.

## Problem Statement

During a network emergency, alert traffic must reach subscribers quickly — even when ordinary background traffic is saturating the network. This project implements an emergency notification service where the SDN controller recognizes emergency packets and gives them preferential forwarding.

## Architecture

```
Admin / CLI
     |
     v
 UDP Server          ──REST──>  Ryu SDN Controller
     |                              |
     v                         OpenFlow 1.3
 SDN-controlled network             |
     |                              v
  +--+--+--+                  OVS Switches
  |  |  |  |                  (s1, s2, s3, s4)
 C1 C2 C3 ...
```

### Topology

```
                      ┌── s2 ──┐
                      │        │
hServer ── s1 ────────┤        ├──── s4 ── hC1
             │        │        │      └── hC2
           hAdmin     └── s3 ──┘
                           │
                          hC3

Noise: hNoise1 @ s2, hNoise2 @ s3
```

Two redundant paths (s1→s2→s4 and s1→s3→s4) allow rerouting on link failure.

## Protocol

All messages use `|`-delimited format:

```
TYPE|SEQ|PRIORITY|TIMESTAMP|PAYLOAD
```

| Type | Example |
|---|---|
| `REGISTER` | `REGISTER\|0\|NORMAL\|1727670000.124\|C1` |
| `ALERT` | `ALERT\|42\|HIGH\|1727670004.531\|FIRE IN BLOCK A` |
| `ACK` | `ACK\|42\|HIGH\|1727670004.781\|C1` |
| `UNREGISTER` | `UNREGISTER\|0\|NORMAL\|1727670100.220\|C1` |
| `HEARTBEAT` | `HEARTBEAT\|0\|NORMAL\|1727670102.004\|C1` |

## Software Requirements

- Ubuntu 20.04+ (or Mininet-compatible Linux)
- Python 3.8-3.11 (Ryu is supported on Python 3.11)
- Mininet 2.3+
- Open vSwitch 2.13+
- Ryu SDN Framework 4.34+
- `iperf3` (for background traffic)

## Installation

```bash
# Clone the repository
git clone https://github.com/AAK1767/emergency-notification-network.git
cd emergency-notification-network

# Install Python dependencies
pip3 install -r requirements.txt

# Mininet & OVS are typically system packages
sudo apt-get install mininet openvswitch-switch
```

## Native Ubuntu Setup

For the full Mininet demo, use a native Ubuntu installation or an Ubuntu VM.
Use `uv` for Python 3.11 because some Ubuntu releases do not provide
`python3.11` through apt.

```bash
sudo apt update
sudo apt install -y git curl mininet openvswitch-switch iperf3

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.11

git clone https://github.com/AAK1767/emergency-notification-network.git
cd emergency-notification-network

# Install the Python dependencies needed by the controller and applications.
python3 -m pip install "pip==20.3.4" "setuptools==67.6.1" wheel "eventlet==0.33.3"
python3 -m pip install --no-build-isolation -r requirements.txt

python -c "import ryu; print('Ryu import OK')"
sudo service openvswitch-switch start
```

Open a second terminal and start the Ryu controller:

```bash
cd emergency-notification-network
python3 controller/run_ryu.py controller/ryu_app.py --observe-links --verbose
```

In a third terminal, start the Mininet topology:

```bash
cd emergency-notification-network
sudo mn -c
sudo python3 topology/topo.py
```

When `mininet>` appears, run the server, clients, and alert sender with
`python3`:

```text
mininet> hServer python3 server/server.py &
mininet> hC1 python3 client/client.py --id C1 --server 10.0.0.1 --port 9999 &
mininet> hC2 python3 client/client.py --id C2 --server 10.0.0.1 --port 9999 &
mininet> hC3 python3 client/client.py --id C3 --server 10.0.0.1 --port 9999 &
mininet> hAdmin python3 server/send_alert.py --server 10.0.0.1 --port 9999 -m "FIRE IN BLOCK A"
```

## Using WSL 2

WSL uses the same Python setup as native Ubuntu. The only WSL-specific change
is `--no-tc`, because WSL kernels may not support Mininet traffic-control
qdiscs.

If WSL is not installed, run this once from Administrator PowerShell:

```powershell
wsl --install -d Ubuntu
```

Then run this in Ubuntu:

```bash
sudo apt update
sudo apt install -y git curl mininet openvswitch-switch iperf3

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.11

git clone https://github.com/AAK1767/emergency-notification-network.git
cd emergency-notification-network

python3 -m pip install "pip==20.3.4" "setuptools==67.6.1" wheel "eventlet==0.33.3"
python3 -m pip install --no-build-isolation -r requirements.txt
sudo service openvswitch-switch start
```

Use two WSL terminals. In terminal 1, start the controller:

```bash
cd ~/emergency-notification-network
python3 controller/run_ryu.py controller/ryu_app.py --observe-links --verbose
```

In terminal 2, start the topology:

```bash
cd ~/emergency-notification-network
sudo mn -c
sudo python3 topology/topo.py --no-tc
```

When `mininet>` appears, run the server, clients, and alert sender. Replace
`/home/<user>/emergency-notification-network` with your repository path if
using a custom working directory:

```text
mininet> hServer python3 server/server.py &
mininet> hC1 python3 client/client.py --id C1 --server 10.0.0.1 --port 9999 &
mininet> hC2 python3 client/client.py --id C2 --server 10.0.0.1 --port 9999 &
mininet> hC3 python3 client/client.py --id C3 --server 10.0.0.1 --port 9999 &
mininet> hAdmin python3 server/send_alert.py --server 10.0.0.1 --port 9999 -m "FIRE IN BLOCK A"
```

## Repository Structure

```
├── config/
│   └── config.json          # Central configuration
├── common/
│   ├── protocol.py          # Message encoding / decoding
│   └── logger.py            # Timestamped logging
├── server/
│   ├── server.py            # Emergency notification server
│   ├── subscriber_manager.py
│   ├── alert_manager.py     # ACK tracking & retransmission
│   ├── controller_client.py # REST integration with Ryu
│   └── send_alert.py        # Standalone alert sender
├── client/
│   └── client.py            # Subscriber client
├── controller/
│   ├── run_ryu.py           # Python 3.11-compatible Ryu launcher
│   └── ryu_app.py           # Ryu SDN controller application
├── topology/
│   └── topo.py              # Mininet topology definition
├── tests/
│   └── test_protocol.py     # Unit + local E2E tests
├── experiments/             # Experiment scripts (D2)
├── results/                 # Data & graphs (D2)
├── docs/                    # Extra documentation
├── run_demo.py              # Automated D1 demo
├── plan.md                  # Full project plan
└── requirements.txt
```

## Quick Start (D1 Demo)

The D1 demo showcases **end-to-end emergency notification delivery**:

```text
hAdmin sends an ALERT → hServer broadcasts it → hC1/hC2/hC3 receive it and send ACKs
```

The clients register with `hServer` first. The server then tracks each ACK and
reports when the alert has been acknowledged by all registered subscribers.

### Option A — Run the automated demo

This is the shortest way to run the complete D1 flow. Start the Ryu controller
in one terminal first:

```bash
python controller/run_ryu.py controller/ryu_app.py --observe-links --verbose
```

In a second terminal, from the repository root, clean up any stale Mininet
state, then run the automated demo:

```bash
sudo mn -c
sudo python3 run_demo.py
```

For WSL kernels that do not support Mininet traffic-control qdiscs, use:

```bash
sudo mn -c
sudo python3 run_demo.py --no-tc
```

The demo intentionally uses Ubuntu's system `python3`, including for the
server, clients, and alert sender started inside Mininet. Mininet is installed
as an Ubuntu system package, so this avoids a separate virtual-environment
setup for the demo.

Run `sudo mn -c` again before retrying if the demo is interrupted or exits
without cleaning up the network.

`run_demo.py` automates the parts that are otherwise entered at the Mininet
prompt:

1. Creates and starts the D1 topology.
2. Runs `pingall` to verify host connectivity.
3. Starts `server/server.py` on `hServer`.
4. Starts clients `C1`, `C2`, and `C3` on `hC1`, `hC2`, and `hC3`.
5. Sends the fixed demo message `FIRE IN BLOCK A` from `hAdmin`.
6. Drops into the Mininet CLI so that commands such as `dump` and
   `ovs-ofctl dump-flows s1 -O OpenFlow13` can still be run interactively.

The script does not start the Ryu controller and does not open xterm windows;
those must be started separately if needed. It uses the repository's
system `python3` interpreter for the host processes.

### Verify the automated demo visibly

Watch the demo terminal for these two kinds of log lines. After the automated alert is sent, `run_demo.py` prints a **Delivery logs**
section containing the server log and each client log. Each client should
have an `ALERT received` line for the same sequence number, and the server
should have an `ACK ... received` line for each subscriber:

```text
[CLIENT:C1] ALERT received [SEQ=<n> PRIO=HIGH]: FIRE IN BLOCK A
[CLIENT:C2] ALERT received [SEQ=<n> PRIO=HIGH]: FIRE IN BLOCK A
[CLIENT:C3] ALERT received [SEQ=<n> PRIO=HIGH]: FIRE IN BLOCK A
[SERVER:ALERT] ACK seq=<n> received from C1
[SERVER:ALERT] ACK seq=<n> received from C2
[SERVER:ALERT] ACK seq=<n> received from C3
```

The timestamp prefix and the exact sequence number vary. The final
`All ACKs received for ALERT` server message confirms that the complete
delivery cycle finished. The script also prints the temporary log directory;
from the Mininet CLI you can recheck a log with, for example:

```text
mininet> hC1 cat /tmp/emergency-notification-demo-<pid>/C1.log
mininet> hServer cat /tmp/emergency-notification-demo-<pid>/server.log
```

To inspect the SDN rule from the Mininet CLI, run:

```text
mininet> sh ovs-ofctl dump-flows s1 -O OpenFlow13
```

Look for the flow matching `udp,tp_dst=9999` with `set_queue:1`. This checks
the emergency forwarding rule; the client and server log lines above check
actual notification delivery and ACKs.

### Option B — Run the D1 flow manually

Start the Ryu controller and topology as described above, then at the
`mininet>` prompt start the server and all three clients:

```text
mininet> hServer python3 server/server.py &
mininet> hC1 python3 client/client.py --id C1 --server 10.0.0.1 --port 9999 &
mininet> hC2 python3 client/client.py --id C2 --server 10.0.0.1 --port 9999 &
mininet> hC3 python3 client/client.py --id C3 --server 10.0.0.1 --port 9999 &
```

For visibly separated client and server logs, open xterms before starting
these processes:

```text
mininet> xterm hServer hC1 hC2 hC3
```

Run the commands above in the corresponding xterms, then send an alert from
`hAdmin`:

```text
mininet> hAdmin python3 server/send_alert.py --server 10.0.0.1 --port 9999 -m "FIRE IN BLOCK A"
```

Verify the same three client `ALERT received` lines and three server
`ACK ... received` lines described in the automated flow. You can also type
an alert into the server's interactive CLI; `server/server.py` broadcasts
non-empty lines entered there to all currently registered subscribers.

### Troubleshooting: `No module named 'mininet'`

If `sudo python3 run_demo.py` reports `ModuleNotFoundError:
No module named 'mininet'`, confirm that Mininet is installed in the
WSL/Ubuntu distribution, not only on the Windows host:

```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch
python3 -c "import mininet; print('Mininet import OK')"
```

If the import check fails, run the installation commands as an Ubuntu/WSL
administrator and retry the demo. This error occurs before the topology is
created.

## Running Tests (Local, No Mininet Required)

```bash
python -m pytest tests/ -v
```

## Configuration

All tunables are centralized in `config/config.json`:

| Parameter | Default | Description |
|---|---|---|
| `emergency_port` | 9999 | UDP port for emergency traffic |
| `ack_timeout_ms` | 300 | Milliseconds before retransmission |
| `max_retries` | 3 | Maximum alert retransmissions |
| `stats_poll_interval_s` | 2 | Controller stats polling interval |
| `congestion_threshold_percent` | 70 | Utilization threshold for congestion |

## Key Features (D1)

- [x] UDP protocol with 5-field message format
- [x] Dynamic subscriber registration / unregistration
- [x] Alert broadcast to all registered subscribers
- [x] Per-alert sequence numbers
- [x] ACK-based delivery confirmation
- [x] Timeout + retransmission (configurable)
- [x] Concurrent multi-client handling (threading)
- [x] Ryu controller with OpenFlow 1.3
- [x] Emergency traffic classification (UDP dst port)
- [x] High-priority queue assignment for emergency packets
- [x] Port-statistics monitoring
- [x] REST API for application → controller events
- [x] Redundant two-path Mininet topology
- [x] Baseline-ready (same application, no SDN priority)

## Upcoming (D2)

- [ ] OVS QoS queue configuration scripts
- [ ] Dynamic congestion response
- [ ] Link-failure detection & rerouting
- [ ] Baseline vs. proposed experiments
- [ ] CSV data collection pipeline
- [ ] Matplotlib performance graphs
- [ ] Full experiment matrix

## License

MIT
