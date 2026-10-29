#!/usr/bin/env python3
"""Simple emergency alert dashboard.

Run from the repository root with:
    python gui.py

The dashboard is an admin client. It does not replace the UDP server or
subscriber clients; it sends the same ALERT messages as send_alert.py.
"""

import ipaddress
import json
import os
import queue
import socket
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from common import protocol


ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "config", "config.json")


def load_defaults():
    """Load GUI defaults while returning actionable errors to the caller."""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as handle:
            config = json.load(handle)
        server = config["server"]
        host = str(server["host"])
        # 0.0.0.0 is a bind address, not a destination address.
        if host in {"0.0.0.0", "::"}:
            host = "127.0.0.1" if host == "0.0.0.0" else "::1"
        return host, int(server["port"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read config/config.json: {exc}") from exc


def validate_destination(host, port_text, message):
    """Validate form values and return an IPv4/IPv6 host and integer port."""
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
    """Send one alert and close the socket reliably."""
    payload = protocol.make_alert(0, message, priority)
    with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET,
                       socket.SOCK_DGRAM) as sock:
        sock.settimeout(3)
        sock.sendto(payload, (host, port))


class EmergencyDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Emergency Notification Dashboard")
        self.root.minsize(620, 430)
        self.results = queue.Queue()
        self.sending = False

        try:
            default_host, default_port = load_defaults()
        except RuntimeError as exc:
            default_host, default_port = "127.0.0.1", 9999
            self.startup_error = str(exc)
        else:
            self.startup_error = None

        self.host = tk.StringVar(value=default_host)
        self.port = tk.StringVar(value=str(default_port))
        self.priority = tk.StringVar(value=protocol.PRIO_HIGH)
        self.status = tk.StringVar(value="Ready")
        self._build()
        self.root.after(100, self._poll_results)
        if self.startup_error:
            self._log(f"Configuration warning: {self.startup_error}")

    def _build(self):
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)

        ttk.Label(frame, text="Emergency Alert Dashboard",
                  font=("TkDefaultFont", 16, "bold")).grid(
                      row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))
        ttk.Label(frame, text="Server address").grid(row=1, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.host).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(10, 0))
        ttk.Label(frame, text="UDP port").grid(row=2, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.port, width=12).grid(
            row=2, column=1, sticky="w", padx=(10, 0))
        ttk.Label(frame, text="Priority").grid(row=3, column=0, sticky="w")
        ttk.Combobox(frame, textvariable=self.priority,
                     values=(protocol.PRIO_HIGH, protocol.PRIO_NORMAL, protocol.PRIO_LOW),
                     state="readonly", width=12).grid(
                         row=3, column=1, sticky="w", padx=(10, 0))

        ttk.Label(frame, text="Alert message").grid(
            row=4, column=0, sticky="nw", pady=(12, 0))
        self.message = tk.Text(frame, height=5, wrap=tk.WORD)
        self.message.grid(row=4, column=1, columnspan=2, sticky="nsew",
                          padx=(10, 0), pady=(12, 0))
        self.message.bind("<Control-Return>", lambda _event: self._send())

        self.send_button = ttk.Button(frame, text="Send emergency alert",
                                      command=self._send)
        self.send_button.grid(row=5, column=1, sticky="w", pady=12, padx=(10, 0))
        ttk.Label(frame, textvariable=self.status).grid(
            row=5, column=2, sticky="e", pady=12)

        ttk.Label(frame, text="Activity log").grid(
            row=6, column=0, sticky="nw")
        self.log = tk.Text(frame, height=8, state=tk.DISABLED, wrap=tk.WORD)
        self.log.grid(row=6, column=1, columnspan=2, sticky="nsew",
                      padx=(10, 0))
        frame.rowconfigure(6, weight=1)

    def _send(self):
        if self.sending:
            return
        try:
            host, port, message = validate_destination(
                self.host.get(), self.port.get(), self.message.get("1.0", tk.END))
            priority = self.priority.get()
            if priority not in protocol.VALID_PRIORITIES:
                raise ValueError("Select a valid priority.")
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror("Invalid alert", str(exc), parent=self.root)
            self.status.set("Input error")
            return

        self.sending = True
        self.send_button.configure(state=tk.DISABLED)
        self.status.set("Sending...")
        threading.Thread(
            target=self._send_worker,
            args=(host, port, message, priority),
            daemon=True,
        ).start()

    def _send_worker(self, host, port, message, priority):
        try:
            send_alert(host, port, message, priority)
        except (OSError, ValueError, protocol.ProtocolError) as exc:
            self.results.put(("error", f"Alert failed: {exc}"))
        else:
            self.results.put(("success", f"Alert sent to {host}:{port} ({priority})"))

    def _poll_results(self):
        try:
            while True:
                kind, text = self.results.get_nowait()
                self.sending = False
                self.send_button.configure(state=tk.NORMAL)
                self.status.set("Sent" if kind == "success" else "Failed")
                self._log(text)
                if kind == "error":
                    messagebox.showerror("Send failed", text, parent=self.root)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_results)

    def _log(self, text):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)


def main():
    root = tk.Tk()
    EmergencyDashboard(root)
    root.mainloop()


if __name__ == "__main__":
    main()
