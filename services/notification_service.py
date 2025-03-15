# notification_service.py

from datetime import datetime
import threading

# If you import notification_service inside app.py, or vice versa,
# do a local import to avoid circular imports:
#   from app import socketio
# so inside the function, not at the top-level.

_notifications_lock = threading.Lock()
_notifications = {}

def set_status(device: str, key: str, state: str, message: str = ""):
    with _notifications_lock:
        old_status = _notifications.get((device, key))
        if old_status:
            if old_status["state"] == state and old_status["message"] == message:
                # If absolutely nothing changed, skip the update
                return

        _notifications[(device, key)] = {
            "state": state,
            "message": message,
            "timestamp": datetime.now()
        }

    # Once status is actually changed, broadcast an update
    broadcast_notifications_update()

def clear_status(device: str, key: str):
    with _notifications_lock:
        _notifications.pop((device, key), None)

    # After removing a notification, broadcast again
    broadcast_notifications_update()

def broadcast_notifications_update():
    """Convenience method that loads the updated notifications 
    and emits them via Socket.IO to '/status'."""
    from app import socketio  # local import to avoid circular dependency
    all_notifs = get_all_notifications()
    socketio.emit(
        "notifications_update",
        {"notifications": all_notifs},
        namespace="/status"
    )

def get_all_notifications():
    with _notifications_lock:
        results = []
        for (dev, k), data in _notifications.items():
            results.append({
                "device": dev,
                "key": k,
                "state": data["state"],
                "message": data["message"],
                "timestamp": data["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
            })
        return results
