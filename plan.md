# Project 16 — Emergency Notification Network

## 1. Project Overview

Build a **UDP-based emergency notification system** deployed on **Mininet** and controlled by an **SDN controller (Ryu + OpenFlow 1.3)**.

The system must:

- Register multiple emergency-notification subscribers.
- Send urgent alert messages to all currently registered subscribers.
- Require delivery confirmation through ACKs.
- Retransmit alerts when an expected ACK is not received.
- Identify emergency traffic inside the SDN network.
- Give emergency packets higher forwarding priority during congestion.
- Dynamically react to congestion using network statistics.
- Demonstrate rerouting when a path/link fails.
- Measure latency and packet loss.
- Compare the SDN-controlled system against a non-SDN baseline.
- Produce reproducible experiments, graphs, documentation, and a final demo.

The overall project is designed around the socket-programming, Mininet, SDN-integration, dynamic-SDN, robustness, performance, and documentation requirements in the supplied Jackfruit rubric. The rubric specifically requires low-level TCP/UDP sockets, multiple communicating nodes where applicable, Mininet deployment, interaction with the SDN-controlled network, reproducible topology/source/configuration/test instructions, and complete GitHub documentation. 

Source rubric: `SDN-Socket Programming – Jackfruit Mini Project`.

---

# 2. Problem Statement

During a network emergency, alert traffic should reach subscribers quickly even when ordinary background traffic is consuming network capacity.

The project therefore implements an emergency notification service in which:

```text
Emergency Alert Application
          |
          v
      UDP Server
          |
          v
   SDN-controlled network
          |
     +----+----+----+
     |    |    |    |
    C1   C2   C3   C4 ... Cn
```

The SDN controller recognizes the emergency traffic and applies forwarding/QoS behavior so that emergency notifications receive preferential treatment.

The project must also demonstrate that this behavior matters by deliberately creating congestion and comparing:

```text
Baseline:
Normal forwarding + congestion
        VS
Proposed:
SDN prioritization + congestion
```

---

# 3. Main Objectives

## Functional objectives

1. Implement the emergency notification application using UDP sockets.
2. Support dynamic subscriber registration and unregistration.
3. Broadcast alerts to all registered subscribers.
4. Assign a sequence number to every alert.
5. Have subscribers return an ACK for received alerts.
6. Retransmit an alert when an ACK is not received within a timeout.
7. Handle multiple subscribers concurrently.
8. Detect/classify emergency traffic in the SDN network.
9. Prioritize emergency traffic over background traffic.
10. Monitor network utilization dynamically.
11. Adapt SDN behavior when congestion crosses a threshold.
12. Reroute traffic after a link/path failure.
13. Measure notification latency and packet loss.
14. Compare SDN behavior against a suitable baseline.

---

# 4. Technology Stack

| Component | Technology |
|---|---|
| Application language | Python 3 |
| Socket API | Python `socket` |
| Transport protocol | UDP |
| Network emulator | Mininet |
| Virtual switches | Open vSwitch (OVS) |
| SDN controller | Ryu |
| Southbound protocol | OpenFlow 1.3 |
| Background traffic | `iperf` / `iperf3` |
| Link impairment | Mininet `loss`, `tc netem`, bandwidth limits |
| Packet inspection | Wireshark / `tcpdump` |
| Data processing | Python |
| Graphs | Matplotlib |
| Experiment results | CSV |
| Version control | Git + GitHub |

---

# 5. High-Level Architecture

## 5.1 Application Layer

### Notification Server

Responsibilities:

- Maintain the subscriber registry.
- Accept `REGISTER` messages.
- Accept `UNREGISTER` messages.
- Generate/broadcast emergency alerts.
- Assign unique sequence numbers.
- Track pending ACKs.
- Retransmit when required.
- Record timestamps for measurements.
- Communicate application events to the Ryu controller.

### Subscriber Client

Responsibilities:

- Register with the server.
- Listen for incoming alerts.
- Validate the alert sequence number.
- Record receive timestamp.
- Send an ACK.
- Remain available for multiple alerts.
- Unregister cleanly when exiting.

### Alert Sender

This can be:

- a CLI running on the server host, or
- a separate admin host.

Responsibilities:

- Enter alert text.
- Select priority.
- Trigger the server to distribute the alert.

### Background Traffic Hosts

