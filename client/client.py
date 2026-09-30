import sys
import os
import time
import socket
import threading
import json
import argparse
import uuid

# Add root folder to sys.path to resolve 'common'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import protocol, logger

def load_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "config.json")
    with open(config_path, "r") as f:
        return json.load(f)

class EmergencyClient:
    def __init__(self, subscriber_id, server_ip, server_port, config):
        self.sub_id = subscriber_id
        self.config = config
        
        self.server_ip = server_ip or config["client"]["server_ip"]
        self.server_port = server_port or config["client"]["server_port"]
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Bind to OS-assigned port
        self.sock.bind(("0.0.0.0", 0))
        
        self.running = threading.Event()
        self.seen_seqs = set()

    def start(self):
        self.running.set()
        threading.Thread(target=self._recv_loop, daemon=True).start()
        
        self._register()
        
        try:
            while self.running.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info(f"CLIENT:{self.sub_id}", "Interrupted, shutting down...")
        finally:
            self._unregister()
            self.running.clear()
            self.sock.close()

    def _register(self):
        msg = protocol.make_register(self.sub_id)
        self.sock.sendto(msg, (self.server_ip, self.server_port))
        logger.info(f"CLIENT:{self.sub_id}", f"Sent REGISTER to {self.server_ip}:{self.server_port}")

    def _unregister(self):
        msg = protocol.make_unregister(self.sub_id)
        try:
            self.sock.sendto(msg, (self.server_ip, self.server_port))
            logger.info(f"CLIENT:{self.sub_id}", "Sent UNREGISTER to server")
        except OSError:
            pass

    def _recv_loop(self):
        while self.running.is_set():
            try:
                data, addr = self.sock.recvfrom(4096)
                if not data:
                    continue
                receive_ts = time.time()
                
                try:
                    msg = protocol.decode(data)
                except protocol.ProtocolError as e:
                    logger.warn(f"CLIENT:{self.sub_id}", f"Decode error: {e}")
                    continue
                
                if msg.msg_type == protocol.MSG_ALERT:
                    self._handle_alert(msg.seq, msg.payload, msg.priority, receive_ts)
                else:
                    logger.warn(f"CLIENT:{self.sub_id}", f"Unexpected message type: {msg.msg_type}")
                    
            except OSError:
                break
                
    def _handle_alert(self, seq, text, priority, receive_ts):
        # We always ACK, even if duplicate, because the server might have lost our previous ACK
        msg_bytes = protocol.make_ack(seq, self.sub_id, priority)
        self.sock.sendto(msg_bytes, (self.server_ip, self.server_port))
        
        if seq not in self.seen_seqs:
            self.seen_seqs.add(seq)
            logger.success(f"CLIENT:{self.sub_id}", f"ALERT received [SEQ={seq} PRIO={priority}]: {text}")
            logger.debug(f"CLIENT:{self.sub_id}", f"ACK sent for seq={seq}")
        else:
            logger.debug(f"CLIENT:{self.sub_id}", f"Duplicate ALERT seq={seq} received, re-ACKed")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Emergency Notification Client")
    parser.add_argument("--id", type=str, default=None, help="Subscriber ID")
    parser.add_argument("--server", type=str, default=None, help="Server IP")
    parser.add_argument("--port", type=int, default=None, help="Server Port")
    args = parser.parse_args()

    sub_id = args.id or socket.gethostname() or str(uuid.uuid4())[:8]
    
    cfg = load_config()
    client = EmergencyClient(sub_id, args.server, args.port, cfg)
    client.start()
