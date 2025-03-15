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
    Reads data from the global `buffer`, splits on '\r',
    attempts to parse numeric pH readings, and filters out
    obviously noisy or implausible readings.
    On success, update latest_ph_value & possibly emit status_update.
    """
    global buffer, latest_ph_value, last_sent_command
    global old_ph_value, last_read_time
    global ph_jumps

    # If we have a queued command but no active command
    if last_sent_command is None and not command_queue.empty():
        next_cmd = command_queue.get()
        last_sent_command = next_cmd["command"]
        log_with_timestamp(f"[DEBUG] No active command. Sending first queued command: {last_sent_command}")
        send_command_to_probe(ser, next_cmd["command"])

    while '\r' in buffer:
        line, buffer = buffer.split('\r', 1)
        line = line.strip()
        if not line:
            log_with_timestamp("[DEBUG] parse_buffer: skipping empty line.")
            continue

        # Check for "*OK" or "*ER" responses
        if line in ("*OK", "*ER"):
            if last_sent_command:
                log_with_timestamp(f"Response '{line}' received for command: {last_sent_command}")
                last_sent_command = None
            else:
                log_with_timestamp(f"Unexpected response '{line}' (no command in progress)")

            # Send next command if queue is not empty
            if not command_queue.empty():
                next_cmd = command_queue.get()
                last_sent_command = next_cmd["command"]
                log_with_timestamp(f"Sending next queued command: {last_sent_command}")
                send_command_to_probe(ser, next_cmd["command"])
            continue

        # Try to parse a numeric pH reading
        try:
            ph_value = round(float(line), 2)

            # #4: If reading is exactly 0 or 14 => post notification that something is wrong
            if ph_value == 0 or ph_value == 14:
                set_status("ph_probe", "ph_value", "error",
                           f"Unrealistic reading ({ph_value}). Probe or calibration issue?")

            # pH < 1.0 -> skip as noise
            if ph_value < 1.0:
                raise ValueError(f"Ignoring pH <1.0 (noise?). Got {ph_value}")

            # If old_ph_value is not None AND delta > 2.0, skip as improbable
            if old_ph_value is not None:
                delta = abs(ph_value - old_ph_value)

                # #5: Track big swings if delta > 1
                if delta > 1.0:
                    now = datetime.now()
                    # Add this jump timestamp
                    ph_jumps.append(now)
                    # Remove anything older than 1 minute
                    cutoff = now - timedelta(seconds=60)
                    ph_jumps = [t for t in ph_jumps if t >= cutoff]

                    # If we have 5 big jumps in the last minute => notification
                    if len(ph_jumps) >= 5:
                        set_status("ph_probe", "ph_value", "error",
                                   "Frequent large pH swings (5+ in last minute). Probe may be failing.")

                if delta > 2.0:
                    # If the last reading was invalid (like >14), accept the new reading
                    if old_ph_value > 14 or old_ph_value < 1:
                        log_with_timestamp(f"Accepting pH correction from {old_ph_value} -> {ph_value}")
                    else:
                        raise ValueError(
                            f"Ignoring pH jump >2 from old {old_ph_value} -> new {ph_value}"
                        )

            # Accept the new pH
            with ph_lock:
                latest_ph_value = ph_value
                log_with_timestamp(f"Updated latest pH value: {latest_ph_value}")

            old_ph_value = ph_value
            last_read_time = datetime.now()

            from status_namespace import emit_status_update
            emit_status_update()

            # If we have a 'reading' error posted, now that we've got a good reading, clear it
            clear_status("ph_probe", "reading")

        except ValueError as e:
            log_with_timestamp(f"Ignoring line '{line}': {e}")

    # If leftover buffer remains (no '\r' found), do nothing
    if buffer:
        log_with_timestamp(f"[DEBUG] parse_buffer leftover buffer: {buffer!r}")

def serial_reader():
    """
    Main loop that reads from the assigned ph_probe_path, stores data in `buffer`,
    and calls parse_buffer() to handle lines and commands.
    """
    global ser, buffer, latest_ph_value, old_ph_value, last_read_time

    print("DEBUG: Entered serial_reader() at all...")

    # Track the last time we set an error for "no reading"
    last_no_reading_error = None

    while not stop_event.ready():
        settings = load_settings()
        ph_probe_path = settings.get("usb_roles", {}).get("ph_probe")

        # If no pH device is assigned, quietly wait 5s and skip
        if not ph_probe_path:
            # Clear any "communication" or "reading" errors, since we have no device assigned
            clear_status("ph_probe", "communication")
            clear_status("ph_probe", "reading")
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
            ser = serial.Serial(ph_probe_path, baudrate=9600, timeout=1)
            # If we successfully open it, set communication=ok
            set_status("ph_probe", "communication", "ok", f"Opened {ph_probe_path} for pH reading.")
            clear_error("PH_USB_OFFLINE")  # legacy error handling

            # Clear buffer on new device connection
            with ph_lock:
                buffer = ""
                old_ph_value = None
                latest_ph_value = None
                last_read_time = None
                log_with_timestamp("Buffer cleared on new device connection.")

            while not stop_event.ready():
                # #3: If we've assigned a device but haven't gotten a reading for a while => reading error
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
                    # If we have had a reading, check if > 10s old
                    # We'll skip that for now to keep it minimal
                    pass

                raw_data = tpool.execute(ser.read, 100)
                if raw_data:
                    decoded_data = raw_data.decode("utf-8", errors="replace")
                    with ph_lock:
                        buffer += decoded_data
                        # #6: Buffer overflow => notification
                        if len(buffer) > MAX_BUFFER_LENGTH:
                            log_with_timestamp("Buffer exceeded max length. Dumping buffer.")
                            set_status("ph_probe", "communication", "error",
                                       "Buffer exceeded max length. Dumping buffer.")
                            buffer = ""
                    parse_buffer(ser)
                else:
                    eventlet.sleep(0.05)

        except (serial.SerialException, OSError) as e:
            log_with_timestamp(f"Serial error on {ph_probe_path}: {e}. Reconnecting in 5s...")
            set_status("ph_probe", "communication", "error", f"Cannot open {ph_probe_path}: {e}")
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