Generate ordinary traffic using UDP `iperf`/`iperf3` so that congestion can be intentionally created.

---

# 6. Proposed Mininet Topology

Use a topology with **two paths between the server side and subscriber side** so that rerouting can be demonstrated.

Recommended topology:

```text
                         +------ s2 ------+
                         |                |
hServer ---- s1 ---------+                +-------- s4 ---- hC1
                         |                |
                         +------ s3 ------+-------- hC2
                                  |
                                hC3

Other hosts:
hNoise1 ---- attached near s2
hNoise2 ---- attached near s3
```

Logical paths:

```text
Path A: s1 -> s2 -> s4
Path B: s1 -> s3 -> s4
```

A link failure on one branch should allow the controller to select the surviving path.

### Suggested host placement

```text
hServer : Emergency notification server
hAdmin  : Alert sender
hC1     : Subscriber 1
hC2     : Subscriber 2
hC3     : Subscriber 3
hC4     : Subscriber 4 (optional)
hNoise1 : Background traffic generator
hNoise2 : Background traffic generator
```

Start with **3 subscribers** so the first implementation remains manageable. Extend to 5 or 10 for performance experiments.

---

# 7. UDP Application Protocol

All application messages should use one clearly documented format.

Recommended format:

```text
TYPE | SEQ | PRIORITY | TIMESTAMP | PAYLOAD
```

Example:

```text
REGISTER | 0 | NORMAL | 1727670000.124 | subscriber1
```

```text
ALERT | 42 | HIGH | 1727670004.531 | FIRE IN BLOCK A
```

```text
ACK | 42 | HIGH | 1727670004.781 | subscriber1
```

```text
UNREGISTER | 0 | NORMAL | 1727670100.220 | subscriber1
```

```text
HEARTBEAT | 0 | NORMAL | 1727670102.004 | subscriber1
```

## Message types

### `REGISTER`

Adds a subscriber to the active subscriber table.

### `UNREGISTER`

Removes a subscriber from the active table.

### `ALERT`

Carries the emergency notification.

### `ACK`

Confirms receipt of a specific alert sequence number.

### `HEARTBEAT`

Optional liveness message to detect inactive clients.

---

# 8. Subscriber Registry

Maintain a structure similar to:

```text
subscriber_id
IP address
UDP port
registration time
last seen time
pending alerts
```

Example:

```text
C1 -> 10.0.0.2:9001
C2 -> 10.0.0.3:9001
C3 -> 10.0.0.4:9001
```

The server must never assume a fixed number of subscribers.

A new client can register while the system is running.

---

# 9. Alert Delivery and ACK Mechanism

## Basic flow

```text
Admin
  |
  | trigger alert
  v
Server
  |
  | ALERT(seq=42)
  +---------------------> C1
  +---------------------> C2
  +---------------------> C3
  |
  | wait for ACKs
  |
  +<--------------------- ACK 42 C1
  +<--------------------- ACK 42 C2
  +<--------------------- ACK 42 C3
```

## Retransmission

For each alert:

```text
send ALERT
      |
      v
wait ACK until timeout
      |
   +--+--+
   |     |
 ACK   timeout
   |     |
 done   retry
         |
      max retries
         |
   mark delivery failed
```

Recommended starting values:

```text
ACK timeout = 200–500 ms
Maximum retries = 3
```

These values should be configurable rather than hard-coded.

---

# 10. Concurrency Design

The application must handle several clients at once.

Recommended approach:

### Server

Use:

```text
Main thread
   |
   +--> receive/register/unregister handling
   +--> alert sender
   +--> ACK/retransmission handling
```

Possible implementation choices:

- Python threads, or
- `threading` + shared subscriber state.

For this project, **threads are easier to demonstrate during viva**.

Protect shared data such as:

```text
subscriber list
pending ACK table
sequence counter
```

with a `threading.Lock` where required.

---

# 11. SDN Traffic Classification

Use a dedicated UDP destination port for emergency traffic.

Example:

```text
Emergency UDP port = 9999
Normal UDP port    = 8888
```

The controller identifies emergency packets using the UDP destination port.

Example OpenFlow match concept:

```text
match:
    IPv4
    UDP
    udp_dst = 9999
```

The emergency rule should have a higher priority than ordinary UDP forwarding rules.

An optional enhancement is DSCP marking, but the **dedicated UDP port should remain the primary classification mechanism** because it is simple and easy to demonstrate.

