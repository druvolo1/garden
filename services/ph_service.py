# File: ph_service.py
print(f"LOADED ph_service.py from {__file__}", flush=True)

import eventlet
eventlet.monkey_patch()  # Ensure all standard libs are patched early

import signal
import serial
import subprocess
from queue import Queue
from datetime import datetime, timedelta
from eventlet import tpool
from eventlet import semaphore, event

from services.error_service import set_error, clear_error
# Import your notifications helper (not shown here) for set_status/clear_status
from services.notification_service import set_status, clear_status

from utils.settings_utils import load_settings, save_settings

# Shared queue for commands sent to the probe
command_queue = Queue()
stop_event = event.Event()

ph_lock = semaphore.Semaphore()

buffer = ""             # Centralized buffer for incoming serial data
latest_ph_value = None  # Store the most recent pH reading
last_sent_command = None
COMMAND_TIMEOUT = 10
MAX_BUFFER_LENGTH = 100

old_ph_value = None  # stores the previous pH value so we only process changes

ser = None  # Global variable to track the serial connection

def log_with_timestamp(message):
    from status_namespace import is_debug_enabled
    """Logs messages only if debugging is enabled for pH."""
    if is_debug_enabled("ph"):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)

def enqueue_command(command, command_type="general"):
    command_queue.put({"command": command, "type": command_type})

def send_command_to_probe(ser, command):
    """
    Sends a command string to the pH probe, appending '\r'.
    """
    global last_sent_command
    try:
        log_with_timestamp(f"[DEBUG] Sending to probe: {command!r}")
        ser.write((command + '\r').encode())
        last_sent_command = command
    except Exception as e:
        log_with_timestamp(f"Error sending command '{command}': {e}")

# Track how many times in the past minute we've had a "jump > 1 pH"
ph_jumps = []  # list of datetime objects when a big jump occurred

# Track last time we successfully parsed a reading, for #3 (no reading = error)
last_read_time = None

