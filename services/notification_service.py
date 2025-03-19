from datetime import datetime, timedelta
import threading

import requests
# If your code uses: from utils.settings_utils import load_settings
# or from settings import load_settings, adapt accordingly:
from utils.settings_utils import load_settings

_notifications_lock = threading.Lock()
_notifications = {}

# NEW: Tracking structure to handle transitions and counts
__tracking = {}  # keyed by (device, key), value is a dict:
# {
#    "last_state": str,  # e.g. "ok" or "error"
#    "error_timestamps": [list of datetimes within last 24 hours],
#    "muted_until": datetime or None
# }

def set_status(device: str, key: str, state: str, message: str = ""):
    """
    Main entry point for updating a device/key notification status.
    - We add logic to detect when we transition from "ok" to "error" (so we can notify).
    - We also track how many times it triggered in the last 24 hours, and potentially mute.
    """
    with _notifications_lock:
        old_status = _notifications.get((device, key))
        old_state = old_status["state"] if old_status else "ok"  # default "ok" if none
        _notifications[(device, key)] = {
            "state": state,
            "message": message,
            "timestamp": datetime.now()
        }

    # Handle counting logic and possible transitions
    handle_notification_transition(device, key, old_state, state, message)

    # Once status is changed, broadcast an update to the UI via Socket.IO
    broadcast_notifications_update()


def clear_status(device: str, key: str):
    with _notifications_lock:
        _notifications.pop((device, key), None)

    # Also clear the tracking so we don't remain muted or keep old counters
    with _notifications_lock:
        __tracking.pop((device, key), None)

    broadcast_notifications_update()


def broadcast_notifications_update():
    """Emit the latest notifications via Socket.IO to /status."""
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
    """
    Encapsulate the logic for:
      - Only triggering a new alert if going from "ok"->"error"
      - Checking if we are currently muted
      - Counting how many times in last 24 hrs
      - Possibly muting if triggered more than 4 times
      - Clearing counters if going from "error"->"ok"
    """
    now = datetime.now()
    with _notifications_lock:
        track = __tracking.get((device, key), {
            "last_state": "ok",
            "error_timestamps": [],
            "muted_until": None
        })

    # If going from error -> ok, clear counters
    if track["last_state"] == "error" and new_state.lower() == "ok":
        track["error_timestamps"].clear()
        track["muted_until"] = None

    # If going from ok -> error, decide whether to send or skip
    elif track["last_state"] != "error" and new_state.lower() == "error":
        # Check if we are muted
        if track["muted_until"] and now < track["muted_until"]:
            # We are still within the mute period, do nothing
            pass
        else:
            # Clean out old timestamps more than 24h ago
            track["error_timestamps"] = [
                t for t in track["error_timestamps"]
                if (now - t) < timedelta(hours=24)
            ]
            # Add this new trigger time
            track["error_timestamps"].append(now)

            # If we are about to trigger for the 5th time in 24h, we do a special message
            if len(track["error_timestamps"]) == 5:
                message += "\n[muting this notification for 24 hours due to excessive triggering]"
                # We'll set muted_until to 24h from now
                track["muted_until"] = now + timedelta(hours=24)

            # Actually send the Telegram/Discord alerts
            _send_telegram_and_discord(f"Device={device}, Key={key}\n{message}")

    # Update last_state in either case
    track["last_state"] = new_state.lower()

    with _notifications_lock:
        __tracking[(device, key)] = track


def _send_telegram_and_discord(alert_text: str):
    """
    Helper that looks at settings to see if Telegram/Discord are enabled,
    then sends alerts if so.
    """
    # Load from settings
    cfg = load_settings()

    # --- Send Telegram if enabled ---
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

    # --- Send Discord if enabled ---
    if cfg.get("discord_enabled"):
        webhook_url = cfg.get("discord_webhook_url", "").strip()
        if webhook_url:
            try:
                # Discord webhook expects JSON with "content" key
                requests.post(webhook_url, json={"content": alert_text}, timeout=10)
            except Exception as ex:
                print(f"[ERROR] Discord send failed: {ex}")
