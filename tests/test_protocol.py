"""
test_protocol.py — Unit tests for common.protocol.
Run with:
    python -m pytest tests/test_protocol.py -v
"""

import sys, os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from common import protocol

# ──────────────────────────────────────────────────────────────────────────────
# Encoding tests
# ──────────────────────────────────────────────────────────────────────────────

class TestEncode:
    def test_encode_register_bytes(self):
        msg = protocol.make_register("C1")
        assert isinstance(msg, bytes)

    def test_encode_alert_roundtrip(self):
        raw = protocol.make_alert(42, "FIRE IN BLOCK A", protocol.PRIO_HIGH)
        decoded = protocol.decode(raw)
        assert decoded.msg_type == protocol.MSG_ALERT
        assert decoded.seq == 42
        assert decoded.priority == protocol.PRIO_HIGH
        assert decoded.payload == "FIRE IN BLOCK A"

    def test_encode_ack_roundtrip(self):
        raw = protocol.make_ack(42, "C1", protocol.PRIO_HIGH)
        decoded = protocol.decode(raw)
        assert decoded.msg_type == protocol.MSG_ACK
        assert decoded.seq == 42
        assert decoded.payload == "C1"

    def test_encode_register_roundtrip(self):
        raw = protocol.make_register("C2")
        decoded = protocol.decode(raw)
        assert decoded.msg_type == protocol.MSG_REGISTER
        assert decoded.payload == "C2"

    def test_encode_unregister_roundtrip(self):
        raw = protocol.make_unregister("C2")
        decoded = protocol.decode(raw)
        assert decoded.msg_type == protocol.MSG_UNREGISTER
        assert decoded.payload == "C2"

    def test_encode_heartbeat_roundtrip(self):
        raw = protocol.make_heartbeat("C3")
        decoded = protocol.decode(raw)
        assert decoded.msg_type == protocol.MSG_HEARTBEAT

    def test_invalid_type_raises_value_error(self):
        with pytest.raises(ValueError):
            protocol.encode("BAD_TYPE", 0, protocol.PRIO_NORMAL, "x")

    def test_invalid_priority_raises_value_error(self):
        with pytest.raises(ValueError):
            protocol.encode(protocol.MSG_ALERT, 1, "URGENT", "x")

    def test_timestamp_close_to_now(self):
        before = time.time()
        raw = protocol.make_alert(1, "Test")
        after = time.time()
        msg = protocol.decode(raw)
        assert before <= msg.timestamp <= after


# ──────────────────────────────────────────────────────────────────────────────
# Decoding / error-path tests
# ──────────────────────────────────────────────────────────────────────────────

class TestDecode:
    def test_wrong_field_count(self):
        with pytest.raises(protocol.ProtocolError):
            protocol.decode(b"ALERT|42|HIGH|1700000000.0")

    def test_unknown_type(self):
        with pytest.raises(protocol.ProtocolError):
            protocol.decode(b"BOGUS|0|NORMAL|1700000000.0|payload")

    def test_invalid_seq_non_integer(self):
        with pytest.raises(protocol.ProtocolError):
            protocol.decode(b"ALERT|abc|HIGH|1700000000.0|payload")

    def test_invalid_timestamp(self):
        with pytest.raises(protocol.ProtocolError):
            protocol.decode(b"ALERT|1|HIGH|not-a-float|payload")

    def test_invalid_priority(self):
        with pytest.raises(protocol.ProtocolError):
            protocol.decode(b"ALERT|1|URGENT|1700000000.0|payload")

    def test_non_utf8_raises(self):
        with pytest.raises(protocol.ProtocolError):
            protocol.decode(b"\xff\xfe")

    def test_pipe_in_payload_preserved(self):
        """Payload may contain content with pipe characters – only 5 fields split."""
        raw = protocol.encode(protocol.MSG_ALERT, 1, protocol.PRIO_HIGH, "part1|part2|extra")
        msg = protocol.decode(raw)
        assert msg.payload == "part1|part2|extra"


# ──────────────────────────────────────────────────────────────────────────────
# Local end-to-end: server + client in-process
# ──────────────────────────────────────────────────────────────────────────────

class TestLocalE2E:
    """
    Starts a minimal server and one client in the same process to verify the
    register → alert → ACK flow without Mininet/Ryu.
    """

    def test_register_alert_ack(self):
        import socket
        import threading
        import queue

        received = queue.Queue()

        SERVER_PORT = 59999   # high ephemeral port, unlikely to clash
        SERVER_IP   = "127.0.0.1"

        # ── Tiny mock server ─────────────────────────────────────────────
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((SERVER_IP, SERVER_PORT))
        server_sock.settimeout(3.0)

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_sock.bind(("0.0.0.0", 0))
        client_sock.settimeout(3.0)
        _, client_port = client_sock.getsockname()

        def client_thread():
            # 1) Send REGISTER
            client_sock.sendto(protocol.make_register("TestClient"), (SERVER_IP, SERVER_PORT))
            # 2) Wait for ALERT
            data, _ = client_sock.recvfrom(4096)
            msg = protocol.decode(data)
            received.put(("alert", msg.seq, msg.payload))
            # 3) Send ACK
            client_sock.sendto(protocol.make_ack(msg.seq, "TestClient"), (SERVER_IP, SERVER_PORT))

        # ── Run client in background ──────────────────────────────────────
        ct = threading.Thread(target=client_thread, daemon=True)
        ct.start()

        # ── Server receives REGISTER ──────────────────────────────────────
        data, addr = server_sock.recvfrom(4096)
        reg = protocol.decode(data)
        assert reg.msg_type == protocol.MSG_REGISTER
        assert reg.payload == "TestClient"

        # ── Server sends ALERT ───────────────────────────────────────────
        server_sock.sendto(protocol.make_alert(1, "TEST ALERT"), addr)

        # ── Server receives ACK ───────────────────────────────────────────
        data, _ = server_sock.recvfrom(4096)
        ack = protocol.decode(data)
        assert ack.msg_type == protocol.MSG_ACK
        assert ack.seq == 1
        assert ack.payload == "TestClient"

        ct.join(timeout=5)

        # Verify client side received the alert
        item = received.get(timeout=3)
        assert item == ("alert", 1, "TEST ALERT")

        server_sock.close()
        client_sock.close()
