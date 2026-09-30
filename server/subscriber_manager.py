import threading
from common import logger

class SubscriberManager:
    def __init__(self):
        # Dictionary mapping subscriber_id -> (ip, port, last_seen_timestamp)
        self.subscribers = {}
        self.lock = threading.Lock()

    def register(self, sub_id: str, ip: str, port: int, ts: float):
        with self.lock:
            self.subscribers[sub_id] = (ip, int(port), ts)
            logger.info("SERVER:SUB", f"Subscriber {sub_id} registered at {ip}:{port}")
    
    def unregister(self, sub_id: str):
        with self.lock:
            if sub_id in self.subscribers:
                del self.subscribers[sub_id]
                logger.info("SERVER:SUB", f"Subscriber {sub_id} unregistered")

    def update_heartbeat(self, sub_id: str, ts: float):
        with self.lock:
            if sub_id in self.subscribers:
                ip, port, _ = self.subscribers[sub_id]
                self.subscribers[sub_id] = (ip, port, ts)
                logger.debug("SERVER:SUB", f"Heartbeat received from {sub_id}")

    def get_all(self):
        """Returns a list of (subscriber_id, (ip, port, last_seen))."""
        with self.lock:
            return list(self.subscribers.items())
