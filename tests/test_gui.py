"""Headless tests for GUI validation and alert transport."""

import pytest

from gui import validate_destination


def test_gui_accepts_valid_alert():
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
    with pytest.raises(ValueError):
        validate_destination(host, port, message)