---

# 12. SDN Prioritization

Emergency traffic should not merely be "recognized"; the network should actually give it preferential treatment.

Use OVS QoS/queues.

Conceptually:

```text
                  +------------------+
Emergency ----->  | High Priority    | ---->
                  | Queue             |
                  +------------------+

Normal ---------> | Normal Queue     | ---->
                  +------------------+
```

The emergency OpenFlow rule can use:

```text
set_queue(EMERGENCY_QUEUE)
```

before output.

The project should demonstrate the difference during congestion:

```text
Without prioritization:
background traffic competes with alerts

With prioritization:
background traffic is restricted/de-prioritized,
while emergency packets continue to receive service
```

Important: document exactly how OVS queues/QoS are configured on each relevant switch.

---

# 13. Dynamic SDN Behaviour

This is one of the most important parts of the project because the rubric gives **6 marks** to Dynamic SDN Functionality.

The controller should periodically collect switch/port statistics.

Suggested polling interval:

```text
1–2 seconds
```

Track:

```text
bytes transmitted
bytes received
packet counts
port utilization
```

Calculate utilization over an interval.

Example logic:

```text
if utilization < threshold:
    normal forwarding/QoS

if utilization >= threshold:
    activate/tighten emergency prioritization

if path becomes unavailable:
    select alternate path
    install new flows
```

Example configurable threshold:

```text
CONGESTION_THRESHOLD = 70%
```

The threshold should be experimentally adjustable.

---

# 14. Socket–SDN Integration

The application must directly influence network control.

Use a simple control interface between the notification server and the Ryu controller.

Recommended design:

```text
Notification Server
        |
        | REST request / control message
        v
     Ryu Controller
        |
        | OpenFlow rules
        v
      OVS Switches
```

## Event examples

### Registration event

```text
Subscriber C3 registers
        |
        v
Server informs controller
        |
        v
Controller can prepare/update subscriber-related flows
```

### Emergency event

```text
ALERT triggered
        |
        v
Server informs controller:
"Emergency traffic active"
        |
        v
Controller ensures high-priority emergency flow
```

This makes the application event itself influence SDN behavior, directly satisfying the socket–SDN integration requirement.

---

# 15. Link-Failure Handling

Use the redundant topology to demonstrate recovery.

Normal:

```text
s1 ---> s2 ---> s4
```

Failure:

```text
s1 -X-> s2
```

Controller should detect the failed path and redirect traffic:

```text
s1 ---> s3 ---> s4
```

The demonstration should capture:

1. Alert delivery before failure.
2. Link failure event.
3. Controller detection.
4. New flow installation.
5. Alert delivery after rerouting.
6. Any temporary latency increase or packet loss.

Do not claim "zero packet loss" unless the measurements actually show it.

---

# 16. Test Scenarios

## Test 1 — Normal Operation

Conditions:

```text
No background congestion
No link failure
3 subscribers
```

Verify:

- All subscribers receive alerts.
- ACKs are returned.
- No unexpected retransmissions.
- Latency is recorded.

Expected observation:

```text
Reliable end-to-end alert exchange under normal load.
```

---

## Test 2 — Light Congestion

Generate a small UDP background load.

Example concept:

```text
iperf/iperf3 UDP traffic
```

Send alerts simultaneously.

Compare:

```text
baseline vs SDN
```

Measure:

- latency
- packet loss
- retransmissions

---

## Test 3 — Heavy Congestion

Generate enough background traffic to saturate or heavily load a shared bottleneck.

Verify:

```text
background traffic increases
        |
        v
controller detects high utilization
        |
        v
emergency flow receives priority
```

This should be the primary demonstration of the project's purpose.

---

## Test 4 — Packet Loss

Introduce controlled packet loss with:

```text
Mininet link loss
```

or:

```text
tc netem
```

Verify that:

```text
missing ACK
    |
    v
retransmission
    |
    v
eventual ACK
```

is handled correctly.

---

## Test 5 — Link Failure

Bring down one path during an active experiment.

Verify:

```text
failure -> detection -> reroute -> continued service
```

---

## Test 6 — Subscriber Churn

During operation:

```text
C1 registers
C2 registers
C3 registers
C2 unregisters
C4 registers
```

Then send an alert.

Verify only currently registered subscribers are targeted.

---

## Test 7 — Multiple Subscribers

Run:

