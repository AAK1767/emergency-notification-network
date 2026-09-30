import time
import threading
from common import protocol, logger
from server.controller_client import ControllerClient

class AlertManager:
    def __init__(self, sender_socket, ack_timeout, max_retries, controller=None):
        self.sock = sender_socket
        self.ack_timeout_ms = ack_timeout
        self.max_retries = max_retries
        self.seq_counter = 1
        self.lock = threading.Lock()
        
        # controller integration
        self.controller = controller
        
        # seq -> {sub_id: {'retries': 0, 'ip': ip, 'port': port, 'send_ts': ts, 'text': text, 'prio': priority}}
        self.pending_acks = {}
        
        # (seq, sub_id, send_ts, receive_ts, latency_ms)
        self.latencies = []

    def broadcast_alert(self, text, subscribers, priority=protocol.PRIO_HIGH):
        with self.lock:
            seq = self.seq_counter
            self.seq_counter += 1
            
            if self.controller:
                self.controller.post_event("emergency_alert", {"sequence": seq, "priority": priority})
                
            msg_bytes = protocol.make_alert(seq, text, priority)
            
            pending = {}
            send_ts = time.time()
            for sub_id, (ip, port, _) in subscribers:
                try:
                    self.sock.sendto(msg_bytes, (ip, port))
                    pending[sub_id] = {
                        'retries': 0, 'ip': ip, 'port': port, 
                        'send_ts': send_ts, 'text': text, 'prio': priority
                    }
                except Exception as e:
                    logger.error("SERVER:ALERT", f"Failed to send to {sub_id} ({ip}:{port}): {e}")
            
            if pending:
                self.pending_acks[seq] = pending
                t = threading.Thread(target=self._retry_loop, args=(seq,), daemon=True)
                t.start()
            
            logger.info("SERVER:ALERT", f"ALERT seq={seq} sent to {len(pending)} subscribers")
            return seq

    def handle_ack(self, seq, sub_id, receive_ts):
        with self.lock:
            if seq in self.pending_acks and sub_id in self.pending_acks[seq]:
                send_ts = self.pending_acks[seq][sub_id]['send_ts']
                latency_ms = (receive_ts - send_ts) * 1000
                self.latencies.append((seq, sub_id, send_ts, receive_ts, latency_ms))
                
                logger.info("SERVER:ALERT", f"ACK seq={seq} received from {sub_id} (latency={latency_ms:.2f}ms)")
                
                del self.pending_acks[seq][sub_id]
                if not self.pending_acks[seq]:
                    del self.pending_acks[seq]
                    logger.debug("SERVER:ALERT", f"All ACKs received for ALERT seq={seq}")

    def _retry_loop(self, seq):
        timeout_s = self.ack_timeout_ms / 1000.0
        while True:
            time.sleep(timeout_s)
            with self.lock:
                if seq not in self.pending_acks:
                    break
                
                pending = self.pending_acks[seq]
                to_remove = []
                for sub_id, info in pending.items():
                    info['retries'] += 1
                    if info['retries'] > self.max_retries:
                        logger.error("SERVER:ALERT", f"ALERT seq={seq} delivery failed for {sub_id} after {self.max_retries} retries")
                        to_remove.append(sub_id)
                    else:
                        logger.warn("SERVER:ALERT", f"Retransmitting ALERT seq={seq} to {sub_id} (retry {info['retries']})")
                        try:
                            msg_bytes = protocol.make_alert(seq, info['text'], info['prio'])
                            self.sock.sendto(msg_bytes, (info['ip'], info['port']))
                        except Exception as e:
                            logger.error("SERVER:ALERT", f"Failed retransmit to {sub_id}: {e}")
                
                for sub_id in to_remove:
                    del pending[sub_id]
                
                if not pending:
                    del self.pending_acks[seq]
                    break
