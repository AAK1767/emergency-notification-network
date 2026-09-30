import threading
import sys
import os
import json
import socket
import time

# Add root folder to sys.path to resolve 'common'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import protocol, logger
from server.subscriber_manager import SubscriberManager
from server.alert_manager import AlertManager
from server.controller_client import ControllerClient

def load_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "config.json")
    with open(config_path, "r") as f:
        return json.load(f)

class EmergencyServer:
    def __init__(self, config):
        self.config = config
        self.port = config["server"]["port"]
        self.host = config["server"]["host"]
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Allows quick restart
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        
        c = config["controller"]
        self.controller = ControllerClient(c["ip"], c["rest_port"])
        self.sub_mgr = SubscriberManager()
        
        p = config["protocol"]
        self.alert_mgr = AlertManager(self.sock, p["ack_timeout_ms"], p["max_retries"], self.controller)
        
        self.running = threading.Event()

    def start(self):
        self.running.set()
        threading.Thread(target=self._recv_loop, daemon=True).start()
        threading.Thread(target=self._admin_cli, daemon=True).start()
        logger.info("SERVER", f"Emergency Notification Server listening on {self.host}:{self.port}")
        
        try:
            while self.running.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("SERVER", "Interrupted, shutting down...")
        finally:
            self.running.clear()
            self.sock.close()

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
                    logger.warn("SERVER", f"Decode error from {addr}: {e}")
                    continue
                
                self._handle_msg(msg, addr, receive_ts)
                
            except OSError:
                if self.running.is_set():
                    logger.error("SERVER", "Socket receive error")
                break

    def _handle_msg(self, msg, addr, receive_ts):
        ip, port = addr
        # Typically the client includes its subscriber ID in the payload for REG/ACK
        sub_id = msg.payload.strip()
        
        if msg.msg_type == protocol.MSG_REGISTER:
            self.sub_mgr.register(sub_id, ip, port, receive_ts)
            self.controller.post_event("subscriber_register", {"subscriber_id": sub_id, "ip": ip, "port": port})
            
        elif msg.msg_type == protocol.MSG_UNREGISTER:
            self.sub_mgr.unregister(sub_id)
            self.controller.post_event("subscriber_unregister", {"subscriber_id": sub_id})
            
        elif msg.msg_type == protocol.MSG_ACK:
            self.alert_mgr.handle_ack(msg.seq, sub_id, receive_ts)
            
        elif msg.msg_type == protocol.MSG_HEARTBEAT:
            self.sub_mgr.update_heartbeat(sub_id, receive_ts)
            
        else:
            logger.warn("SERVER", f"Unexpected message type from {sub_id} ({ip}:{port}): {msg.msg_type}")

    def _admin_cli(self):
        while self.running.is_set():
            try:
                # Basic read line
                text = input().strip()
                if not text:
                    continue
                if text.lower() == "exit":
                    self.running.clear()
                    break
                
                subs = self.sub_mgr.get_all()
                if not subs:
                    logger.warn("SERVER:CLI", "No subscribers registered. Alert discarded.")
                else:
                    self.alert_mgr.broadcast_alert(text, subs)
            except EOFError:
                break
            except Exception as e:
                logger.error("SERVER:CLI", f"CLI error: {e}")

if __name__ == "__main__":
    cfg = load_config()
    server = EmergencyServer(cfg)
    server.start()