```text
1 subscriber
5 subscribers
10 subscribers
```

and compare:

- average latency
- maximum latency
- packet loss
- retransmissions

---

# 17. Baseline Implementation

The performance comparison requires a baseline.

Use the **same Mininet topology and UDP application**, but remove the proposed SDN prioritization/dynamic behavior.

Baseline:

```text
Normal forwarding
No emergency queue priority
Static/ordinary flow handling
```

Proposed:

```text
SDN classification
+ emergency queue priority
+ dynamic monitoring
+ rerouting
```

Keep as many variables identical as possible:

```text
same topology
same alert size
same alert rate
same subscriber count
same background traffic
same test duration
```

Only the network-control mechanism should differ.

---

# 18. Performance Metrics

## 18.1 Notification Latency

Measure:

```text
Latency = receive_timestamp - send_timestamp
```

Because Mininet hosts run on the same machine, host clocks are suitable for this project experiment.

For every alert, record:

```text
sequence number
subscriber
send time
receive time
latency
```

Report:

- average
- minimum
- maximum
- optionally median and 95th percentile

---

## 18.2 Packet Loss

Use alert sequence numbers.

Example:

```text
Sent:     1 2 3 4 5 6 7 8
Received: 1 2 4 5 7 8
Missing:      3   6
```

Compute:

```text
Packet Loss % =
(missing packets / sent packets) × 100
```

Be explicit about whether loss means:

- original notification packets lost, or
- final undelivered notifications after retransmission.

Prefer reporting both where practical.

---

## 18.3 Delivery Success Rate

```text
Delivery Success % =
(successfully delivered alerts / total alerts) × 100
```

---

## 18.4 Retransmission Count

Record:

```text
alert 42 -> retransmitted 1 time
alert 43 -> retransmitted 0 times
```

Then calculate totals/average.

---

## 18.5 Throughput / Background Traffic

Optionally record the throughput of background UDP traffic so that congestion conditions are reproducible.

---

# 19. Experiment Matrix

Use controlled conditions.

| Experiment | Background Load | Subscribers | SDN Mode |
|---|---:|---:|---|
| E1 | None | 1 | Baseline |
| E2 | None | 1 | Proposed |
| E3 | Light | 1 | Baseline |
| E4 | Light | 1 | Proposed |
| E5 | Moderate | 5 | Baseline |
| E6 | Moderate | 5 | Proposed |
| E7 | Heavy | 5 | Baseline |
| E8 | Heavy | 5 | Proposed |
| E9 | Heavy | 10 | Baseline |
| E10 | Heavy | 10 | Proposed |
| E11 | Packet loss | 5 | Proposed |
| E12 | Link failure | 5 | Proposed |

Run each important condition multiple times rather than relying on one run.

Recommended starting point:

```text
3 repetitions per experiment
```

Then report the mean and variation.

---

# 20. Result Files

Each experiment should generate machine-readable output.

Recommended CSV columns:

```text
experiment_id
mode
background_load
subscriber_count
alert_seq
subscriber_id
send_time
receive_time
latency_ms
delivered
retransmissions
```

A separate network-statistics CSV can contain:

```text
timestamp
switch
port
rx_bytes
tx_bytes
utilization_percent
```

---

# 21. Graphs

Minimum useful graphs:

## Graph 1 — Latency under congestion

```text
X-axis: background traffic load
Y-axis: notification latency (ms)
Lines: baseline vs SDN
```

## Graph 2 — Packet loss

```text
X-axis: background traffic load
Y-axis: packet loss (%)
Lines: baseline vs SDN
```

## Graph 3 — Retransmissions

```text
X-axis: background traffic load
Y-axis: average retransmissions per alert
Lines: baseline vs SDN
```

## Graph 4 — Subscriber scaling

```text
X-axis: number of subscribers
Y-axis: average notification latency
```

## Graph 5 — Link failure recovery

Show either:

```text
latency over time
```

or:

```text
active path over time
```

with the failure point clearly marked.

---

# 22. Controller Responsibilities

The Ryu application should be divided into clear responsibilities.

Suggested structure:

```text
Ryu Controller
|
+-- Switch connection / handshake
|
+-- Flow installation
|
+-- Emergency traffic classifier
|
+-- QoS / priority management
|
+-- Port-statistics monitoring
|
+-- Congestion detector
|
+-- Path/rerouting manager
|
+-- REST/control API
|
+-- Logging
```

