from datetime import datetime, timedelta
import threading
import requests

from utils.settings_utils import load_settings  # Adjust if needed

_notifications_lock = threading.Lock()
_notifications = {}

__tracking = {}
# {
#   (device, key): {
#       "last_state": "ok"/"error",
#       "error_timestamps": [datetimes within last 24 hours],
#       "muted_until": datetime or None
#   }
# }


def set_status(device: str, key: str, state: str, message: str = ""):
    with _notifications_lock:
        old_status = _notifications.get((device, key))
        old_state = old_status["state"] if old_status else "ok"
        print(f"[DEBUG] set_status for device={device}, key={key}, old_state={old_state}, new_state={state}")
        
        _notifications[(device, key)] = {
            "state": state,
            "message": message,
            "timestamp": datetime.now()
        }

    # Let’s debug right before we call the transition handler
    handle_notification_transition(device, key, old_state, state, message)

    # Then broadcast to the UI
    broadcast_notifications_update()


def clear_status(device: str, key: str):
    with _notifications_lock:
        _notifications.pop((device, key), None)
        __tracking.pop((device, key), None)
        print(f"[DEBUG] clear_status called for device={device}, key={key}; removed from tracking")

    broadcast_notifications_update()

def broadcast_notifications_update():
    # Import your debug settings loader. Adjust import path as needed.
    from api.debug import load_debug_settings
    from app import socketio  # local import to avoid circular dependency
    
    # Check if notifications are enabled in debug settings
    debug_cfg = load_debug_settings()
    if not debug_cfg.get("notifications", True):
        print("[DEBUG] Notifications are turned OFF in debug settings, skipping broadcast.")
        return

    # If still on, proceed with the normal broadcast
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
        print("[DEBUG] Transition: ERROR -> OK")
        # Send a “cleared” notification
        _send_telegram_and_discord(f"Device={device}, Key={key}\nIssue cleared; now OK.")

        # Reset counters / unmute
        track["error_timestamps"].clear()
        track["muted_until"] = None
        print("[DEBUG] Cleared error_timestamps and un-muted this device/key.")

    # -------- OK -> ERROR transition --------
    elif old_state != "error" and new_state == "error":
        print("[DEBUG] Transition: OK -> ERROR (or not-error -> ERROR)")
        if track["muted_until"] and now < track["muted_until"]:
            print(f"[DEBUG] Currently muted until {track['muted_until']} - skipping notification.")
        else:
            # Clean out timestamps older than 24 hours
            original_count = len(track["error_timestamps"])
            track["error_timestamps"] = [
                t for t in track["error_timestamps"]
                if (now - t) < timedelta(hours=24)
            ]
            removed_count = original_count - len(track["error_timestamps"])
            if removed_count > 0:
                print(f"[DEBUG] Removed {removed_count} stale error timestamps (>24h old).")

            # Append this new error occurrence
            track["error_timestamps"].append(now)
            new_count = len(track["error_timestamps"])
            print(f"[DEBUG] error_timestamps has {new_count} in last 24h: {track['error_timestamps']}")

            # If this is the 5th time in 24h, add muting text
            if new_count == 5:
                print("[DEBUG] This is the 5th error in 24h. Mute for 24h.")
                message += "\n[muting this notification for 24 hours due to excessive triggering]"
                track["muted_until"] = now + timedelta(hours=24)
                print(f"[DEBUG] Setting muted_until to {track['muted_until']}")

            # Actually send the notification
            print("[DEBUG] Sending notification to Telegram/Discord.")
            _send_telegram_and_discord(f"Device={device}, Key={key}\n{message}")

    # Update last_state
    track["last_state"] = new_state

    with _notifications_lock:
        __tracking[(device, key)] = track


def _send_telegram_and_discord(alert_text: str):
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
                print(f"[DEBUG] Telegram POST status={resp.status_code}")
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
                print(f"[DEBUG] Discord POST status={resp.status_code}")
            except Exception as ex:
                print(f"[ERROR] Discord send failed: {ex}")
        else:
            print("[DEBUG] Discord enabled but missing webhook_url, skipping...")
