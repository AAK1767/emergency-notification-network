import threading
import requests
from common import logger

class ControllerClient:
    def __init__(self, host, port):
        self.url = f"http://{host}:{port}/api/event"
    
    def post_event(self, event_type, data=None):
        """Send an event to the Ryu controller asynchronously."""
        def _send():
            payload = {"event": event_type}
            if data:
                payload.update(data)
            try:
                requests.post(self.url, json=payload, timeout=2.0)
                logger.debug("CONTROLLER_CLIENT", f"Sent event {event_type} to controller")
            except Exception as e:
                logger.warn("CONTROLLER_CLIENT", f"Failed to notify controller: {e}")
        
        t = threading.Thread(target=_send, daemon=True)
        t.start()
