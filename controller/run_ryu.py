#!/usr/bin/env python3
"""Start Ryu 4.34 with Python 3.11-compatible Eventlet behavior."""

import eventlet.wsgi

# Ryu 4.34 imports this removed Eventlet sentinel unconditionally.
if not hasattr(eventlet.wsgi, "ALREADY_HANDLED"):
    eventlet.wsgi.ALREADY_HANDLED = None

from ryu.cmd.manager import main


if __name__ == "__main__":
    main()
