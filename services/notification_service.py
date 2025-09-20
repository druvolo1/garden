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

def log_notify_debug(msg: str):
    from status_namespace import is_debug_enabled
    """Logs messages only if 'notifications' debug is ON."""
    if is_debug_enabled("notifications"):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def is_notification_active(device: str, key: str) -> bool:
    """
    Returns True if a notification for (device, key) is currently active (state != "ok").
    """
    with _notifications_lock:
        data = _notifications.get((device, key))
        if data and data["state"].lower() != "ok":
            return True
    return False

def set_status(device: str, key: str, state: str, message: str = ""):
    """
    Called whenever we have a new state for (device, key).
    We'll record the state in _notifications, then run handle_notification_transition
    to determine if we should notify or not.
    """
    with _notifications_lock:
        old_status = _notifications.get((device, key))
        old_state = old_status["state"] if old_status else "ok"

        # If already active and new state is also not "ok", don't notify again
        if old_state != "ok" and state != "ok":
            # Just update timestamp/message in _notifications, but skip transition logic
            _notifications[(device, key)] = {
                "state": state,
                "message": message,
                "timestamp": datetime.now()
            }
            broadcast_notifications_update()
            return

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
        log_notify_debug(f"[DEBUG] clear_status called for (device={device}, key={key}); reset counters & removed from tracking")

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
        log_notify_debug("[DEBUG] Notifications are turned OFF in debug settings, skipping broadcast.")
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
    import api.settings
    if api.settings.feeding_in_progress:
        log_notify_debug(f"[DEBUG] Feeding in progress; skipping notification transition for {device}/{key}.")
        return

    now = datetime.now()
    old_state = old_state.lower()
    new_state = new_state.lower()

    with _notifications_lock:
        track = __tracking.get((device, key), {
            "last_state": "ok",
            "error_timestamps": [],
            "muted_until": None
        })

    log_notify_debug(f"[DEBUG] handle_notification_transition device={device}, key={key}")
    log_notify_debug(f"        old_state={old_state}, new_state={new_state}, track={track}")

    # -------- ERROR -> OK transition --------
    if old_state == "error" and new_state == "ok":
        # If we're currently muted, skip sending "cleared"
        if track["muted_until"] and now < track["muted_until"]:
            log_notify_debug(f"[DEBUG] Currently muted until {track['muted_until']} - skipping 'cleared' notification.")
        else:
            log_notify_debug("[DEBUG] Transition: ERROR -> OK - sending 'cleared' notification.")
            _send_telegram_and_discord(f"Device={device}, Key={key}\nIssue cleared; now OK.")
        # Notice: we do NOT clear timestamps or unmute.
        # They stay until 24h passes or the user manually clears.

    # -------- OK -> ERROR transition --------
    elif old_state != "error" and new_state == "error":
        if track["muted_until"] and now < track["muted_until"]:
            log_notify_debug(f"[DEBUG] Currently muted until {track['muted_until']} - skipping ERROR notification.")
        else:
            # Remove stale timestamps older than 24h
            original_count = len(track["error_timestamps"])
            track["error_timestamps"] = [
                t for t in track["error_timestamps"]
                if (now - t) < timedelta(hours=24)
            ]
            removed_count = original_count - len(track["error_timestamps"])
            if removed_count > 0:
                log_notify_debug(f"[DEBUG] Removed {removed_count} old error timestamps (>24h).")

            # Append this new error occurrence
            track["error_timestamps"].append(now)
            new_count = len(track["error_timestamps"])
            log_notify_debug(f"[DEBUG] error_timestamps has {new_count} in last 24h: {track['error_timestamps']}")

            # If this is the 5th error, set a 24h mute
            if new_count == 5:
                message += "\n[muting this notification for 24 hours due to excessive triggering]"
                track["muted_until"] = now + timedelta(hours=24)
                log_notify_debug(f"[DEBUG] Setting muted_until to {track['muted_until']}")

            log_notify_debug("[DEBUG] Sending notification to Telegram/Discord.")
            _send_telegram_and_discord(f"Device={device}, Key={key}\n{message}")

    # Update last_state
    track["last_state"] = new_state
    with _notifications_lock:
        __tracking[(device, key)] = track



