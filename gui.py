#!/usr/bin/env python3
"""Interactive demo console for the Emergency Notification Network.

Run from the repository root with ``python gui.py``.  The console can run a
local server/client demo without Mininet and can execute or display the D2
Mininet commands when it is run on the Linux/WSL networking host.
"""

import ipaddress
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import tkinter as tk
import shutil
from tkinter import messagebox, simpledialog, ttk

from common import protocol


ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "config", "config.json")


def load_defaults():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as handle:
            config = json.load(handle)
        server = config["server"]
        host = str(server["host"])
        if host in {"0.0.0.0", "::"}:
            host = "127.0.0.1" if host == "0.0.0.0" else "::1"
        return host, int(server["port"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read config/config.json: {exc}") from exc


def validate_destination(host, port_text, message):
    host = host.strip()
    message = message.strip()
    if not host:
        raise ValueError("Server address is required.")
    try:
        ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("Enter a valid IPv4 or IPv6 server address.") from exc
    try:
        port = int(port_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("Port must be a number from 1 to 65535.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("Port must be a number from 1 to 65535.")
    if not message:
        raise ValueError("Alert message cannot be empty.")
    if len(message.encode("utf-8")) > 3500:
        raise ValueError("Alert message is too long (maximum 3500 bytes).")
    return host, port, message


def send_alert(host, port, message, priority):
    payload = protocol.make_alert(0, message, priority)
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_DGRAM) as sock:
        sock.settimeout(3)
        sock.sendto(payload, (host, port))


class DemoConsole:
    """Tkinter orchestration layer; all subprocess and socket work is off-thread."""

    def __init__(self, root):
        self.root = root
        self.root.title("Emergency Notification Network - Demo Console")
        self.root.minsize(980, 680)
        self.events = queue.Queue()
        self.processes = {}
        self.mininet_process = None
        self.closing = False

        try:
            host, port = load_defaults()
        except RuntimeError as exc:
            host, port = "127.0.0.1", 9999
            self.startup_error = str(exc)
        else:
            self.startup_error = None

        self.host = tk.StringVar(value=host)
        self.port = tk.StringVar(value=str(port))
        self.priority = tk.StringVar(value=protocol.PRIO_HIGH)
        self.message = tk.StringVar(value="FIRE IN BLOCK A")
        self.condition = tk.StringVar(value="baseline")
        self.count = tk.StringVar(value="20")
        self.drop_every = tk.StringVar(value="0")
        self.status = tk.StringVar(value="Ready")
        self._build()
        self.root.after(100, self._poll_events)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        if self.startup_error:
            self._log("ERROR", self.startup_error)

    def _build(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.demo_tab = ttk.Frame(self.notebook, padding=10)
        self.d2_tab = ttk.Frame(self.notebook, padding=10)
        self.explain_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.demo_tab, text="Live Demo")
        self.notebook.add(self.d2_tab, text="D2 Controls")
        self.notebook.add(self.explain_tab, text="What is happening?")
        self._build_demo_tab()
        self._build_d2_tab()
        self._build_explain_tab()

        bottom = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        bottom.pack(fill=tk.X)
        ttk.Label(bottom, textvariable=self.status).pack(side=tk.LEFT)
        ttk.Button(bottom, text="Clear output", command=self._clear_output).pack(side=tk.RIGHT)
        self.output = tk.Text(self.root, height=10, state=tk.DISABLED, wrap=tk.WORD)
        self.output.pack(fill=tk.BOTH, expand=False, padx=8, pady=(0, 8))

    def _build_demo_tab(self):
        # Live Demo controls the real local UDP server and subscriber processes.
        tab = self.demo_tab
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(8, weight=1)
        ttk.Label(tab, text="Local application demo",
                  font=("TkDefaultFont", 15, "bold")).grid(
                      row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        ttk.Label(tab, text="This tab starts the real UDP server and subscribers locally.").grid(
            row=1, column=0, columnspan=3, sticky="w")
        self._entry(tab, 2, "Server address", self.host)
        self._entry(tab, 3, "UDP port", self.port)
        self._entry(tab, 4, "Alert message", self.message)
        ttk.Label(tab, text="Priority").grid(row=5, column=0, sticky="w")
        ttk.Combobox(tab, textvariable=self.priority,
                     values=tuple(protocol.VALID_PRIORITIES),
                     state="readonly", width=12).grid(row=5, column=1, sticky="w")

        controls = ttk.LabelFrame(tab, text="Application controls", padding=8)
        controls.grid(row=6, column=0, columnspan=3, sticky="ew", pady=12)
        for column in range(4):
            controls.columnconfigure(column, weight=1)
        self._button(controls, "Start server", self._start_server, 0)
        self._button(controls, "Start C1-C3", self._start_clients, 1)
        self._button(controls, "Send alert", self._send, 2)
        self._button(controls, "Stop all", self._stop_all, 3)

        scenarios = ttk.LabelFrame(tab, text="One-click scenarios", padding=8)
        scenarios.grid(row=7, column=0, columnspan=3, sticky="ew")
        self._button(scenarios, "Run local demo", self._run_local_demo, 0)
        self._button(scenarios, "Test retransmission", self._run_retransmission, 1)
        self._button(scenarios, "Show server/client logs", self._show_processes, 2)

    def _build_d2_tab(self):
        # D2 controls run measurements and prepare commands for Mininet/OVS.
        tab = self.d2_tab
        tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text="D2 controls",
                  font=("TkDefaultFont", 15, "bold")).grid(
                      row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        ttk.Label(tab, text="These buttons run the real experiment utilities or prepare Mininet commands.").grid(
            row=1, column=0, columnspan=3, sticky="w")
        self._entry(tab, 2, "Condition", self.condition)
        self._entry(tab, 3, "Samples", self.count)
        self._entry(tab, 4, "Drop every N (0=none)", self.drop_every)
        controls = ttk.LabelFrame(tab, text="Measurement pipeline", padding=8)
        controls.grid(row=5, column=0, columnspan=3, sticky="ew", pady=12)
        self._button(controls, "Collect CSV", self._collect_results, 0)
        self._button(controls, "Generate graph", self._generate_graph, 1)
        self._button(controls, "Run both conditions", self._run_both_conditions, 2)

        sdn = ttk.LabelFrame(tab, text="SDN / Mininet actions", padding=8)
        sdn.grid(row=6, column=0, columnspan=3, sticky="ew")
        self._button(sdn, "Configure QoS queue", self._setup_qos, 0)
        self._button(sdn, "Link s1-s2 down", lambda: self._show_mininet_command("link s1 s2 down"), 1)
        self._button(sdn, "Link s1-s2 up", lambda: self._show_mininet_command("link s1 s2 up"), 2)
        self._button(sdn, "Show flow command", self._show_flow_command, 3)
        ttk.Label(tab, text=(
            "Use this tab as the main D2 control surface. It launches the "
            "controller/topology and sends commands to the live Mininet CLI. "
            "The normal CLI remains available as a backup."
        ), wraplength=800).grid(row=7, column=0, columnspan=3, sticky="w", pady=12)

        network = ttk.LabelFrame(tab, text="Network demo session", padding=8)
        network.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        for column in range(4):
            network.columnconfigure(column, weight=1)
        self._button(network, "Start Ryu", self._start_ryu, 0)
        self._button(network, "Start Mininet", self._start_mininet, 1)
        self._button(network, "Start D1 services", self._start_mininet_services, 2)
        self._button(network, "Stop network", self._stop_network, 3)

        actions = ttk.LabelFrame(tab, text="D2 actions", padding=8)
        actions.grid(row=9, column=0, columnspan=3, sticky="ew")
        for column in range(4):
            actions.columnconfigure(column, weight=1)
        self._button(actions, "Setup QoS", self._setup_qos, 0)
        self._button(actions, "Create congestion", self._create_congestion, 1)
        self._button(actions, "Link s1-s2 down", lambda: self._send_mininet("link s1 s2 down"), 2)
        self._button(actions, "Link s1-s2 up", lambda: self._send_mininet("link s1 s2 up"), 3)

        inspect = ttk.LabelFrame(tab, text="Mininet command console", padding=8)
        inspect.grid(row=10, column=0, columnspan=3, sticky="ew")
        inspect.columnconfigure(0, weight=1)
        self.mininet_command = tk.StringVar()
        ttk.Entry(inspect, textvariable=self.mininet_command).grid(
            row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(inspect, text="Run command",
                   command=lambda: self._send_mininet(self.mininet_command.get())).grid(
                       row=0, column=1)
        ttk.Button(inspect, text="Show flows",
                   command=lambda: self._send_mininet("sh ovs-ofctl dump-flows s1 -O OpenFlow13")).grid(
                       row=0, column=2, padx=(8, 0))
        ttk.Label(inspect, text="Examples: pingall, dump, link s1 s2 down").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(5, 0))

    def _build_explain_tab(self):
        # This tab gives a short explanation while the user operates the demo.
        text = (
            "LIVE DEMO\n"
            "Start server -> start C1-C3 -> send alert. The server broadcasts a "
            "numbered UDP ALERT and clients return ACK messages.\n\n"
            "RETRANSMISSION\n"
            "Stop one client after registration and send an alert. The server "
            "waits 300 ms, retransmits up to 3 times, then reports failure.\n\n"
            "D2 CONGESTION\n"
            "Background traffic fills a link. Ryu polls OpenFlow counters and "
            "logs CONGESTION_ON/OFF around the configured threshold.\n\n"
            "D2 QOS\n"
            "UDP destination port 9999 identifies emergency traffic. OVS queue "
            "1 is assigned through set_queue:1.\n\n"
            "D2 REROUTING\n"
            "After s1-s2 fails, Ryu clears learned flows. The redundant path "
            "s1-s3-s4 is learned by subsequent packets.\n\n"
            "MEASUREMENTS\n"
            "CSV collection records latency and delivery. The graph compares "
            "conditions. The local script validates the pipeline; Mininet/Ryu "
            "logs are the evidence for actual SDN behavior."
        )
        ttk.Label(self.explain_tab, text="Feature explanations",
                  font=("TkDefaultFont", 15, "bold")).pack(anchor="w", pady=(0, 12))
        box = tk.Text(self.explain_tab, wrap=tk.WORD, height=25)
        box.pack(fill=tk.BOTH, expand=True)
        box.insert("1.0", text)
        box.configure(state=tk.DISABLED)

    def _entry(self, parent, row, label, variable):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=3)

    def _button(self, parent, label, command, column):
        ttk.Button(parent, text=label, command=command).grid(
            row=0, column=column, sticky="ew", padx=4, pady=3)

    def _start_server(self):
        if "server" in self.processes:
            self._log("INFO", "Server is already running")
            return
        self._start_process("server", [sys.executable, "server/server.py"])

    def _start_clients(self):
        for subscriber in ("C1", "C2", "C3"):
            if subscriber not in self.processes:
                self._start_process(
                    subscriber,
                    [sys.executable, "client/client.py", "--id", subscriber,
                     "--server", self.host.get(), "--port", self.port.get()],
                )

    def _run_local_demo(self):
        self._start_server()
        self.root.after(1200, self._start_clients)
        self.root.after(3000, self._send)

    def _start_ryu(self):
        if os.name == "nt":
            self._error("Ryu/Mininet network controls must run in Ubuntu or WSL.")
            return
        if "ryu" in self.processes:
            self._log("INFO", "Ryu is already running")
            return
        self._start_process(
            "ryu",
            [sys.executable, "controller/run_ryu.py", "controller/ryu_app.py",
             "--observe-links", "--verbose"],
        )

    def _start_mininet(self):
        if os.name == "nt":
            self._error("Mininet controls must run in Ubuntu or WSL.")
            return
        if self.mininet_process and self.mininet_process.poll() is None:
            self._log("INFO", "Mininet is already running")
            return
        if shutil.which("sudo") is None:
            self._error("sudo was not found. Start Mininet manually from the CLI.")
            return
        password = self._ask_sudo_password()
        if password is None:
            return
        command = ["sudo", "-S", "-p", "", "python3", "topology/topo.py", "--no-tc"]
        try:
            self.mininet_process = subprocess.Popen(
                command, cwd=ROOT, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except (OSError, ValueError) as exc:
            self._error(f"Could not start Mininet: {exc}")
            return
        try:
            self.mininet_process.stdin.write(password + "\n")
            self.mininet_process.stdin.flush()
        except (OSError, ValueError) as exc:
            self.mininet_process.terminate()
            self.mininet_process = None
            self._error(f"Could not authenticate sudo: {exc}")
            return
        finally:
            password = None
        threading.Thread(
            target=self._read_mininet, args=(self.mininet_process,), daemon=True
        ).start()
        self._log("INFO", "Mininet is starting. Wait for the mininet> prompt.")

    def _ask_sudo_password(self):
        """Ask once without logging or retaining the password."""
        return simpledialog.askstring(
            "Sudo authentication",
            "Enter your WSL/Ubuntu sudo password to start Mininet or configure QoS:",
            parent=self.root,
            show="*",
        )

    def _read_mininet(self, process):
        try:
            for line in process.stdout:
                self.events.put(("LOG", f"[mininet] {line.rstrip()}"))
        except OSError as exc:
            self.events.put(("ERROR", f"Mininet output failed: {exc}"))
        finally:
            self.events.put(("INFO", "Mininet stopped"))
            self.mininet_process = None

    def _send_mininet(self, command):
        command = command.strip()
        if not command:
            self._error("Enter a Mininet command first.")
            return
        process = self.mininet_process
        if not process or process.poll() is not None or process.stdin is None:
            self._error("Mininet is not running. Click Start Mininet first.")
            return
        try:
            process.stdin.write(command + "\n")
            process.stdin.flush()
            self._log("COMMAND", f"mininet> {command}")
        except (OSError, ValueError) as exc:
            self._error(f"Could not send Mininet command: {exc}")

    def _start_mininet_services(self):
        commands = [
            "pingall",
            "hServer sh -c 'python3 server/server.py > /tmp/gui-d2-server.log 2>&1' &",
            "hC1 sh -c 'python3 client/client.py --id C1 --server 10.0.0.1 --port 9999 > /tmp/gui-d2-C1.log 2>&1' &",
            "hC2 sh -c 'python3 client/client.py --id C2 --server 10.0.0.1 --port 9999 > /tmp/gui-d2-C2.log 2>&1' &",
            "hC3 sh -c 'python3 client/client.py --id C3 --server 10.0.0.1 --port 9999 > /tmp/gui-d2-C3.log 2>&1' &",
        ]
        for command in commands:
            self._send_mininet(command)
        self._log("INFO", "D1 services started inside Mininet; D2 controls are ready.")

    def _create_congestion(self):
        self._send_mininet("hNoise1 iperf -s &")
        self._send_mininet("hServer iperf -c 10.0.0.11 -u -b 20M -t 30 &")
        self._log("INFO", "Background traffic started; watch the Ryu output for CONGESTION_ON.")

    def _run_retransmission(self):
        self._log("INFO", "Starting subscribers; stop one client before sending the test alert")
        self._start_server()
        self._start_clients()
        self._log("INFO", "Use 'Stop all' only after observing ACK/retry output")

    def _send(self):
        if self.priority.get() not in protocol.VALID_PRIORITIES:
            self._error("Select a valid priority.")
            return
        try:
            host, port, message = validate_destination(
                self.host.get(), self.port.get(), self.message.get())
        except ValueError as exc:
            self._error(str(exc))
            return
        threading.Thread(
            target=self._send_worker, args=(host, port, message, self.priority.get()),
            daemon=True,
        ).start()

    def _send_worker(self, host, port, message, priority):
        try:
            send_alert(host, port, message, priority)
        except (OSError, ValueError, protocol.ProtocolError) as exc:
            self.events.put(("ERROR", f"Alert failed: {exc}"))
        else:
            self.events.put(("INFO", f"Alert sent to {host}:{port} ({priority})"))

    def _start_process(self, name, command):
        # Keep child processes visible and capture their output in the GUI.
        try:
            process = subprocess.Popen(
                command, cwd=ROOT, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except (OSError, ValueError) as exc:
            self._error(f"Could not start {name}: {exc}")
            return
        self.processes[name] = process
        threading.Thread(target=self._read_process, args=(name, process), daemon=True).start()
        self._log("INFO", f"Started {name}")

    def _read_process(self, name, process):
        # A reader thread prevents a busy server/client from blocking the GUI.
        try:
            for line in process.stdout:
                self.events.put(("LOG", f"[{name}] {line.rstrip()}"))
        except (OSError, ValueError) as exc:
            self.events.put(("ERROR", f"{name} log reader failed: {exc}"))
        finally:
            code = process.poll()
            self.events.put(("INFO", f"{name} stopped (exit={code})"))
            self.events.put(("PROCESS_DONE", name))

    def _stop_all(self):
        for name, process in list(self.processes.items()):
            if process.poll() is None:
                process.terminate()
                self._log("INFO", f"Stopping {name}")
        self.processes.clear()

    def _stop_network(self):
        if self.mininet_process and self.mininet_process.poll() is None:
            try:
                if self.mininet_process.stdin:
                    self.mininet_process.stdin.write("exit\n")
                    self.mininet_process.stdin.flush()
                self.mininet_process.terminate()
            except OSError as exc:
                self._log("ERROR", f"Could not stop Mininet cleanly: {exc}")
        self.mininet_process = None
        self._stop_all()
        self._log("INFO", "Network processes stopped. Run 'sudo mn -c' if cleanup is needed.")

    def _show_processes(self):
        if not self.processes:
            self._log("INFO", "No local processes are running")
            return
        for name, process in self.processes.items():
            self._log("INFO", f"{name}: pid={process.pid}, running={process.poll() is None}")

    def _collect_results(self):
        command = [
            sys.executable, "experiments/collect_results.py",
            "--condition", self.condition.get(),
            "--count", self.count.get(),
            "--drop-every", self.drop_every.get(),
            "--output", f"results/raw/d2_{self.condition.get()}.csv",
        ]
        self._run_command(command)

    def _run_both_conditions(self):
        self.condition.set("baseline")
        self.drop_every.set("0")
        self._collect_results()
        self.condition.set("proposed")
        self.drop_every.set("5")
        self.root.after(100, self._collect_results)

    def _generate_graph(self):
        self._run_command([
            sys.executable, "experiments/generate_graphs.py",
            "--input", "results/raw/d2_baseline.csv", "results/raw/d2_proposed.csv",
        ])

    def _setup_qos(self):
        password = self._ask_sudo_password()
        if password is None:
            return
        self._run_command(
            ["sudo", "-S", "-p", "", "python3", "experiments/setup_qos.py"],
            stdin_data=password,
        )
        password = None

    def _show_flow_command(self):
        self._log("COMMAND", "mininet> sh ovs-ofctl dump-flows s1 -O OpenFlow13")
        self._log("INFO", "Look for udp,tp_dst=9999 and set_queue:1")

    def _show_mininet_command(self, command):
        self._log("COMMAND", f"mininet> {command}")
        self._log("INFO", "Run this command in the active Mininet CLI.")

    def _run_command(self, command, stdin_data=None):
        if isinstance(command, str):
            command = command.split()
        threading.Thread(
            target=self._command_worker,
            args=(command, stdin_data),
            daemon=True,
        ).start()

    def _command_worker(self, command, stdin_data=None):
        try:
            result = subprocess.run(
                command, cwd=ROOT, input=(f"{stdin_data}\n" if stdin_data is not None else None),
                capture_output=True, text=True, timeout=120,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self.events.put(("ERROR", f"Command failed to start: {exc}"))
            return
        output = (result.stdout + result.stderr).strip()
        if output:
            for line in output.splitlines():
                self.events.put(("LOG", f"[command] {line}"))
        self.events.put(("INFO", f"Command exited with code {result.returncode}"))

    def _poll_events(self):
        # Tkinter widgets are updated only on the main thread.
        try:
            while True:
                kind, text = self.events.get_nowait()
                if kind == "PROCESS_DONE":
                    self.processes.pop(text, None)
                    continue
                self._log(kind, text)
                self.status.set(text)
        except queue.Empty:
            pass
        if not self.closing:
            self.root.after(100, self._poll_events)

    def _log(self, level, text):
        self.output.configure(state=tk.NORMAL)
        self.output.insert(tk.END, f"[{level}] {text}\n")
        self.output.see(tk.END)
        self.output.configure(state=tk.DISABLED)

    def _clear_output(self):
        self.output.configure(state=tk.NORMAL)
        self.output.delete("1.0", tk.END)
        self.output.configure(state=tk.DISABLED)

    def _error(self, text):
        self._log("ERROR", text)
        messagebox.showerror("Demo console", text, parent=self.root)

    def _close(self):
        self.closing = True
        self._stop_network()
        self.root.destroy()


def main():
    root = tk.Tk()
    DemoConsole(root)
    root.mainloop()


if __name__ == "__main__":
    main()
