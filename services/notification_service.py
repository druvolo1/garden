from datetime import datetime, timedelta
import threading
import requests

# Adjust import if you use your own settings load function
from utils.settings_utils import load_settings

_notifications_lock = threading.Lock()
_notifications = {}

# Tracking structure for error states & counts
__tracking = {}  
# {
#    (device, key): {
#       "last_state": "ok"/"error",
#       "error_timestamps": [datetime objects within last 24 hours],
#       "muted_until": datetime or None
#    }
# }

def set_status(device: str, key: str, state: str, message: str = ""):
    with _notifications_lock:
        old_status = _notifications.get((device, key))
        old_state = old_status["state"] if old_status else "ok"
        _notifications[(device, key)] = {
            "state": state,
            "message": message,
            "timestamp": datetime.now()
        }

    # Added: handle transitions and possibly send notifications
    handle_notification_transition(device, key, old_state, state, message)

    # Broadcast to the UI
    broadcast_notifications_update()

def clear_status(device: str, key: str):
    with _notifications_lock:
        _notifications.pop((device, key), None)
        __tracking.pop((device, key), None)

    broadcast_notifications_update()

def broadcast_notifications_update():
    """Emit the updated notifications via Socket.IO."""
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

def handle_notification_transition(device: str, key: str, old_state: str, new_state: str, message: str):
    now = datetime.now()

    # Grab or create the tracking object
    with _notifications_lock:
        track = __tracking.get((device, key), {
            "last_state": "ok",
            "error_timestamps": [],
            "muted_until": None
        })

    old_state = old_state.lower()
    new_state = new_state.lower()

    # ----- ERROR → OK transition -----
    if old_state == "error" and new_state == "ok":
        # We’ll send a one-time "cleared" notification here:
        _send_telegram_and_discord(
            f"Device={device}, Key={key}\nIssue cleared; now back to OK."
        )

        # Reset counters and mute
        track["error_timestamps"].clear()
        track["muted_until"] = None

    # ----- OK → ERROR transition -----
    elif old_state != "error" and new_state == "error":
        # If we are muted and still within the mute period, skip
        if track["muted_until"] and now < track["muted_until"]:
            pass
        else:
            # Clean out old timestamps > 24h
            track["error_timestamps"] = [
                t for t in track["error_timestamps"]
                if (now - t) < timedelta(hours=24)
            ]
            # Add new error trigger time
            track["error_timestamps"].append(now)

            # If hitting 5th time, append the muting message + set mute
            if len(track["error_timestamps"]) == 5:
                message += "\n[muting this notification for 24 hours due to excessive triggering]"
                track["muted_until"] = now + timedelta(hours=24)

            # Send the “ok → error” alert
            _send_telegram_and_discord(
                f"Device={device}, Key={key}\n{message}"
            )

    # Update tracking
    track["last_state"] = new_state
    with _notifications_lock:
        __tracking[(device, key)] = track

def _send_telegram_and_discord(alert_text: str):
    """
    Helper: loads Telegram/Discord settings and sends if enabled.
    """
    cfg = load_settings()

    # --- Telegram ---
    if cfg.get("telegram_enabled"):
        bot_token = cfg.get("telegram_bot_token", "").strip()
        chat_id = cfg.get("telegram_chat_id", "").strip()
        if bot_token and chat_id:
            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {"chat_id": chat_id, "text": alert_text}
                requests.post(url, json=payload, timeout=10)
            except Exception as ex:
                print(f"[ERROR] Telegram send failed: {ex}")

    # --- Discord ---
    if cfg.get("discord_enabled"):
        webhook_url = cfg.get("discord_webhook_url", "").strip()
        if webhook_url:
            try:
                requests.post(webhook_url, json={"content": alert_text}, timeout=10)
            except Exception as ex:
                print(f"[ERROR] Discord send failed: {ex}")
