import threading
import requests
from common import logger

class ControllerClient:
    def __init__(self, host, port):
        self.url = f"http://{host}:{port}/api/event"
        self._unavailable = False
        self._lock = threading.Lock()
    
    def post_event(self, event_type, data=None):
        """Send an event to the Ryu controller asynchronously."""
        with self._lock:
            if self._unavailable:
                return

        def _send():
            payload = {"event": event_type}
            if data:
                payload.update(data)
            try:
                response = requests.post(self.url, json=payload, timeout=2.0)
                response.raise_for_status()
                logger.debug("CONTROLLER_CLIENT", f"Sent event {event_type} to controller")
            except requests.RequestException as e:
                with self._lock:
                    already_reported = self._unavailable
                    self._unavailable = True
                if not already_reported:
                    logger.info(
                        "CONTROLLER_CLIENT",
                        f"Controller REST API unavailable at {self.url}; "
                        f"continuing without REST events ({e})",
                    )

        t = threading.Thread(target=_send, daemon=True)
        t.start()
