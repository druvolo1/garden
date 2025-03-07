# File: ph_service.py
print(f"LOADED ph_service.py from {__file__}", flush=True)

import eventlet
eventlet.monkey_patch()  # Ensure all standard libs are patched early

import signal
import serial
import subprocess
from queue import Queue
from datetime import datetime
from eventlet import tpool
from services.error_service import set_error, clear_error

from utils.settings_utils import load_settings

# Shared queue for commands sent to the probe
command_queue = Queue()
stop_event = eventlet.event.Event()  # Eventlet's own Event

ph_lock = eventlet.semaphore.Semaphore()

buffer = ""  # Centralized buffer for incoming serial data
latest_ph_value = None  # Store the most recent pH reading
last_sent_command = None
COMMAND_TIMEOUT = 10
MAX_BUFFER_LENGTH = 100

ser = None  # Global variable to track the serial connection

def log_with_timestamp(message):
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

def parse_buffer(ser):
    global buffer, latest_ph_value, last_sent_command

    ################### NEW LOGIC ###################
    # If we don't currently have a command in progress
    # but the queue is NOT empty, immediately send the first command.
    if last_sent_command is None and not command_queue.empty():
        next_cmd = command_queue.get()
        last_sent_command = next_cmd["command"]
        log_with_timestamp(f"[DEBUG] No active command. Sending first queued command: {last_sent_command}")
        send_command_to_probe(ser, next_cmd["command"])
    ################### END NEW LOGIC ###################

    while '\r' in buffer:
        line, buffer = buffer.split('\r', 1)
        line = line.strip()

        if not line:
            log_with_timestamp("[DEBUG] parse_buffer: skipping empty line.")
            continue

        #log_with_timestamp(f"[DEBUG] parse_buffer line: {line!r}")

        if line in ("*OK", "*ER"):
            if last_sent_command:
                log_with_timestamp(f"Response '{line}' received for command: {last_sent_command}")
                last_sent_command = None
            else:
                log_with_timestamp(f"Unexpected response: {line} (no command in progress)")

            if not command_queue.empty():
                next_cmd = command_queue.get()
                last_sent_command = next_cmd["command"]
                log_with_timestamp(f"Sending next queued command: {last_sent_command}")
                send_command_to_probe(ser, next_cmd["command"])
            continue

        # Attempt to parse a numeric pH reading
        try:
            ph_value = round(float(line), 2)
            if not (0.0 <= ph_value <= 14.0):
                raise ValueError(f"pH out of range: {ph_value}")
            with ph_lock:
                latest_ph_value = ph_value
                log_with_timestamp(f"Updated latest pH value: {latest_ph_value}")
        except ValueError as e:
            log_with_timestamp(f"Discarding unexpected response: '{line}' ({e})")

    if buffer:
        log_with_timestamp(f"[DEBUG] parse_buffer leftover buffer: {buffer!r}")


def serial_reader():
    """
    Main loop that reads from the assigned ph_probe_path, stores data in `buffer`,
    and calls parse_buffer() to handle lines and commands.
    """
    global ser  # Use the global serial connection
    print("DEBUG: Entered serial_reader() at all...")

    while not stop_event.ready():
        settings = load_settings()
        ph_probe_path = settings.get("usb_roles", {}).get("ph_probe")

        # If no pH device is assigned, quietly wait 5s and skip
        if not ph_probe_path:
            clear_error("PH_USB_OFFLINE")
            eventlet.sleep(5)
            continue

        try:
            # Optional: just for debugging, list /dev/serial/by-id devices
            dev_list = subprocess.check_output("ls /dev/serial/by-id", shell=True).decode().splitlines()
            dev_list_str = ", ".join(dev_list) if dev_list else "No devices found"
            log_with_timestamp(f"Devices in /dev/serial/by-id: {dev_list_str}")
        except subprocess.CalledProcessError:
            log_with_timestamp("No devices found in /dev/serial/by-id (subprocess error).")

        log_with_timestamp(f"Currently assigned pH probe device: {ph_probe_path}")

        try:
            ser = serial.Serial(ph_probe_path, baudrate=9600, timeout=1)
            clear_error("PH_USB_OFFLINE")
            log_with_timestamp(f"Opened serial port {ph_probe_path} for pH reading.")

            # Clear buffer on new device connection
            with ph_lock:
                global buffer
                buffer = ""
                log_with_timestamp("Buffer cleared on new device connection.")

            while not stop_event.ready():
                # Read up to 100 bytes
                raw_data = tpool.execute(ser.read, 100)
                if raw_data:
                    # Debug: show raw bytes
                    #log_with_timestamp(f"[DEBUG] Received raw bytes: {raw_data}")
                    decoded_data = raw_data.decode("utf-8", errors="replace")
                    with ph_lock:
                        buffer += decoded_data
                        if len(buffer) > MAX_BUFFER_LENGTH:
                            log_with_timestamp("Buffer exceeded max length. Dumping buffer.")
                            buffer = ""
                    parse_buffer(ser)
                else:
                    # minimal sleep
                    eventlet.sleep(0.05)

        except (serial.SerialException, OSError) as e:
            log_with_timestamp(f"Serial error on {ph_probe_path}: {e}. Reconnecting in 5s...")
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

    # Clear buffer & reading
    with ph_lock:
        buffer = ""
        latest_ph_value = None
        log_with_timestamp("Buffer and latest pH value cleared.")

    stop_serial_reader()

    # Small delay to ensure the old thread is done
    eventlet.sleep(1)

    stop_event = eventlet.event.Event()
    start_serial_reader()

def get_last_sent_command():
    global last_sent_command
    if last_sent_command:
        return last_sent_command
    return "No command has been sent yet."

def start_serial_reader():
    """
    Spawns the background serial_reader thread using Eventlet.
    """
    eventlet.spawn(serial_reader)
    log_with_timestamp("Serial reader started.")

def stop_serial_reader():
    """
    Signals the serial_reader thread to stop, closes the serial port, and clears buffer/state.
    """
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
    """
    Returns the most recent pH reading if a pH device is assigned.
    - If no pH device assigned, returns None with NO log message.
    - If a device is assigned but no reading, logs "No pH reading available." once and returns None.
    """
    global latest_ph_value

    settings = load_settings()
    ph_probe_path = settings.get("usb_roles", {}).get("ph_probe")
    if not ph_probe_path:
        # No device assigned -> return None, no log
        return None

    with ph_lock:
        if latest_ph_value is not None:
            return latest_ph_value

    # If we have a device assigned but haven't gotten a reading yet
    log_with_timestamp("No pH reading available.")
    return None

def graceful_exit(signum, frame):
    """
    Called on SIGINT/SIGTERM. Cleans up serial_reader then exits.
    """
    log_with_timestamp(f"Received signal {signum}. Cleaning up...")
    try:
        stop_serial_reader()
    except Exception as e:
        log_with_timestamp(f"Error during cleanup: {e}")
    log_with_timestamp("Cleanup complete. Exiting application.")
    raise SystemExit()

def handle_stop_signal(signum, frame):
    """
    Called on SIGTSTP. You could decide if you want to handle that differently.
    """
    log_with_timestamp(f"Received signal {signum} (SIGTSTP). Cleaning up...")
    graceful_exit(signum, frame)

# Uncomment and add proper signal handling if needed:
# signal.signal(signal.SIGINT, graceful_exit)
# signal.signal(signal.SIGTERM, graceful_exit)
# signal.signal(signal.SIGTSTP, handle_stop_signal)