def parse_buffer(ser):
    """
    Reads data from `buffer`, splitting on '\r',
    and applies these rules:

    1) If pH is 0 or 14 => "probe_health"=error: bad probe.
    2) If delta>1 => skip applying reading. If we get 5 such jumps
       in a minute => "probe_health"=error: "unstable readings."
       If we go below 5, revert to "probe_health"=ok: "readings appear normal."
    3) If reading is accepted, check range logic for "within_range."
    """

    global buffer, latest_ph_value, last_sent_command
    global old_ph_value, last_read_time, ph_jumps

    if last_sent_command is None and not command_queue.empty():
        next_cmd = command_queue.get()
        last_sent_command = next_cmd["command"]
        log_with_timestamp(f"[DEBUG] No active command. Sending queued command: {last_sent_command}")
        send_command_to_probe(ser, next_cmd["command"])

    while '\r' in buffer:
        line, buffer = buffer.split('\r', 1)
        line = line.strip()
        if not line:
            log_with_timestamp("[DEBUG] parse_buffer: skipping empty line.")
            continue

        # Possible *OK or *ER responses
        if line in ("*OK", "*ER"):
            if last_sent_command:
                log_with_timestamp(f"Response '{line}' for command {last_sent_command}")
                last_sent_command = None
            else:
                log_with_timestamp(f"Unexpected response '{line}' (no command in progress)")
            if not command_queue.empty():
                next_cmd = command_queue.get()
                last_sent_command = next_cmd["command"]
                log_with_timestamp(f"Sending next queued command: {last_sent_command}")
                send_command_to_probe(ser, next_cmd["command"])
            continue

        try:
            ph_value = round(float(line), 2)
            # Indicate we're receiving data
            set_status("ph_probe", "reading", "ok", "Receiving readings.")

            # 1) Condition: If 0 or 14 => "probe_health"=error
            if ph_value == 0 or ph_value == 14:
                set_status("ph_probe", "probe_health", "error",
                           f"Unrealistic reading ({ph_value}). Probe may be bad.")
                # Typically we'd skip further logic
                continue

            # If <1 => treat as noise or error
            if ph_value < 1.0:
                raise ValueError(f"Ignoring pH <1.0 (noise?). Got {ph_value}")

            # 2) Condition: If we have an old reading, see if delta>1 => skip
            accepted_this_reading = False
            if old_ph_value is not None:
                delta = abs(ph_value - old_ph_value)
                log_with_timestamp(f"Delta from {old_ph_value} -> {ph_value} = {delta:.2f}")

                # If delta>1 => we do NOT accept the reading
                if delta > 1.0:
                    # Track a "big jump" in the rolling list
                    now = datetime.now()
                    ph_jumps.append(now)
                    # Purge older than 60s
                    cutoff = now - timedelta(seconds=60)
                    ph_jumps = [t for t in ph_jumps if t >= cutoff]

                    # If we have 5 big jumps => "probe_health"=error: "unstable"
                    if len(ph_jumps) >= 5:
                        set_status("ph_probe", "probe_health", "error",
                                   "Unstable readings detected (5 large jumps in last minute).")
                    else:
                        # If it's under 5, "probe_health"=ok: "normal"
                        set_status("ph_probe", "probe_health", "ok",
                                   "Readings appear normal.")
                    # Skip updating old_ph_value or latest_ph_value
                    continue
                else:
                    # delta <= 1 => accept reading
                    accepted_this_reading = True
                    # If we were in an error from big swings, we might revert to "ok"
                    # as above if len(ph_jumps)<5. Already done above if delta>1
                    # so if we get a stable reading, let's see if we can reduce jumps
                    now = datetime.now()
                    cutoff = now - timedelta(seconds=60)
                    ph_jumps = [t for t in ph_jumps if t >= cutoff]
                    if len(ph_jumps) == 0:
                        set_status("ph_probe", "probe_health", "ok", "Readings appear normal.")

            else:
                # If no old reading => accept the first reading
                accepted_this_reading = True
                set_status("ph_probe", "probe_health", "ok", "First valid pH reading received.")

            # If we accepted the reading => update old_ph_value, latest_ph_value, range logic
            if accepted_this_reading:
                with ph_lock:
                    latest_ph_value = ph_value
                    log_with_timestamp(f"Accepted new pH reading: {ph_value}")
                old_ph_value = ph_value
                last_read_time = datetime.now()

                # 3) Check if pH is in recommended range => "within_range"
                s = load_settings()
                ph_min = s.get("ph_range", {}).get("min", 5.5)
                ph_max = s.get("ph_range", {}).get("max", 6.5)
                if ph_value < ph_min or ph_value > ph_max:
                    set_status("ph_probe", "within_range", "error",
                               f"pH {ph_value} out of recommended range [{ph_min}, {ph_max}].")
                else:
                    set_status("ph_probe", "within_range", "ok",
                               f"pH is within recommended range [{ph_min}, {ph_max}].")

            from status_namespace import emit_status_update
            emit_status_update()

        except ValueError as e:
            log_with_timestamp(f"Ignoring line '{line}': {e}")

    # If leftover data remains but no '\r' => do nothing
    if buffer:
        log_with_timestamp(f"[DEBUG] leftover buffer: {buffer!r}")


