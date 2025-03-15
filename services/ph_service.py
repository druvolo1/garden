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

# Track last time we successfully parsed a reading
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

    # If there's a queued command waiting and we are not in the middle of another
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

        # Check for ack/nack responses
        if line in ("*OK", "*ER"):
            if last_sent_command:
                log_with_timestamp(f"Response '{line}' for command {last_sent_command}")
                last_sent_command = None
            else:
                log_with_timestamp(f"Unexpected response '{line}' (no command in progress)")

            # If there's another queued command, send it
            if not command_queue.empty():
                next_cmd = command_queue.get()
                last_sent_command = next_cmd["command"]
                log_with_timestamp(f"Sending next queued command: {last_sent_command}")
                send_command_to_probe(ser, next_cmd["command"])
            continue

        # Attempt to parse a pH reading
        try:
            ph_value = round(float(line), 2)
            # Indicate we're receiving data
            set_status("ph_probe", "reading", "ok", "Receiving readings.")

            # 1) Condition: If 0 or 14 => "probe_health"=error
            if ph_value == 0 or ph_value == 14:
                set_status("ph_probe", "probe_health", "error",
                           f"Unrealistic reading ({ph_value}). Probe may be bad.")
                continue

            # If <1 => treat as noise or error
            if ph_value < 1.0:
                raise ValueError(f"Ignoring pH <1.0 (noise?). Got {ph_value}")

            # 2) If we have an old reading, check if delta>1 => skip
            accepted_this_reading = False
            if old_ph_value is not None:
                delta = abs(ph_value - old_ph_value)
                log_with_timestamp(f"Delta from {old_ph_value} -> {ph_value} = {delta:.2f}")

                if delta > 1.0:
                    now = datetime.now()
                    ph_jumps.append(now)
                    # Purge older than 60s
                    cutoff = now - timedelta(seconds=60)
                    ph_jumps = [t for t in ph_jumps if t >= cutoff]

                    # If we have 5 big jumps => "probe_health"=error
                    if len(ph_jumps) >= 5:
                        set_status("ph_probe", "probe_health", "error",
                                   "Unstable readings detected (5 large jumps in last minute).")
                    else:
                        set_status("ph_probe", "probe_health", "ok",
                                   "Readings appear normal.")
                    # skip updating
                    continue
                else:
                    accepted_this_reading = True
                    # If stable reading, see if we can revert to 'ok'
                    now = datetime.now()
                    cutoff = now - timedelta(seconds=60)
                    ph_jumps = [t for t in ph_jumps if t >= cutoff]
                    if len(ph_jumps) == 0:
                        set_status("ph_probe", "probe_health", "ok", "Readings appear normal.")
            else:
                # If no old reading => accept the first reading
                accepted_this_reading = True
                set_status("ph_probe", "probe_health", "ok", "First valid pH reading received.")

            if accepted_this_reading:
                with ph_lock:
                    latest_ph_value = ph_value
                    log_with_timestamp(f"Accepted new pH reading: {ph_value}")
                old_ph_value = ph_value
                last_read_time = datetime.now()

                # 3) Range check
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

    # leftover data with no '\r'
    if buffer:
        log_with_timestamp(f"[DEBUG] leftover buffer: {buffer!r}")


