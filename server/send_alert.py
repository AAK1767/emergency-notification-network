#!/usr/bin/env python3
"""
send_alert.py — Standalone script to send an alert to the Emergency Server.

Usage:
    python3 send_alert.py --server 10.0.0.1 --port 9999 --message "FIRE IN BLOCK A"
    python3 send_alert.py --server 10.0.0.1 --port 9999  # interactive mode

Can be run from hAdmin in Mininet or from any host that can reach the server.
"""

import sys
import os
import socket
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import protocol, logger


def send_alert(server_ip, server_port, message, priority=protocol.PRIO_HIGH):
    """Send a single alert trigger to the notification server."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    msg = protocol.make_alert(0, message, priority)  # seq=0 => server assigns real seq
    sock.sendto(msg, (server_ip, server_port))
    logger.info("ADMIN", f"Alert sent to {server_ip}:{server_port}: {message}")
    sock.close()


def main():
    parser = argparse.ArgumentParser(description="Emergency Alert Sender")
    parser.add_argument("--server", type=str, default="10.0.0.1", help="Server IP")
    parser.add_argument("--port", type=int, default=9999, help="Server UDP port")
    parser.add_argument("--message", "-m", type=str, default=None,
                        help="Alert message (omit for interactive mode)")
    parser.add_argument("--priority", "-p", type=str, default="HIGH",
                        choices=["HIGH", "NORMAL", "LOW"])
    args = parser.parse_args()

    if args.message:
        send_alert(args.server, args.port, args.message, args.priority)
    else:
        print("Emergency Alert Sender — Interactive Mode")
        print("Type alert messages, press Enter to send. Ctrl-C to quit.\n")
        try:
            while True:
                text = input("ALERT> ").strip()
                if text:
                    send_alert(args.server, args.port, text, args.priority)
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")


if __name__ == "__main__":
    main()