The controller should log important state transitions, for example:

```text
[SDN] s1 connected
[SDN] emergency flow installed
[SDN] s2 port 2 utilization = 82%
[SDN] congestion threshold exceeded
[SDN] alternate path selected
[SDN] flow updated
```

These logs will be useful during the demo and viva.

---

# 23. Notification Server Responsibilities

Suggested internal modules:

```text
server/
    server.py
    subscriber_manager.py
    alert_manager.py
    protocol.py
    controller_client.py
    logger.py
```

### `protocol.py`

Responsible for:

- message formatting
- parsing
- validation

### `subscriber_manager.py`

Responsible for:

- register
- unregister
- lookup
- active subscriber state

### `alert_manager.py`

Responsible for:

- sequence numbers
- sending alerts
- ACK tracking
- timeout
- retransmission

### `controller_client.py`

Responsible for:

- sending REST/control events to Ryu

---

# 24. Subscriber Client Responsibilities

Suggested structure:

```text
client/
    client.py
    protocol.py
    logger.py
```

Core flow:

```text
start
 |
 +--> register
 |
 +--> listen
 |      |
 |      +--> ALERT received
 |              |
 |              +--> record timestamp
 |              +--> display alert
 |              +--> send ACK
 |
 +--> heartbeat (optional)
 |
 +--> unregister
 |
end
```

---

# 25. Recommended Repository Layout

```text
emergency-notification-network/
│
├── README.md
├── PLAN.md
├── requirements.txt
├── LICENSE
│
├── server/
│   ├── server.py
│   ├── protocol.py
│   ├── subscriber_manager.py
│   ├── alert_manager.py
│   ├── controller_client.py
│   └── logger.py
│
├── client/
│   ├── client.py
│   ├── protocol.py
│   └── logger.py
│
├── controller/
│   ├── ryu_app.py
│   ├── routing.py
│   ├── qos.py
│   ├── monitor.py
│   └── api.py
│
├── topology/
│   └── topo.py
│
├── tests/
│   ├── test_normal.sh
│   ├── test_congestion.sh
│   ├── test_loss.sh
│   ├── test_failure.sh
│   └── test_churn.sh
│
├── experiments/
│   ├── run_experiment.py
│   └── config.json
│
├── results/
│   ├── raw/
│   ├── processed/
│   └── graphs/
│
└── docs/
    ├── architecture.md
    ├── protocol.md
    ├── experiments.md
    └── demo.md
```

Keep generated result files separate from source code.

---

# 26. Development Plan

## Phase 1 — Understand and Freeze the Design

Deliver:

- architecture diagram
- topology design
- protocol specification
- list of message types
- list of ports
- list of metrics
- baseline definition

### Done when

Everyone in the group can explain:

```text
Who sends what?
To whom?
Over which UDP port?
How is an ACK handled?
How does SDN recognize emergency traffic?
How is priority applied?
How is congestion detected?
How is rerouting triggered?
```

---

# 27. Phase 2 — Build the UDP Application

Implement in this order:

### Step 1

Create protocol encode/decode functions.

### Step 2

Implement subscriber registration.

### Step 3

Implement unregistration.

### Step 4

Implement alert broadcast.

### Step 5

Add sequence numbers.

### Step 6

Implement ACK handling.

### Step 7

Implement retransmission.

### Step 8

Add concurrent client handling.

### Step 9

Add logging and timestamps.

### Step 10

Test the application outside Mininet first.

### Exit criterion

A server + 3 local clients must be able to:

```text
register
receive alert
send ACK
retransmit on timeout
unregister
```

before SDN is added.

---

# 28. Phase 3 — Build the Mininet Topology

Implement:

```text
hServer
hAdmin
hC1...hCn
hNoise1...
s1
s2
s3
s4
```

Verify:

```bash
pingall
```

and verify the expected paths.

Then run the UDP application inside Mininet hosts.

### Exit criterion

The complete UDP system works through Mininet without SDN-specific prioritization.

---

# 29. Phase 4 — Implement the Ryu Controller

First implement:

1. OpenFlow 1.3 switch connection.
2. Basic forwarding.
3. Flow-table logging.
4. Emergency UDP classification.
5. High-priority emergency flow.
6. QoS queue handling.
7. Port-stat monitoring.
8. Congestion detection.
9. Alternate-path selection.
10. Link-failure recovery.