def serial_reader():
    """
    Main loop that reads from the assigned ph_probe_path, stores data in `buffer`,
    and calls parse_buffer() to handle lines and commands.

    Adds logic:
    - If we cannot open the port 5 times in a row, set communication=error.
    - Once we do open successfully, set communication=ok and reset failures to 0.
    """
    global ser, buffer, latest_ph_value, old_ph_value, last_read_time

    print("DEBUG: Entered serial_reader() at all...")

    # Track the last time we set an error for "no reading"
    last_no_reading_error = None

    # NEW: track how many times in a row we fail to open the USB device
    consecutive_fails = 0
    MAX_FAILS = 5

    while not stop_event.ready():
        settings = load_settings()
        ph_probe_path = settings.get("usb_roles", {}).get("ph_probe")

        # If no pH device is assigned, quietly wait 5s and skip
        if not ph_probe_path:
            # Clear any "communication", "reading", or "ph_value" states, since we have no device
            clear_status("ph_probe", "communication")
            clear_status("ph_probe", "reading")
            clear_status("ph_probe", "ph_value")
            eventlet.sleep(5)
            continue

        try:
            # Just a debug listing
            try:
                dev_list = subprocess.check_output("ls /dev/serial/by-id", shell=True).decode().splitlines()
                dev_list_str = ", ".join(dev_list) if dev_list else "No devices found"
                log_with_timestamp(f"Devices in /dev/serial/by-id: {dev_list_str}")
            except subprocess.CalledProcessError:
                log_with_timestamp("No devices found in /dev/serial/by-id (subprocess error).")

            log_with_timestamp(f"Currently assigned pH probe device: {ph_probe_path}")

            # Attempt to open the serial port
            ser = serial.Serial(ph_probe_path, baudrate=9600, timeout=1)

            # If we reach here, we successfully opened the port; reset failures to 0
            consecutive_fails = 0

            start_of_loop = datetime.now()
            # If we successfully open it, set communication=ok
            set_status("ph_probe", "communication", "ok", f"Opened {ph_probe_path} for pH reading.")
            clear_error("PH_USB_OFFLINE")  # legacy error handling

            # Initialize 'reading' as ok so the dash shows it as OK initially
            set_status("ph_probe", "reading", "ok", "Initial state: awaiting pH data.")

            # Clear buffer on new device connection
            with ph_lock:
                buffer = ""
                old_ph_value = None
                latest_ph_value = None
                last_read_time = None
                log_with_timestamp("Buffer cleared on new device connection.")

            while not stop_event.ready():
                # If we've assigned a device but haven't gotten a reading for a while => reading error
                if last_read_time is None:
                    # If no reading at all for 10s => error
                    # We'll only post once every 30s so it doesn't spam
                    if (last_no_reading_error is None or
                       (datetime.now() - last_no_reading_error).total_seconds() > 30):
                        if (datetime.now() - start_of_loop).total_seconds() > 10:
                            set_status("ph_probe", "reading", "error",
                                       "No pH reading available (device assigned, but no data).")
                            last_no_reading_error = datetime.now()
                else:
                    # (Optional) If you want to check if the last_read_time is too old, do it here
                    pass

                # Read up to 100 bytes from the port
                raw_data = tpool.execute(ser.read, 100)
                if raw_data:
                    decoded_data = raw_data.decode("utf-8", errors="replace")
                    with ph_lock:
                        buffer += decoded_data
                        # If buffer is too big => communication=error
                        if len(buffer) > MAX_BUFFER_LENGTH:
                            log_with_timestamp("Buffer exceeded max length. Dumping buffer.")
                            set_status("ph_probe", "communication", "error",
                                       "Buffer exceeded max length. Dumping buffer.")
                            buffer = ""
                    parse_buffer(ser)
                else:
                    eventlet.sleep(0.05)

        except (serial.SerialException, OSError) as e:
            # We failed to open the port
            consecutive_fails += 1
            log_with_timestamp(f"Serial error on {ph_probe_path}: {e}. Reconnecting in 5s... (fail #{consecutive_fails})")

            # If we hit 5 fails, set communication=error
            if consecutive_fails >= MAX_FAILS:
                set_status("ph_probe", "communication", "error",
                           f"Cannot open {ph_probe_path} after {consecutive_fails} consecutive attempts.")

            set_error("PH_USB_OFFLINE")  # legacy error approach
            eventlet.sleep(5)

        finally:
            if ser and ser.is_open:
                ser.close()
                log_with_timestamp("Serial connection closed.")

