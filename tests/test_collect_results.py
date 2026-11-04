from experiments.collect_results import ACK_RE, ALERT_RE


def test_ack_lines_captured_with_alert_read():
    lines = [
        "ALERT seq=7 sent to 3 subscribers\n",
        "ACK seq=7 received from C1 (latency=1.20ms)\n",
        "ACK seq=7 received from C2 (latency=1.40ms)\n",
        "ACK seq=7 received from C3 (latency=1.60ms)\n",
    ]

    alert = ALERT_RE.search(lines[0])
    assert alert and int(alert.group(1)) == 7
    acks = {
        match.group(2): float(match.group(3))
        for line in lines[1:]
        if (match := ACK_RE.search(line))
    }
    assert acks == {"C1": 1.2, "C2": 1.4, "C3": 1.6}
