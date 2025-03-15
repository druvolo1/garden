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
    """
    Place a command into the queue.
    command_type can be "calibration", "slope_query", or "general".
    """
    log_with_timestamp(f"[DEBUG] enqueue_command('{command}', type='{command_type}') called.")
    command_queue.put({"command": command, "type": command_type})

def send_command_to_probe(ser, command):
    """
    Sends a command string to the pH probe, appending '\r'.
    """
    global last_sent_command
    try:
        log_with_timestamp(f"[DEBUG] Actually writing to serial: {command!r}")
        ser.write((command + '\r').encode())
        last_sent_command = command
    except Exception as e:
        log_with_timestamp(f"Error sending command '{command}': {e}")

# Track how many times in the past minute we've had a "jump > 1 pH"
ph_jumps = []  # list of datetime objects when a big jump occurred

# Track last time we successfully parsed a reading
last_read_time = None

# Slope data + event
slope_event = event.Event()
slope_data = None

def parse_buffer(ser):
    """
    Reads data from `buffer`, splitting on '\r',
    and applies these rules for pH readings, slope, etc.
    """

    global buffer, latest_ph_value, last_sent_command
    global old_ph_value, last_read_time, ph_jumps
    global slope_data, slope_event  # so we can update slope_data, slope_event

    if last_sent_command is None and not command_queue.empty():
        next_cmd = command_queue.get()
        last_sent_command = next_cmd["command"]
        log_with_timestamp(f"[DEBUG] parse_buffer: Taking next command from queue: {last_sent_command}")
        send_command_to_probe(ser, next_cmd["command"])

    while '\r' in buffer:
        line, buffer = buffer.split('\r', 1)
        line = line.strip()
        if not line:
            log_with_timestamp("[DEBUG] parse_buffer: skipping empty line.")
            continue

        log_with_timestamp(f"[DEBUG] parse_buffer: got line '{line}'")

        # *OK / *ER
        if line in ("*OK", "*ER"):
            if last_sent_command:
                log_with_timestamp(f"[DEBUG] parse_buffer: response '{line}' for command {last_sent_command}")
                last_sent_command = None
            else:
                log_with_timestamp(f"[DEBUG] parse_buffer: unexpected '{line}' (no command in progress)")

            if not command_queue.empty():
                next_cmd = command_queue.get()
                last_sent_command = next_cmd["command"]
                log_with_timestamp(f"[DEBUG] parse_buffer: Now sending next queued command: {last_sent_command}")
                send_command_to_probe(ser, next_cmd["command"])
            continue

        # Slope
        if line.upper().startswith("?SLOPE,"):
            log_with_timestamp(f"[DEBUG] parse_buffer got slope line: {line}")
            try:
                payload = line[7:]  # or line.split(",", 1)[1]
                parts = payload.split(",")  # e.g. ["110.2", "92.1", "4.67"]
                acid = float(parts[0])
                base = float(parts[1])
                offset = float(parts[2])
                slope_data = {
                    "acid_slope": acid,
                    "base_slope": base,
                    "offset": offset
                }
                log_with_timestamp(f"[DEBUG] parse_buffer: slope_data set to {slope_data}")

                # ─────────────────────────────────────────────────────────
                # Save slope to settings immediately after parsing it
                s = load_settings()
                s["ph_probe_slope"] = slope_data
                save_settings(s)
                log_with_timestamp(f"[DEBUG] Slope data saved to settings: {slope_data}")
                # ─────────────────────────────────────────────────────────

                last_sent_command = None
                slope_event.send()

                if not command_queue.empty():
                    nxt = command_queue.get()
                    last_sent_command = nxt["command"]
                    log_with_timestamp(f"[DEBUG] parse_buffer: sending next queued command: {last_sent_command}")
                    send_command_to_probe(ser, nxt["command"])
            except Exception as e:
                log_with_timestamp(f"Error parsing slope line '{line}': {e}")
            continue

        # Otherwise, try pH numeric
        try:
            ph_value = round(float(line), 2)
            set_status("ph_probe", "reading", "ok", "Receiving readings.")
            log_with_timestamp(f"[DEBUG] parse_buffer: recognized numeric pH => {ph_value}")

            if ph_value == 0 or ph_value == 14:
                set_status("ph_probe", "probe_health", "error",
                           f"Unrealistic reading ({ph_value}). Probe may be bad.")
                continue

            if ph_value < 1.0:
                raise ValueError(f"Ignoring pH <1.0 (noise?). Got {ph_value}")

            accepted_this_reading = False
            if old_ph_value is not None:
                delta = abs(ph_value - old_ph_value)
                log_with_timestamp(f"[DEBUG] parse_buffer: Delta from {old_ph_value} -> {ph_value} = {delta:.2f}")
                if delta > 1.0:
                    now = datetime.now()
                    ph_jumps.append(now)
                    cutoff = now - timedelta(seconds=60)
                    ph_jumps = [t for t in ph_jumps if t >= cutoff]

                    if len(ph_jumps) >= 5:
                        set_status("ph_probe", "probe_health", "error",
                                   "Unstable readings detected (5 large jumps in last minute).")
                    else:
                        set_status("ph_probe", "probe_health", "ok",
                                   "Readings appear normal.")
                    continue
                else:
                    accepted_this_reading = True
                    now = datetime.now()
                    cutoff = now - timedelta(seconds=60)
                    ph_jumps = [t for t in ph_jumps if t >= cutoff]
                    if len(ph_jumps) == 0:
                        set_status("ph_probe", "probe_health", "ok", "Readings appear normal.")
            else:
                # first reading
                accepted_this_reading = True
                set_status("ph_probe", "probe_health", "ok", "First valid pH reading received.")

            if accepted_this_reading:
                with ph_lock:
                    latest_ph_value = ph_value
                    log_with_timestamp(f"Accepted new pH reading: {ph_value}")
                old_ph_value = ph_value
                last_read_time = datetime.now()

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
            log_with_timestamp(f"[DEBUG] parse_buffer ignoring line '{line}': {e}")

    if buffer:
        log_with_timestamp(f"[DEBUG] leftover buffer: {buffer!r}")



