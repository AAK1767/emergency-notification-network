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
git clone https://github.com/<your-user>/emergency-notification-network.git
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

git clone https://github.com/<your-user>/emergency-notification-network.git
cd emergency-notification-network

uv venv --seed --python 3.11 .venv
source .venv/bin/activate
python -m pip install "pip==20.3.4" "setuptools==67.6.1" wheel "eventlet==0.33.3"
python -m pip install --no-build-isolation -r requirements.txt

python -c "import ryu; print('Ryu import OK')"
sudo service openvswitch-switch start
```

Open a second terminal, activate the same environment, and start the Ryu
controller:

```bash
cd emergency-notification-network
source .venv/bin/activate
python controller/run_ryu.py controller/ryu_app.py --observe-links --verbose
```

In a third terminal, start the Mininet topology:

```bash
cd emergency-notification-network
sudo mn -c
sudo python3 topology/topo.py
```

When `mininet>` appears, run the server, clients, and alert sender using the
absolute path to `.venv/bin/python`:

```text
mininet> hServer /home/<user>/emergency-notification-network/.venv/bin/python server/server.py &
mininet> hC1 /home/<user>/emergency-notification-network/.venv/bin/python client/client.py --id C1 --server 10.0.0.1 --port 9999 &
mininet> hC2 /home/<user>/emergency-notification-network/.venv/bin/python client/client.py --id C2 --server 10.0.0.1 --port 9999 &
mininet> hC3 /home/<user>/emergency-notification-network/.venv/bin/python client/client.py --id C3 --server 10.0.0.1 --port 9999 &
mininet> hAdmin /home/<user>/emergency-notification-network/.venv/bin/python server/send_alert.py --server 10.0.0.1 --port 9999 -m "FIRE IN BLOCK A"
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

git clone https://github.com/<your-user>/emergency-notification-network.git
cd emergency-notification-network

uv venv --seed --python 3.11 .venv
source .venv/bin/activate
python -m pip install "pip==20.3.4" "setuptools==67.6.1" wheel "eventlet==0.33.3"
python -m pip install --no-build-isolation -r requirements.txt
sudo service openvswitch-switch start
```

Use two WSL terminals. In terminal 1, start the controller:

```bash
cd ~/emergency-notification-network
source .venv/bin/activate
python controller/run_ryu.py controller/ryu_app.py --observe-links --verbose
```

In terminal 2, start the topology:

```bash
cd ~/emergency-notification-network
sudo mn -c
sudo python3 topology/topo.py --no-tc
```

When `mininet>` appears, run the server, clients, and alert sender. Replace
`/home/<user>/emergency-notification-network` with your repository path:

```text
mininet> hServer /home/<user>/emergency-notification-network/.venv/bin/python server/server.py &
mininet> hC1 /home/<user>/emergency-notification-network/.venv/bin/python client/client.py --id C1 --server 10.0.0.1 --port 9999 &
mininet> hC2 /home/<user>/emergency-notification-network/.venv/bin/python client/client.py --id C2 --server 10.0.0.1 --port 9999 &
mininet> hC3 /home/<user>/emergency-notification-network/.venv/bin/python client/client.py --id C3 --server 10.0.0.1 --port 9999 &
mininet> hAdmin /home/<user>/emergency-notification-network/.venv/bin/python server/send_alert.py --server 10.0.0.1 --port 9999 -m "FIRE IN BLOCK A"
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

### Step 1 — Start the Ryu Controller

```bash
python controller/run_ryu.py controller/ryu_app.py --observe-links --verbose
```

### Step 2 — Start the Mininet Topology

```bash
sudo python3 topology/topo.py
```

### Step 3 — Start the Server (from Mininet CLI)

```bash
mininet> hServer python3 server/server.py &
```

### Step 4 — Start Subscriber Clients

```bash
mininet> hC1 python3 client/client.py --id C1 --server 10.0.0.1 --port 9999 &
mininet> hC2 python3 client/client.py --id C2 --server 10.0.0.1 --port 9999 &
mininet> hC3 python3 client/client.py --id C3 --server 10.0.0.1 --port 9999 &
```

### Step 5 — Send an Emergency Alert

From the hServer terminal, type the alert text and press Enter, **or** from a separate terminal:

```bash
mininet> hAdmin python3 server/send_alert.py --server 10.0.0.1 --port 9999 -m "FIRE IN BLOCK A"
```

### Step 6 — Verify SDN Emergency Flow

```bash
mininet> sh ovs-ofctl dump-flows s1 -O OpenFlow13
```

Look for the flow matching `udp,tp_dst=9999` with `set_queue:1`.

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
