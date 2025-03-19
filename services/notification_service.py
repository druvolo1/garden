from datetime import datetime, timedelta
import threading
import requests

from utils.settings_utils import load_settings  # Adjust if needed

_notifications_lock = threading.Lock()
_notifications = {}  # Current "snapshot" of device/key states

# Each entry in __tracking is keyed by (device, key), e.g. ("pump1", "overheating"):
# {
#   "last_state": str,  # "ok" or "error"
#   "error_timestamps": [datetime objects within the past 24h],
#   "muted_until": datetime or None
# }
__tracking = {}


def set_status(device: str, key: str, state: str, message: str = ""):
    """
    Called whenever we have a new state for (device, key).
    We'll record the state in _notifications, then run handle_notification_transition
    to determine if we should notify or not.
    """
    with _notifications_lock:
        old_status = _notifications.get((device, key))
        old_state = old_status["state"] if old_status else "ok"

        # Update the current snapshot
        _notifications[(device, key)] = {
            "state": state,
            "message": message,
            "timestamp": datetime.now()
        }

    # Check for transitions, possibly send notifications
    handle_notification_transition(device, key, old_state, state, message)

    # Broadcast the updated notifications to the UI (if not muted by debug settings)
    broadcast_notifications_update()


def clear_status(device: str, key: str):
    """
    Called by the web UI "Clear" button to remove a notification and reset counters.
    """
    with _notifications_lock:
        _notifications.pop((device, key), None)
        __tracking.pop((device, key), None)
        print(f"[DEBUG] clear_status called for (device={device}, key={key}); reset counters & removed from tracking")

    broadcast_notifications_update()


def broadcast_notifications_update():
    """
    Emits the updated notifications to the UI using Socket.IO,
    unless 'notifications' debug toggle is OFF.
    """
    from api.debug import load_debug_settings  # ADJUST: your actual path
    from app import socketio  # local import to avoid circular dependency

    debug_cfg = load_debug_settings()
    if not debug_cfg.get("notifications", True):
        print("[DEBUG] Notifications are turned OFF in debug settings, skipping broadcast.")
        return

    all_notifs = get_all_notifications()
    socketio.emit(
        "notifications_update",
        {"notifications": all_notifs},
        namespace="/status"
    )


def get_all_notifications():
    """
    Returns a list of all current notifications from _notifications
    (device, key, state, message, timestamp).
    """
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
    old_state = old_state.lower()
    new_state = new_state.lower()

    with _notifications_lock:
        track = __tracking.get((device, key), {
            "last_state": "ok",
            "error_timestamps": [],
            "muted_until": None
        })

    print(f"[DEBUG] handle_notification_transition device={device}, key={key}")
    print(f"        old_state={old_state}, new_state={new_state}, track={track}")

    # -------- ERROR -> OK transition --------
    if old_state == "error" and new_state == "ok":
        # If we're currently muted, skip sending "cleared"
        if track["muted_until"] and now < track["muted_until"]:
            print(f"[DEBUG] Currently muted until {track['muted_until']} - skipping 'cleared' notification.")
        else:
            print("[DEBUG] Transition: ERROR -> OK - sending 'cleared' notification.")
            _send_telegram_and_discord(f"Device={device}, Key={key}\nIssue cleared; now OK.")
        # Notice: we do NOT clear timestamps or unmute.
        # They stay until 24h passes or the user manually clears.

    # -------- OK -> ERROR transition --------
    elif old_state != "error" and new_state == "error":
        if track["muted_until"] and now < track["muted_until"]:
            print(f"[DEBUG] Currently muted until {track['muted_until']} - skipping ERROR notification.")
        else:
            # Remove stale timestamps older than 24h
            original_count = len(track["error_timestamps"])
            track["error_timestamps"] = [
                t for t in track["error_timestamps"]
                if (now - t) < timedelta(hours=24)
            ]
            removed_count = original_count - len(track["error_timestamps"])
            if removed_count > 0:
                print(f"[DEBUG] Removed {removed_count} old error timestamps (>24h).")

            # Append this new error occurrence
            track["error_timestamps"].append(now)
            new_count = len(track["error_timestamps"])
            print(f"[DEBUG] error_timestamps has {new_count} in last 24h: {track['error_timestamps']}")

            # If this is the 5th error, set a 24h mute
            if new_count == 5:
                message += "\n[muting this notification for 24 hours due to excessive triggering]"
                track["muted_until"] = now + timedelta(hours=24)
                print(f"[DEBUG] Setting muted_until to {track['muted_until']}")

            print("[DEBUG] Sending notification to Telegram/Discord.")
            _send_telegram_and_discord(f"Device={device}, Key={key}\n{message}")

    # Update last_state
    track["last_state"] = new_state
    with _notifications_lock:
        __tracking[(device, key)] = track



def _send_telegram_and_discord(alert_text: str):
    """
    Helper function to actually send the notification to Telegram and/or Discord if enabled.
    """
    cfg = load_settings()

    print(f"[DEBUG] _send_telegram_and_discord called with text:\n{alert_text}")

    # --- Telegram ---
    if cfg.get("telegram_enabled"):
        bot_token = cfg.get("telegram_bot_token", "").strip()
        chat_id = cfg.get("telegram_chat_id", "").strip()
        if bot_token and chat_id:
            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {"chat_id": chat_id, "text": alert_text}
                resp = requests.post(url, json=payload, timeout=10)
                print(f"[DEBUG] Telegram POST => {resp.status_code}")
            except Exception as ex:
                print(f"[ERROR] Telegram send failed: {ex}")
        else:
            print("[DEBUG] Telegram enabled but missing bot_token/chat_id, skipping...")

    # --- Discord ---
    if cfg.get("discord_enabled"):
        webhook_url = cfg.get("discord_webhook_url", "").strip()
        if webhook_url:
            try:
                resp = requests.post(webhook_url, json={"content": alert_text}, timeout=10)
                print(f"[DEBUG] Discord POST => {resp.status_code}")
            except Exception as ex:
                print(f"[ERROR] Discord send failed: {ex}")
        else:
            print("[DEBUG] Discord enabled but missing webhook_url, skipping...")