def serial_reader():
    global ser, buffer, latest_ph_value, old_ph_value, last_read_time

    print("DEBUG: Entered serial_reader() at all...")
    consecutive_fails = 0
    MAX_FAILS = 5
    last_no_reading_error_time = None

    while not stop_event.ready():
        settings = load_settings()
        ph_probe_path = settings.get("usb_roles", {}).get("ph_probe")

        if not ph_probe_path:
            clear_status("ph_probe", "communication")
            clear_status("ph_probe", "reading")
            clear_status("ph_probe", "ph_value")
            eventlet.sleep(5)
            continue

        try:
            try:
                dev_list = subprocess.check_output("ls /dev/serial/by-id", shell=True).decode().splitlines()
                dev_list_str = ", ".join(dev_list) if dev_list else "No devices found"
                log_with_timestamp(f"[DEBUG] Found devices: {dev_list_str}")
            except subprocess.CalledProcessError:
                log_with_timestamp("[DEBUG] No devices found in /dev/serial/by-id (subprocess error).")

            log_with_timestamp(f"[DEBUG] Trying to open serial port: {ph_probe_path}")
            ser = serial.Serial(ph_probe_path, baudrate=9600, timeout=1)
            consecutive_fails = 0

            set_status("ph_probe", "communication", "ok",
                       f"Opened {ph_probe_path} for pH reading.")
            clear_error("PH_USB_OFFLINE")

            with ph_lock:
                buffer = ""
                old_ph_value = None
                latest_ph_value = None
                last_read_time = None
                log_with_timestamp("[DEBUG] Buffer cleared on new device connection.")

            # ─────────────────────────────────────────────────────────────
            # Enable continuous read mode as soon as we connect:
            # (Use "C,1" or "C,2" depending on your device/ASCII vs. continuous)
            log_with_timestamp("[DEBUG] Enabling continuous read mode now that the device is open.")
            send_command_to_probe(ser, "C,1")
            # ─────────────────────────────────────────────────────────────

            while not stop_event.ready():
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

                raw_data = tpool.execute(ser.read, 100)
                if raw_data:
                    decoded_data = raw_data.decode("utf-8", errors="replace")
                    with ph_lock:
                        buffer += decoded_data
                        if len(buffer) > MAX_BUFFER_LENGTH:
                            log_with_timestamp("[DEBUG] Buffer exceeded max length. Dumping buffer.")
                            set_status("ph_probe", "communication", "error",
                                       "Buffer exceeded max length. Dumping buffer.")
                            buffer = ""
                    parse_buffer(ser)
                else:
                    eventlet.sleep(0.01)

        except (serial.SerialException, OSError) as e:
            consecutive_fails += 1
            log_with_timestamp(
                f"[DEBUG] Serial error on {ph_probe_path}: {e}. "
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
                log_with_timestamp("[DEBUG] Serial connection closed.")



def send_configuration_commands(ser):
    try:
        log_with_timestamp("[DEBUG] Sending default config commands: 'C,2'")
        command = "C,2"
        send_command_to_probe(ser, command)
    except Exception as e:
        log_with_timestamp(f"[DEBUG] Error sending configuration commands: {e}")


def calibrate_ph(ser, level):
    valid_levels = {
        'low': 'Cal,low,4.00',
        'mid': 'Cal,mid,7.00',
        'high': 'Cal,high,10.00',
        'clear': 'Cal,clear'
    }

    global last_sent_command
    if level not in valid_levels:
        log_with_timestamp(f"[DEBUG] Invalid calibration level: {level}")
        return {"status": "failure", "message": "Invalid calibration level"}

    with ph_lock:
        command = valid_levels[level]
        if last_sent_command is None:
            log_with_timestamp(f"[DEBUG] calibrate_ph() -> sending: {command}")
            send_command_to_probe(ser, command)
            last_sent_command = command
            return {"status": "success", "message": f"Calibration command '{command}' sent"}
        else:
            msg = f"[DEBUG] calibrate_ph() -> cannot send '{command}' while waiting for response."
            log_with_timestamp(msg)
            return {"status": "failure", "message": "A command is already in progress"}


def enqueue_calibration(level):
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
    log_with_timestamp(f"[DEBUG] enqueue_calibration('{level}') -> puts '{command}' in queue")
    command_queue.put({"command": command, "type": "calibration"})
    return {"status": "success", "message": f"Calibration command '{command}' enqueued."}


def restart_serial_reader():
    global stop_event, buffer, latest_ph_value
    log_with_timestamp("[DEBUG] restart_serial_reader() called.")

    with ph_lock:
        buffer = ""
        latest_ph_value = None
        log_with_timestamp("[DEBUG] Buffer and latest pH value cleared for restart.")

    stop_serial_reader()
    eventlet.sleep(1)
    stop_event = event.Event()
    start_serial_reader()

def get_last_sent_command():
    global last_sent_command
    result = last_sent_command if last_sent_command else "No command has been sent yet."
    log_with_timestamp(f"[DEBUG] get_last_sent_command() -> {result}")
    return result

def start_serial_reader():
    log_with_timestamp("[DEBUG] start_serial_reader() -> spawning serial_reader thread.")
    eventlet.spawn(serial_reader)

def stop_serial_reader():
    global buffer, latest_ph_value, ser
    log_with_timestamp("[DEBUG] stop_serial_reader() called.")

    with ph_lock:
        buffer = ""
        latest_ph_value = None
        log_with_timestamp("[DEBUG] Buffer and latest pH value cleared during stop.")

    if ser and ser.is_open:
        ser.close()
        log_with_timestamp("[DEBUG] Serial connection closed.")

    stop_event.send()
    log_with_timestamp("[DEBUG] serial_reader stopped via event.")


def get_latest_ph_reading():
    global latest_ph_value
    settings = load_settings()
    ph_probe_path = settings.get("usb_roles", {}).get("ph_probe")
    if not ph_probe_path:
        log_with_timestamp("[DEBUG] get_latest_ph_reading() -> no pH device assigned.")
        return None

    with ph_lock:
        if latest_ph_value is not None:
            log_with_timestamp(f"[DEBUG] get_latest_ph_reading() -> returning {latest_ph_value}")
            return latest_ph_value

    log_with_timestamp("[DEBUG] get_latest_ph_reading() -> no pH reading available.")
    return None

def graceful_exit(signum, frame):
    log_with_timestamp(f"[DEBUG] Received signal {signum}. Doing graceful_exit...")
    try:
        stop_serial_reader()
    except Exception as e:
        log_with_timestamp(f"[DEBUG] Error during cleanup: {e}")
    log_with_timestamp("[DEBUG] Cleanup complete. Exiting.")
    raise SystemExit()

def handle_stop_signal(signum, frame):
    log_with_timestamp(f"[DEBUG] Received signal {signum} (SIGTSTP). will graceful_exit..")
    graceful_exit(signum, frame)


# ----------------------------------------------------------------------
# QUEUE-BASED SLOPE QUERY: Turn off continuous mode, request slope
# ----------------------------------------------------------------------

def enqueue_disable_continuous():
    """
    Enqueues a command to disable continuous output: C,0
    """
    log_with_timestamp("[DEBUG] enqueue_disable_continuous() -> putting C,0 in queue.")
    enqueue_command("C,0", "general")

def enqueue_enable_continuous():
    """
    Enqueues a command to re-enable continuous output: C,1
    """
    log_with_timestamp("[DEBUG] enqueue_enable_continuous() -> putting C,1 in queue.")
    enqueue_command("C,1", "general")


def enqueue_slope_query():
    """
    1. Enqueue "C,0" to stop continuous streaming
    2. Enqueue "Slope,?" so we can get a well-formed slope response
    3. We do NOT re-enable continuous mode here, unless you want to.
       Wait up to 3 seconds for parse_buffer() to see the "?Slope," line.
    """
    global slope_event, slope_data

    log_with_timestamp("[DEBUG] enqueue_slope_query() called. Will set up slope_event and slope_data.")
    slope_event = event.Event()
    slope_data = None

    # Step 1: turn off continuous
    #log_with_timestamp("[DEBUG] enqueue_slope_query() -> disabling continuous mode by queueing 'C,0'")
    #enqueue_disable_continuous()

    # Step 2: slope
    log_with_timestamp("[DEBUG] enqueue_slope_query() -> queueing 'Slope,?'")
    enqueue_command("Slope,?", "slope_query")

    # We'll only re-enable continuous reading once the slope line arrives,
    # or if you prefer, do it after the function returns.

    log_with_timestamp("[DEBUG] enqueue_slope_query() -> about to WAIT up to 10s for slope_event.")
    try:
        with eventlet.timeout.Timeout(10, False):
            slope_event.wait()
    except eventlet.timeout.Timeout:
        log_with_timestamp("[DEBUG] enqueue_slope_query() -> Timed out waiting for slope_event.")
        return None

    log_with_timestamp(f"[DEBUG] enqueue_slope_query() -> we got slope_event, slope_data={slope_data}")
    return slope_data


def get_slope_info():
    """
    Called from /api/ph/slope endpoint. 
    Returns slope data or None on timeout/failure.
    """
    log_with_timestamp("[DEBUG] get_slope_info() called. Will run enqueue_slope_query() now...")
    result = enqueue_slope_query()
    if result is None:
        log_with_timestamp("[DEBUG] get_slope_info() -> slope_data is None (timed out or not found).")
    else:
        log_with_timestamp(f"[DEBUG] get_slope_info() -> success, slope_data={result}")
        # If you want to re-enable continuous reading right away:
        # enqueue_enable_continuous()
    return result

def get_slope_info():
    """
    Called from /api/ph/slope endpoint. 
    Returns slope data or None on timeout/failure.
    """
    log_with_timestamp("[DEBUG] get_slope_info() called. Will run enqueue_slope_query() now...")
    result = enqueue_slope_query()
    if result is None:
        log_with_timestamp("[DEBUG] get_slope_info() -> slope_data is None (timed out or not found).")
    else:
        log_with_timestamp(f"[DEBUG] get_slope_info() -> success, slope_data={result}")
        # If you want to re-enable continuous reading right away:
        # enqueue_enable_continuous()
    return result
