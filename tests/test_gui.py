"""Headless tests for GUI validation and alert transport."""

import pytest

from gui import DemoConsole, validate_destination


def test_gui_accepts_valid_alert():
    # Valid form data should be normalized and returned for sending.
    assert validate_destination("127.0.0.1", "9999", "Fire in block A") == (
        "127.0.0.1", 9999, "Fire in block A"
    )


@pytest.mark.parametrize(
    "host,port,message",
    [
        ("not-an-ip", "9999", "test"),
        ("127.0.0.1", "0", "test"),
        ("127.0.0.1", "9999", ""),
    ],
)
def test_gui_rejects_invalid_alert(host, port, message):
    # Invalid form data must be stopped before a socket is opened.
    with pytest.raises(ValueError):
        validate_destination(host, port, message)


@pytest.mark.parametrize(
    "line,channel",
    [
        ("2026 [CLIENT:C1] Sent REGISTER", "Clients"),
        ("2026 [SERVER:SUB] Subscriber C1 registered", "Application"),
        ("2026 [CONTROLLER_CLIENT] Sent event subscriber_register", "Application"),
        ("mininet> pingall", "Mininet"),
    ],
)
def test_mininet_log_channels(line, channel):
    assert DemoConsole._classify_mininet_log(line) == channel
