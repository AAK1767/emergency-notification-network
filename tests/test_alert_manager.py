from server.alert_manager import AlertManager


class FakeSocket:
    def __init__(self):
        self.sent = []

    def sendto(self, payload, address):
        self.sent.append((payload, address))


def test_reconnected_subscriber_endpoint_is_used_for_retries():
    sock = FakeSocket()
    manager = AlertManager(sock, ack_timeout=1000, max_retries=3)

    sequence = manager.broadcast_alert(
        "test alert",
        [("C2", ("127.0.0.1", 41000, 0))],
    )
    manager.update_subscriber_endpoint("C2", "127.0.0.1", 42000)

    assert manager.pending_acks[sequence]["C2"]["port"] == 42000
