# File: services/notification_service.py

import threading
from datetime import datetime

# A lock to prevent concurrent access if multiple threads call set_status simultaneously
_notifications_lock = threading.Lock()

# Dictionary for storing statuses:
#   (device, key) -> {
#       "state": "<string>",
#       "message": "<string>",
#       "timestamp": "<datetime object>"
#   }
_notifications = {}


def set_status(device: str, key: str, state: str, message: str = ""):
    """
    Create or update a status for the given (device, key) pair.
    - device: e.g. "ph_probe"
    - key: e.g. "communication"
    - state: e.g. "ok", "error", ...
    - message: optional description

    Now also prevents re-setting the same state & message,
    so we don't spam updates if nothing actually changed.
    """
    with _notifications_lock:
        old_status = _notifications.get((device, key))
        if old_status:
            old_state = old_status["state"]
            old_msg   = old_status["message"]
            # If nothing changed, just return, skipping the update
            if old_state == state and old_msg == message:
                return

        # Otherwise, store (updating timestamp if changed)
        _notifications[(device, key)] = {
            "state": state,
            "message": message,
            "timestamp": datetime.now()
        }

def clear_status(device: str, key: str):
    """
    Remove the notification for (device, key) if it exists.
    """
    with _notifications_lock:
        _notifications.pop((device, key), None)


def get_all_notifications():
    """
    Return a list of all current notifications, each including device, key, state, message, timestamp.
    """
    with _notifications_lock:
        results = []
        for (dev, k), data in _notifications.items():
            results.append({
                "device": dev,
                "key": k,
                "state": data["state"],
                "message": data["message"],
                # Convert datetime to string for easy JSON return
                "timestamp": data["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
            })
        return results
