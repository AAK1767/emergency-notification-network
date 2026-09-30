"""
protocol.py — Message encoding/decoding/validation for the Emergency Notification Network.

Message format:
    TYPE|SEQ|PRIORITY|TIMESTAMP|PAYLOAD

Examples:
    REGISTER|0|NORMAL|1727670000.124|subscriber1
    ALERT|42|HIGH|1727670004.531|FIRE IN BLOCK A
    ACK|42|HIGH|1727670004.781|subscriber1
    UNREGISTER|0|NORMAL|1727670100.220|subscriber1
    HEARTBEAT|0|NORMAL|1727670102.004|subscriber1
"""

import time

DELIMITER = "|"

# Message types
MSG_REGISTER    = "REGISTER"
MSG_UNREGISTER  = "UNREGISTER"
MSG_ALERT       = "ALERT"
MSG_ACK         = "ACK"
MSG_HEARTBEAT   = "HEARTBEAT"

VALID_TYPES = {MSG_REGISTER, MSG_UNREGISTER, MSG_ALERT, MSG_ACK, MSG_HEARTBEAT}

# Priority levels
PRIO_HIGH   = "HIGH"
PRIO_NORMAL = "NORMAL"
PRIO_LOW    = "LOW"

VALID_PRIORITIES = {PRIO_HIGH, PRIO_NORMAL, PRIO_LOW}

# ─────────────────────────────────────────────────────────────────────────────
# Encoding
# ─────────────────────────────────────────────────────────────────────────────

def encode(msg_type: str, seq: int, priority: str, payload: str, timestamp: float = None) -> bytes:
    """Encode a message into bytes ready to send over UDP."""
    if msg_type not in VALID_TYPES:
        raise ValueError(f"Unknown message type: {msg_type}")
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"Unknown priority: {priority}")
    if timestamp is None:
        timestamp = time.time()
    raw = DELIMITER.join([msg_type, str(seq), priority, f"{timestamp:.6f}", payload])
    return raw.encode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Decoding
# ─────────────────────────────────────────────────────────────────────────────

class Message:
    """Represents a decoded protocol message."""
    __slots__ = ("msg_type", "seq", "priority", "timestamp", "payload", "raw")

    def __init__(self, msg_type, seq, priority, timestamp, payload, raw=""):
        self.msg_type  = msg_type
        self.seq       = seq
        self.priority  = priority
        self.timestamp = timestamp
        self.payload   = payload
        self.raw       = raw

    def __repr__(self):
        return (f"Message(type={self.msg_type}, seq={self.seq}, "
                f"priority={self.priority}, payload={self.payload!r})")


class ProtocolError(Exception):
    """Raised when a message cannot be parsed or fails validation."""


def decode(data: bytes) -> Message:
    """Decode raw bytes into a Message.  Raises ProtocolError on failure."""
    try:
        raw = data.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ProtocolError(f"Non-UTF-8 data: {exc}") from exc

    parts = raw.split(DELIMITER, 4)
    if len(parts) != 5:
        raise ProtocolError(f"Expected 5 fields, got {len(parts)}: {raw!r}")

    msg_type, seq_str, priority, ts_str, payload = parts

    if msg_type not in VALID_TYPES:
        raise ProtocolError(f"Unknown message type: {msg_type!r}")

    try:
        seq = int(seq_str)
    except ValueError as exc:
        raise ProtocolError(f"Invalid seq number: {seq_str!r}") from exc

    if priority not in VALID_PRIORITIES:
        raise ProtocolError(f"Unknown priority: {priority!r}")

    try:
        timestamp = float(ts_str)
    except ValueError as exc:
        raise ProtocolError(f"Invalid timestamp: {ts_str!r}") from exc

    return Message(msg_type, seq, priority, timestamp, payload, raw=raw)


# ─────────────────────────────────────────────────────────────────────────────
# Convenience constructors
# ─────────────────────────────────────────────────────────────────────────────

def make_register(subscriber_id: str) -> bytes:
    return encode(MSG_REGISTER, 0, PRIO_NORMAL, subscriber_id)

def make_unregister(subscriber_id: str) -> bytes:
    return encode(MSG_UNREGISTER, 0, PRIO_NORMAL, subscriber_id)

def make_alert(seq: int, text: str, priority: str = PRIO_HIGH) -> bytes:
    return encode(MSG_ALERT, seq, priority, text)

def make_ack(seq: int, subscriber_id: str, priority: str = PRIO_HIGH) -> bytes:
    return encode(MSG_ACK, seq, priority, subscriber_id)

def make_heartbeat(subscriber_id: str) -> bytes:
    return encode(MSG_HEARTBEAT, 0, PRIO_NORMAL, subscriber_id)