Do not implement all dynamic features at once.

Test each stage independently.

---

# 30. Phase 5 — Socket–SDN Integration

Implement the application-to-controller interface.

Example event model:

```text
SERVER -> RYU

REGISTER:
{
    "event": "subscriber_register",
    "subscriber_ip": "...",
    "subscriber_port": ...
}

ALERT:
{
    "event": "emergency_alert",
    "sequence": 42,
    "priority": "HIGH"
}
```

The exact JSON schema should be documented once finalized.

### Exit criterion

Triggering an application event produces a visible controller-side action/log entry.

---

# 31. Phase 6 — Congestion and Dynamic Behaviour

Introduce background UDP traffic.

Then verify:

```text
low utilization
     |
     v
normal state

high utilization
     |
     v
congestion detected
     |
     v
emergency QoS activated
```

Capture:

```bash
ovs-ofctl dump-flows <switch>
```

and controller logs as evidence.

---

# 32. Phase 7 — Robustness

Implement and test:

### Packet loss

```text
loss -> timeout -> retransmission -> ACK
```

### Link failure

```text
failure -> detection -> alternate path
```

### Subscriber churn

```text
register/unregister while system is active
```

At least one meaningful challenging scenario is required by the rubric, with examples including congestion, packet loss, link failure, overload, or service failure.

---

# 33. Phase 8 — Performance Evaluation

Run the same experiments against:

```text
A. Baseline
B. Proposed SDN system
```

Collect raw CSV data first.

Do not manually type graph values.

Pipeline:

```text
Mininet experiment
      |
      v
CSV logs
      |
      v
analysis script
      |
      v
statistics
      |
      v
Matplotlib graphs
```

---

# 34. Phase 9 — Documentation

README must contain:

1. Project overview.
2. Problem statement.
3. Architecture.
4. Software requirements.
5. Installation.
6. Repository structure.
7. How to start Ryu.
8. How to start Mininet.
9. How to start server.
10. How to start clients.
11. How to trigger an alert.
12. How to create congestion.
13. How to trigger link failure.
14. How to run baseline.
15. How to run experiments.
16. How to generate graphs.
17. Sample output.
18. Results.
19. Limitations.
20. Team/member contribution.

The supplied rubric explicitly expects topology, source code, configuration, test cases, reproduction instructions, and complete GitHub documentation.

---

# 35. Demo Plan

The final demo should be scripted rather than improvised.

## Demo Part 1 — Show architecture

Explain:

```text
Admin -> UDP Server -> SDN network -> Subscribers
                         ^
                         |
                    Ryu Controller
```

## Demo Part 2 — Register clients

Show:

```text
C1 registered
C2 registered
C3 registered
```

## Demo Part 3 — Send normal alert

Send one emergency alert.

Show:

```text
C1 received
C2 received
C3 received

ACKs returned
```

## Demo Part 4 — Show SDN flow

Run:

```bash
ovs-ofctl dump-flows s1
```

Show the emergency flow.

## Demo Part 5 — Create congestion

Start UDP background traffic.

Send emergency alerts during congestion.

## Demo Part 6 — Show dynamic response

Show:

```text
controller statistics
congestion detection
priority flow / queue action
```

## Demo Part 7 — Fail a link

Bring down one path.

Show:

```text
path failure
controller response
alternate path
continued alert delivery
```

## Demo Part 8 — Show results

Display latency/loss comparison graphs.

---

# 36. Evidence to Capture

Capture screenshots/logs for:

```text
1. Mininet topology
2. pingall success
3. subscriber registration
4. alert delivery
5. ACK exchange
6. retransmission
7. Ryu controller logs
8. emergency flow table
9. QoS/queue configuration
10. congestion statistics
11. link failure
12. rerouted traffic
13. baseline result
14. SDN result
15. final graphs
```

These provide concrete evidence for the demo, report, and viva.

---

# 37. Rubric Mapping

The supplied rubric allocates **40 marks total**:

- D1 = 15 marks
- D2 = 25 marks

The detailed rubric evaluates architecture, socket implementation, Mininet + SDN, socket–SDN integration, initial testing, complete functionality, dynamic SDN behavior, robustness, performance comparison, and documentation/demo/viva. 