def send_configuration_commands(ser):
    try:
        log_with_timestamp("Sending configuration commands to the pH probe...")
        command = "C,2"
        send_command_to_probe(ser, command)
    except Exception as e:
        log_with_timestamp(f"Error sending configuration commands: {e}")

def calibrate_ph(ser, level):
    """
    Directly sends calibration commands to the pH probe.
    It's recommended to use enqueue_calibration(...) if you want them queued up
    instead of immediate direct send.
    """
    valid_levels = {
        'low': 'Cal,low,4.00',
        'mid': 'Cal,mid,7.00',
        'high': 'Cal,high,10.00',
        'clear': 'Cal,clear'
    }

    global last_sent_command
    if level not in valid_levels:
        log_with_timestamp(f"Invalid calibration level: {level}")
        return {"status": "failure", "message": "Invalid calibration level"}

    with ph_lock:
        command = valid_levels[level]
        if last_sent_command is None:
            send_command_to_probe(ser, command)
            last_sent_command = command
            log_with_timestamp(f"Calibration command '{command}' sent.")
            return {"status": "success", "message": f"Calibration command '{command}' sent"}

        else:
            log_with_timestamp(f"Cannot send calibration command '{command}' while waiting for a response.")
            return {"status": "failure", "message": "A command is already in progress"}

def enqueue_calibration(level):
    """
    Places a calibration command into the queue for subsequent sending once
    the probe responds to prior commands.
    """
    valid_levels = {
        'low': 'Cal,low,4.00',
        'mid': 'Cal,mid,7.00',
        'high': 'Cal,high,10.00',
        'clear': 'Cal,clear'
    }

    if level not in valid_levels:
        return {
            "status": "failure",
            "message": f"Invalid calibration level: {level}. Must be one of {list(valid_levels.keys())}."
        }

    command = valid_levels[level]
    command_queue.put({"command": command, "type": "calibration"})
    return {"status": "success", "message": f"Calibration command '{command}' enqueued."}

def restart_serial_reader():
    """
    Stops the current serial_reader thread (if any), clears buffer/state, and spawns a new one.
    """
    global stop_event, buffer, latest_ph_value
    log_with_timestamp("Restarting serial reader...")

    with ph_lock:
        buffer = ""
        latest_ph_value = None
        log_with_timestamp("Buffer and latest pH value cleared.")

    stop_serial_reader()

    eventlet.sleep(1)  # ensure old thread is done
    stop_event = event.Event()
    start_serial_reader()

def get_last_sent_command():
    global last_sent_command
    if last_sent_command:
        return last_sent_command
    return "No command has been sent yet."

def start_serial_reader():
    eventlet.spawn(serial_reader)
    log_with_timestamp("Serial reader started.")

def stop_serial_reader():
    global buffer, latest_ph_value, ser
    log_with_timestamp("Stopping serial reader...")

    with ph_lock:
        buffer = ""
        latest_ph_value = None
        log_with_timestamp("Buffer and latest pH value cleared during stop.")

    if ser and ser.is_open:
        ser.close()
        log_with_timestamp("Serial connection closed.")

    stop_event.send()
    log_with_timestamp("Serial reader stopped.")

def get_latest_ph_reading():
    global latest_ph_value
    settings = load_settings()
    ph_probe_path = settings.get("usb_roles", {}).get("ph_probe")
    if not ph_probe_path:
        # No device assigned -> return None, no log
        return None

    with ph_lock:
        if latest_ph_value is not None:
            return latest_ph_value

    log_with_timestamp("No pH reading available.")
    return None

def graceful_exit(signum, frame):
    log_with_timestamp(f"Received signal {signum}. Cleaning up...")
    try:
        stop_serial_reader()
    except Exception as e:
        log_with_timestamp(f"Error during cleanup: {e}")
    log_with_timestamp("Cleanup complete. Exiting application.")
    raise SystemExit()

def handle_stop_signal(signum, frame):
    log_with_timestamp(f"Received signal {signum} (SIGTSTP). Cleaning up...")
    graceful_exit(signum, frame)
