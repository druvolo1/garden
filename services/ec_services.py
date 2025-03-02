# File: services/ec_service.py
import eventlet
eventlet.monkey_patch()

import signal
import serial
import subprocess
from queue import Queue
from datetime import datetime
from eventlet import tpool
from utils.settings_utils import load_settings
from services.error_service import set_error, clear_error
from eventlet import event

ec_command_queue = Queue()
ec_stop_event = event.Event()

ec_lock = eventlet.semaphore.Semaphore()
ec_buffer = ""
latest_ec_value = None
last_ec_command = None

MAX_BUFFER_LENGTH = 100

ec_ser = None  # The serial connection for the EC meter

def log_with_timestamp(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def parse_ec_buffer():
    """
    Parses 'ec_buffer' for line(s). If a line is numeric, we treat it as an EC reading.
    If it’s '*OK' or '*ER', we handle command acknowledgment from queue.
    """
    global ec_buffer, latest_ec_value, last_ec_command

    while '\r' in ec_buffer:
        line, ec_buffer = ec_buffer.split('\r', 1)
        line = line.strip()

        if not line:
            log_with_timestamp("Skipping empty line from EC parse.")
            continue

        # Check for ack responses (like pH)
        if line in ("*OK", "*ER"):
            if last_ec_command:
                log_with_timestamp(f"EC meter response '{line}' to command: {last_ec_command}")
                last_ec_command = None
            else:
                log_with_timestamp(f"EC meter got response {line}, but no command was pending.")

            # If we have queued commands, send next
            if not ec_command_queue.empty():
                next_cmd = ec_command_queue.get()
                last_ec_command = next_cmd
                send_ec_command(next_cmd)
            continue

        # Attempt to parse a numeric EC reading
        try:
            # E.g. if your meter outputs "1234" for 1.234 mS, or something similar
            ec_val = float(line)
            # Optionally check range if you know typical min/max
            if ec_val < 0 or ec_val > 9999:
                raise ValueError(f"EC out of plausible range: {ec_val}")

            with ec_lock:
                latest_ec_value = ec_val
            log_with_timestamp(f"Updated latest EC value: {latest_ec_value}")
        except ValueError as e:
            log_with_timestamp(f"Discarding non-numeric or invalid EC line: '{line}' ({e})")

def send_ec_command(cmd):
    global ec_ser, last_ec_command
    if not ec_ser or not ec_ser.is_open:
        log_with_timestamp("Cannot send command. EC serial not open.")
        return

    try:
        log_with_timestamp(f"Sending EC command: {cmd}")
        ec_ser.write((cmd + '\r').encode())
    except Exception as e:
        log_with_timestamp(f"Error sending EC command '{cmd}': {e}")
        last_ec_command = None

def ec_serial_reader():
    global ec_ser, ec_buffer
    log_with_timestamp("EC serial reader started.")

    while not ec_stop_event.ready():
        # 1) Check assigned device
        settings = load_settings()
        ec_path = settings.get("usb_roles", {}).get("ec_meter")
        if not ec_path:
            # No device assigned, wait
            clear_error("EC_USB_OFFLINE")
            eventlet.sleep(5)
            continue

        # 2) Attempt to open EC device
        try:
            ec_ser = serial.Serial(ec_path, baudrate=9600, timeout=1)
            clear_error("EC_USB_OFFLINE")
            log_with_timestamp(f"Opened EC serial port {ec_path}. Buffer cleared.")
            with ec_lock:
                ec_buffer = ""

            # 3) Main read loop
            while not ec_stop_event.ready():
                raw = tpool.execute(ec_ser.read, 100)
                if raw:
                    decoded = raw.decode("utf-8", errors="replace")
                    with ec_lock:
                        ec_buffer += decoded
                        if len(ec_buffer) > MAX_BUFFER_LENGTH:
                            log_with_timestamp("EC buffer exceeded max length, clearing.")
                            ec_buffer = ""
                    parse_ec_buffer()
                else:
                    eventlet.sleep(0.05)

        except (serial.SerialException, OSError) as e:
            log_with_timestamp(f"EC serial error on {ec_path}: {e}, retry in 5s.")
            set_error("EC_USB_OFFLINE")
            eventlet.sleep(5)
        finally:
            if ec_ser and ec_ser.is_open:
                ec_ser.close()
                log_with_timestamp("EC serial connection closed.")

def start_ec_serial_reader():
    """
    Spawns the background EC serial reader thread.
    """
    log_with_timestamp("Starting EC serial reader thread...")
    eventlet.spawn(ec_serial_reader)

def stop_ec_serial_reader():
    """
    Signals the EC reader to stop, clears buffer/EC value, closes the port.
    """
    global ec_buffer, latest_ec_value, ec_ser
    log_with_timestamp("Stopping EC serial reader...")

    with ec_lock:
        ec_buffer = ""
        latest_ec_value = None

    if ec_ser and ec_ser.is_open:
        ec_ser.close()
    ec_stop_event.send()
    log_with_timestamp("EC serial reader stopped.")

def get_latest_ec_reading():
    """
    Returns the most recent EC reading if the ec_meter is assigned & we have data,
    else None.
    """
    settings = load_settings()
    ec_path = settings.get("usb_roles", {}).get("ec_meter")
    if not ec_path:
        return None  # No device assigned

    with ec_lock:
        return latest_ec_value

def enqueue_calibration_command(level):
    """
    Similar to pH: for example 'Cal,low', 'Cal,high', etc. 
    Add your own logic. We'll do dummy commands for now.
    """
    valid = {
        "low": "Cal,low,1.00",   # hypothetical low standard
        "high": "Cal,high,5.00",
        "clear": "Cal,clear"
    }
    if level not in valid:
        return {
            "status": "failure",
            "message": f"Invalid calibration level: {level}"
        }

    cmd = valid[level]
    ec_command_queue.put(cmd)
    return {
        "status": "success",
        "message": f"EC calibration command enqueued: {cmd}"
    }

def restart_ec_serial_reader():
    """
    Stop + Start the EC serial reader fresh.
    """
    log_with_timestamp("Restarting EC serial reader...")
    stop_ec_serial_reader()
    eventlet.sleep(1)
    global ec_stop_event
    ec_stop_event = event.Event()
    start_ec_serial_reader()