| Rubric Component | Marks | Project Evidence |
|---|---:|---|
| Problem Understanding & Architecture | 2 | Architecture diagram, objectives, protocol, communication flow |
| TCP/UDP Socket Implementation | 4 | UDP server/client, datagrams, ACKs, retransmission, concurrency, error handling |
| Mininet + SDN Implementation | 4 | Mininet topology, OVS switches, Ryu controller, OpenFlow rules |
| Socket–SDN Integration | 3 | Server/controller API and application-triggered SDN behavior |
| Initial Testing & Demo | 2 | End-to-end Mininet demo and basic test cases |
| Complete Application Functionality | 4 | Registration, alerts, ACKs, retransmission, multiple subscribers |
| Dynamic SDN Functionality | 6 | Port-stat monitoring, congestion response, prioritization, rerouting |
| Challenging Scenario / Robustness | 4 | Congestion + packet loss and/or link failure |
| Performance Evaluation & Comparison | 5 | Latency/loss/retransmission measurements and baseline comparison |
| Documentation, Final Demo & Viva | 6 | README, reproducible commands, graphs, architecture and individual understanding |

---

# 38. D1 Target

The first milestone should produce a **small but working end-to-end system**.

## D1 checklist

```text
[ ] Architecture finalized
[ ] UDP protocol finalized
[ ] Server implemented
[ ] Client implemented
[ ] Subscriber registration works
[ ] Alert delivery works
[ ] ACK mechanism works
[ ] 3 clients work
[ ] Mininet topology works
[ ] Ryu connects to switches
[ ] Emergency UDP traffic is classified
[ ] Priority flow can be observed
[ ] Basic end-to-end demonstration works
[ ] Initial documentation written
```

Do not wait until D2 to discover that the core application is broken.

---

# 39. D2 Target

D2 should add the features that make the project genuinely SDN-centric.

## D2 checklist

```text
[ ] Retransmission fully tested
[ ] Dynamic port monitoring works
[ ] Congestion threshold detection works
[ ] Emergency QoS activates correctly
[ ] Link-failure rerouting works
[ ] Packet-loss scenario tested
[ ] Subscriber churn tested
[ ] Baseline implemented
[ ] Multiple experimental conditions tested
[ ] CSV data collection automated
[ ] Graph generation automated
[ ] Results analyzed
[ ] README complete
[ ] Demo procedure reproducible
[ ] Every team member understands the implementation
```

---

# 40. Suggested Two-Day Work Split

## Day 1 — D1

### Morning

```text
Architecture
Protocol
Mininet topology
```

### Midday

```text
UDP server
UDP client
registration
alert broadcast
```

### Afternoon

```text
ACK
retransmission
concurrency
```

### Evening

```text
Ryu
basic OpenFlow
emergency traffic classification
priority flow
```

### Day 1 end goal

```text
Admin
  |
  v
UDP server
  |
  v
Mininet + OVS + Ryu
  |
  +--> C1
  +--> C2
  +--> C3
```

with working alert + ACK communication.

---

# 41. Day 2 — D2

### Morning

```text
QoS queues
port monitoring
dynamic congestion handling
```

### Midday

```text
link failure
alternate path
packet-loss handling
```

### Afternoon

```text
baseline
experiments
CSV collection
```

### Evening

```text
graphs
README
demo cleanup
viva preparation
```

---

# 42. Important Design Decisions

Keep these decisions simple and explainable.

### Decision 1 — UDP

UDP is required by the assigned project, so reliability is implemented at the **application layer** using:

```text
sequence number
ACK
timeout
retransmission
```

### Decision 2 — Dedicated emergency port

Use a dedicated port such as:

```text
9999
```

because this makes SDN classification easy to demonstrate.

### Decision 3 — Redundant topology

Use two paths so that rerouting is observable rather than theoretical.

### Decision 4 — QoS queue

Use OVS queueing so that "priority" has a concrete network effect during congestion.

### Decision 5 — Configurable thresholds

Put values such as:

```text
ACK_TIMEOUT
MAX_RETRIES
CONGESTION_THRESHOLD
POLL_INTERVAL
EMERGENCY_PORT
```

in one configuration file.

---

# 43. Error Handling Requirements

The application should handle at least:

```text
invalid message format
unknown message type
duplicate registration
unregistered ACK sender
client timeout
socket bind failure
socket send/receive errors
controller unavailable
subscriber disappearing
```

Do not let one failed subscriber terminate the entire server.

---

# 44. Logging Requirements