def _send_telegram_and_discord(alert_text: str):
    """
    Helper function to actually send the notification to Telegram and/or Discord if enabled.
    Prepends the system name to the alert.
    """
    cfg = load_settings()
    system_name = cfg.get("system_name", "Garden")
    final_alert = f"[{system_name}] {alert_text}"

    log_notify_debug(f"[DEBUG] _send_telegram_and_discord called with text:\n{final_alert}")

    # --- Telegram ---
    if cfg.get("telegram_enabled"):
        bot_token = cfg.get("telegram_bot_token", "").strip()
        chat_id = cfg.get("telegram_chat_id", "").strip()
        if bot_token and chat_id:
            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {"chat_id": chat_id, "text": final_alert}
                resp = requests.post(url, json=payload, timeout=10)
                log_notify_debug(f"[DEBUG] Telegram POST => {resp.status_code}")
            except Exception as ex:
                log_notify_debug(f"[ERROR] Telegram send failed: {ex}")
        else:
            log_notify_debug("[DEBUG] Telegram enabled but missing bot_token/chat_id, skipping...")

    # --- Discord ---
    if cfg.get("discord_enabled"):
        webhook_url = cfg.get("discord_webhook_url", "").strip()
        if webhook_url:
            try:
                resp = requests.post(webhook_url, json={"content": final_alert}, timeout=10)
                log_notify_debug(f"[DEBUG] Discord POST => {resp.status_code}")
            except Exception as ex:
                log_notify_debug(f"[ERROR] Discord send failed: {ex}")
        else:
            log_notify_debug("[DEBUG] Discord enabled but missing webhook_url, skipping...")


# -----------------------------------------------------------------------------
# NEW CODE to track per-condition errors: 5 times in 24h => mute
# -----------------------------------------------------------------------------

_condition_lock = threading.Lock()

# Example:
# {
#    (device, condition_key): {
#        "error_timestamps": [datetime objects],
#        "muted_until": datetime or None
#    }
# }
_condition_counters = {}

def report_condition_error(device: str, condition_key: str, message: str):
    """
    For repeated error conditions. If called 5 times in 24 hours, we send
    a "muting for 24 hours" notice and skip further notifications for this
    (device, condition_key) until that 24h is up.

    Example usage from ph_service.py:
       report_condition_error("ph_probe", "unrealistic_reading",
           "Unrealistic pH reading (0.0). Probe may be disconnected.")
    """
    import api.settings
    if api.settings.feeding_in_progress:
        log_notify_debug(f"[DEBUG] Feeding in progress; skipping condition error report for {device}/{condition_key}.")
        return

    # --- ADDED: don't retrigger if active ---
    if is_notification_active(device, condition_key):
        log_notify_debug(f"[DEBUG] {device}/{condition_key} notification already active. Skipping duplicate notification.")
        return

    now = datetime.now()

    with _condition_lock:
        info = _condition_counters.get((device, condition_key), {
            "error_timestamps": [],
            "muted_until": None
        })

        # If we're already muted, check if it expired
        if info["muted_until"] and now < info["muted_until"]:
            log_notify_debug(f"[DEBUG] {device}/{condition_key} still muted until {info['muted_until']}, skipping.")
            return
        elif info["muted_until"] and now >= info["muted_until"]:
            # Mute expired => unmute
            info["muted_until"] = None
            log_notify_debug(f"[DEBUG] {device}/{condition_key} => Mute has expired, continuing.")

        # Remove old timestamps > 24h
        original_count = len(info["error_timestamps"])
        info["error_timestamps"] = [
            t for t in info["error_timestamps"]
            if (now - t) < timedelta(hours=24)
        ]
        removed = original_count - len(info["error_timestamps"])
        if removed > 0:
            log_notify_debug(f"[DEBUG] Removed {removed} stale timestamps for {device}/{condition_key}.")

        # Add this new occurrence
        info["error_timestamps"].append(now)
        count_24h = len(info["error_timestamps"])
        log_notify_debug(f"[DEBUG] {device}/{condition_key} triggered => {count_24h} times in last 24h.")

        # If it's the 5th time, we append the muting note
        final_message = message
        if count_24h == 5:
            final_message += "\n[muting this condition for 24 hours due to repeated triggers]"
            info["muted_until"] = now + timedelta(hours=24)
            log_notify_debug(f"[DEBUG] {device}/{condition_key} => set muted_until={info['muted_until']}")

        # Actually send it
        _send_telegram_and_discord(f"{device}/{condition_key}\n{final_message}")

        # Save updated data
        _condition_counters[(device, condition_key)] = info


def clear_condition(device: str, condition_key: str):
    """
    If user hits "Clear" in the UI for a specific condition, reset counters.
    This is separate from clear_status(), which was for the ok→error approach.
    """
    with _condition_lock:
        _condition_counters.pop((device, condition_key), None)
        log_notify_debug(f"[DEBUG] Cleared condition counters => {device}/{condition_key}")