def serial_reader():
    """
    Main loop that reads from the assigned ph_probe_path, stores data in `buffer`,
    and calls parse_buffer() to handle lines and commands.

    - If we cannot open the port 5 times in a row, set communication=error.
    - Once opened successfully, we continuously read until we see an actual
      I/O error or the stop_event is triggered.
    - If no reading is received for 30s, set reading=error (once every 30s to avoid spam).
    - We do NOT close the port (or mark it error) merely because a read() returns 0 bytes.
    """
    global ser, buffer, latest_ph_value, old_ph_value, last_read_time

    print("DEBUG: Entered serial_reader() at all...")

    # Track how many times in a row we fail to open the USB device
    consecutive_fails = 0
    MAX_FAILS = 5

    # Track the last time we raised the "no reading" error so we don't spam
    last_no_reading_error_time = None

    while not stop_event.ready():
        settings = load_settings()
        ph_probe_path = settings.get("usb_roles", {}).get("ph_probe")

        # If no pH device is assigned, wait a bit and clear statuses
        if not ph_probe_path:
            clear_status("ph_probe", "communication")
            clear_status("ph_probe", "reading")
            clear_status("ph_probe", "ph_value")
            eventlet.sleep(5)
            continue

        try:
            # Debug listing
            try:
                dev_list = subprocess.check_output("ls /dev/serial/by-id", shell=True).decode().splitlines()
                dev_list_str = ", ".join(dev_list) if dev_list else "No devices found"
                log_with_timestamp(f"Devices in /dev/serial/by-id: {dev_list_str}")
            except subprocess.CalledProcessError:
                log_with_timestamp("No devices found in /dev/serial/by-id (subprocess error).")

            log_with_timestamp(f"Currently assigned pH probe device: {ph_probe_path}")

            # Try opening the serial port
            ser = serial.Serial(ph_probe_path, baudrate=9600, timeout=1)
            consecutive_fails = 0  # reset on success

            set_status("ph_probe", "communication", "ok",
                       f"Opened {ph_probe_path} for pH reading.")
            clear_error("PH_USB_OFFLINE")  # legacy error handling

            # Start fresh state
            with ph_lock:
                buffer = ""
                old_ph_value = None
                latest_ph_value = None
                last_read_time = None
                log_with_timestamp("Buffer cleared on new device connection.")

            # We read indefinitely until exception or stop_event
            while not stop_event.ready():
                # If no reading for 30s => set reading=error once every 30s
                if last_read_time:
                    elapsed = (datetime.now() - last_read_time).total_seconds()
                    if elapsed > 30:
                        if (not last_no_reading_error_time or
                           (datetime.now() - last_no_reading_error_time).total_seconds() > 30):
                            set_status(
                                "ph_probe",
                                "reading",
                                "error",
                                "No pH reading available for 30+ seconds."
                            )
                            last_no_reading_error_time = datetime.now()
                else:
                    # If never received a reading and it's been >30s since open, same logic
                    pass

                raw_data = tpool.execute(ser.read, 100)
                if raw_data:
                    decoded_data = raw_data.decode("utf-8", errors="replace")
                    with ph_lock:
                        buffer += decoded_data
                        if len(buffer) > MAX_BUFFER_LENGTH:
                            log_with_timestamp("Buffer exceeded max length. Dumping buffer.")
                            set_status("ph_probe", "communication", "error",
                                       "Buffer exceeded max length. Dumping buffer.")
                            buffer = ""
                    parse_buffer(ser)
                else:
                    eventlet.sleep(0.01)

        except (serial.SerialException, OSError) as e:
            # We failed either on open or on read
            consecutive_fails += 1
            log_with_timestamp(
                f"Serial error on {ph_probe_path}: {e}. "
                f"Reconnecting in 5s... (fail #{consecutive_fails})"
            )

            if consecutive_fails >= MAX_FAILS:
                set_status("ph_probe", "communication", "error",
                           f"Cannot open {ph_probe_path} after {consecutive_fails} attempts.")

            set_error("PH_USB_OFFLINE")
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
    Recommended to use enqueue_calibration(...) if you want them queued
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
            "message": f"Invalid calibration level: {level}. "
                       f"Must be one of {list(valid_levels.keys())}."
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

# ----------------------------------------------------------------------
# NEW: Function to query Slope info from the probe on demand
# ----------------------------------------------------------------------

def get_slope_info(timeout=1.0):
    """
    Sends 'Slope,?' to the EZO pH probe, waits briefly for a response like:
      ?Slope,ACID,BASE,OFFSET
    Returns a dict:
      { 'acid_slope': float, 'base_slope': float, 'offset': float }
    or None on failure.

    Note: This function does a direct blocking read from the serial port,
    which might not fully align with your concurrency approach. If you prefer
    a queued approach, adapt accordingly.
    """
    global ser

    # If the port isn't open, try opening it or fail
    if not ser or not ser.is_open:
        # Optionally, try to open. Or else return None.
        try:
            settings = load_settings()
            ph_probe_path = settings.get("usb_roles", {}).get("ph_probe")
            if not ph_probe_path:
                log_with_timestamp("No pH device assigned, cannot get slope.")
                return None
            ser = serial.Serial(ph_probe_path, baudrate=9600, timeout=1)
        except Exception as e:
            log_with_timestamp(f"Cannot open port for slope check: {e}")
            return None

    # flush any leftover:
    try:
        ser.reset_input_buffer()
    except:
        pass

    # send the command
    slope_cmd = "Slope,?"
    try:
        log_with_timestamp(f"Sending slope command: {slope_cmd}")
        ser.write((slope_cmd + "\r").encode())
    except Exception as e:
        log_with_timestamp(f"Error writing slope command: {e}")
        return None

    # read lines up to `timeout`
    end_time = datetime.now() + timedelta(seconds=timeout)
    slope_line = None

    while datetime.now() < end_time:
        raw_line = ser.readline().decode("utf-8", errors="replace").strip()
        if raw_line.startswith("?Slope,"):
            slope_line = raw_line
            break
        eventlet.sleep(0.01)  # short sleep

    if not slope_line:
        log_with_timestamp("Did not receive slope response.")
        return None

    # parse something like "?Slope,98.0,97.5,-3.2"
    try:
        payload = slope_line.replace("?Slope,", "")  # => "98.0,97.5,-3.2"
        parts = payload.split(",")
        acid_slope = float(parts[0])
        base_slope = float(parts[1])
        offset = float(parts[2])
        return {
            "acid_slope": acid_slope,
            "base_slope": base_slope,
            "offset": offset
        }
    except Exception as e:
        log_with_timestamp(f"Error parsing slope line '{slope_line}': {e}")
        return None