Use timestamped logs.

Example:

```text
2026-09-30 10:00:03.421 [SERVER] C1 registered
2026-09-30 10:00:08.932 [SERVER] ALERT seq=42 sent
2026-09-30 10:00:08.947 [CLIENT:C1] ALERT seq=42 received
2026-09-30 10:00:08.951 [CLIENT:C1] ACK seq=42 sent
2026-09-30 10:00:09.002 [SERVER] ACK seq=42 received from C1
```

Controller:

```text
2026-09-30 10:00:09.800 [SDN] s2 port=2 utilization=83%
2026-09-30 10:00:09.801 [SDN] congestion threshold exceeded
2026-09-30 10:00:09.802 [SDN] emergency queue activated
```

These logs make timing and causality easy to explain.

---

# 45. Configuration

Create a central configuration file such as:

```text
config/
    config.json
```

Example:

```json
{
  "emergency_port": 9999,
  "ack_timeout_ms": 300,
  "max_retries": 3,
  "stats_poll_interval_s": 2,
  "congestion_threshold_percent": 70,
  "experiment_duration_s": 30
}
```

Do not scatter configuration values throughout the code.

---

# 46. Validation Strategy

Build in layers.

```text
L1: UDP protocol
        |
L2: server/client
        |
L3: multi-client
        |
L4: Mininet deployment
        |
L5: Ryu forwarding
        |
L6: emergency classification
        |
L7: QoS prioritization
        |
L8: dynamic monitoring
        |
L9: rerouting
        |
L10: performance experiments
```

Only move to the next layer after the current layer works.

This reduces debugging complexity dramatically.

---

# 47. Common Failure Points to Avoid

### Do not make the controller purely decorative

Simply running Ryu while the application behaves identically to normal forwarding is not enough. The SDN functionality must affect network behavior.

### Do not claim prioritization without a measurable mechanism

Show the actual OpenFlow rule and QoS/queue configuration.

### Do not compare different experiments unfairly

Baseline and proposed system must use matching conditions.

### Do not manually enter performance results

Generate them from experiment logs.

### Do not make the topology unnecessarily large

A small redundant topology is easier to debug and easier to explain.

### Do not put everything in one Python file

Separate protocol, application logic, controller interaction, experiments, and analysis.

---

# 48. Definition of Done

The project is complete when all of the following are true:

```text
Application
    |
    +--> multiple subscribers
    +--> REGISTER/UNREGISTER
    +--> ALERT
    +--> ACK
    +--> timeout/retransmission
    +--> concurrency
    +--> logging
            |
            v
Mininet
    |
    +--> multi-switch topology
    +--> redundant paths
    +--> background traffic
            |
            v
Ryu/SDN
    |
    +--> OpenFlow 1.3
    +--> emergency classification
    +--> priority/QoS
    +--> statistics monitoring
    +--> congestion reaction
    +--> rerouting
            |
            v
Evaluation
    |
    +--> latency
    +--> packet loss
    +--> retransmissions
    +--> multiple loads
    +--> multiple subscriber counts
    +--> baseline comparison
    +--> graphs
            |
            v
Documentation
    |
    +--> README
    +--> setup instructions
    +--> test commands
    +--> architecture
    +--> results
    +--> reproducible demo
```

---

# 49. Final Deliverables

The GitHub repository should contain:

```text
[1] Source code
[2] Mininet topology
[3] Ryu controller
[4] Configuration
[5] Test scripts
[6] Experiment scripts
[7] Raw results
[8] Processed results
[9] Graphs
[10] README
[11] Architecture/protocol documentation
[12] Demo instructions
```

The supplied rubric states that students must provide the topology, source code, configuration, test cases, and reproduction instructions, and that the final demo code should be shared in a GitHub repository with complete documentation.

---

# 50. Immediate Next Step

Implement in this exact order:

```text
1. protocol.py
2. server.py
3. client.py
4. ACK + retransmission
5. Mininet topo.py
6. run UDP app inside Mininet
7. ryu_app.py
8. emergency flow classification
9. OVS QoS queue
10. socket -> Ryu integration
11. stats monitoring
12. congestion response
13. link-failure rerouting
14. baseline
15. automated experiments
16. graphs
17. README + demo
```

The priority is **working end-to-end functionality first**, followed by the dynamic SDN features and performance evidence that carry the largest D2 weight.
