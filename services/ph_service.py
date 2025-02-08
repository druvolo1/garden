print(f"LOADED ph_service.py from {__file__}", flush=True)

import eventlet
eventlet.monkey_patch()  # Ensure all standard libs are patched early

import signal
import serial
import subprocess
from queue import Queue
from datetime import datetime
from eventlet import tpool

from api.settings import load_settings

# Shared queue for commands sent to the probe
command_queue = Queue()
stop_event = eventlet.event.Event()  # Eventlet's own Event

ph_lock = eventlet.semaphore.Semaphore()

buffer = ""  # Centralized buffer for incoming serial data
latest_ph_value = None  # Store the most recent pH reading
last_sent_command = None
COMMAND_TIMEOUT = 10
MAX_BUFFER_LENGTH = 100

def log_with_timestamp(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)

def enqueue_command(command, command_type="general"):
    command_queue.put({"command": command, "type": command_type})

def send_command_to_probe(ser, command):
    global last_sent_command
    try:
        log_with_timestamp(f"Sending command to probe: {command}")
        ser.write((command + '\r').encode())
        last_sent_command = command
    except Exception as e:
        log_with_timestamp(f"Error sending command '{command}': {e}")

def parse_buffer(ser):
    global buffer, latest_ph_value, last_sent_command

    while '\r' in buffer:
        line, buffer = buffer.split('\r', 1)
        line = line.strip()

        #log_with_timestamp(f"parse_buffer found line: {line!r}")

        if not line:
            log_with_timestamp("Skipping empty line from parse_buffer.")
            continue

        if line in ("*OK", "*ER"):
            if last_sent_command:
                log_with_timestamp(f"Response '{line}' received for command: {last_sent_command}")
                last_sent_command = None
            else:
                log_with_timestamp(f"Unexpected response: {line} (no command was sent)")

            if not command_queue.empty():
                next_cmd = command_queue.get()
                last_sent_command = next_cmd["command"]
                log_with_timestamp(f"Sending next command: {last_sent_command}")
                send_command_to_probe(ser, next_cmd["command"])
            continue

        try:
            ph_value = round(float(line), 2)
            if not (0.0 <= ph_value <= 14.0):
                raise ValueError(f"pH value out of range: {ph_value}")

            with ph_lock:
                latest_ph_value = ph_value
                log_with_timestamp(f"Updated latest pH value: {latest_ph_value}")

        except ValueError as e:
            log_with_timestamp(f"Discarding unexpected response: '{line}' ({e})")

    if buffer:
        log_with_timestamp(f"Partial data retained in buffer: '{buffer}'")

def serial_reader():
    print("DEBUG: Entered serial_reader() at all...")

    while not stop_event.ready():
        settings = load_settings()
        ph_probe_path = settings.get("usb_roles", {}).get("ph_probe")

        try:
            dev_list = subprocess.check_output("ls /dev/serial/by-id", shell=True).decode().splitlines()
            dev_list_str = ", ".join(dev_list) if dev_list else "No devices found"
            log_with_timestamp(f"Devices in /dev/serial/by-id: {dev_list_str}")
        except subprocess.CalledProcessError:
            log_with_timestamp("No devices found in /dev/serial/by-id (subprocess error).")

        log_with_timestamp(f"Currently assigned pH probe device in settings: {ph_probe_path}")

        if not ph_probe_path:
            log_with_timestamp("No pH probe assigned. Retrying in 5s...")
            eventlet.sleep(5)
            continue

        log_with_timestamp(f"Attempting to open pH probe device: {ph_probe_path}")

        try:
            with serial.Serial(ph_probe_path, baudrate=9600, timeout=1) as ser:
                log_with_timestamp(f"Opened serial port {ph_probe_path} for pH reading.")
                # Uncomment if the sensor requires a start command:
                # ser.write(b'R\r')
                while not stop_event.ready():
                    raw_data = tpool.execute(ser.read, 100)
                    if raw_data:
                        #log_with_timestamp(f"Raw data received ({len(raw_data)} bytes): {raw_data!r}")
                        decoded_data = raw_data.decode("utf-8", errors="replace")
                        #log_with_timestamp(f"Decoded data: {decoded_data!r}")
                        with ph_lock:
                            global buffer
                            buffer += decoded_data
                            if len(buffer) > MAX_BUFFER_LENGTH:
                                log_with_timestamp("Buffer exceeded maximum length. Dumping buffer.")
                                buffer = ""
                        parse_buffer(ser)
                    else:
                        eventlet.sleep(0.05)
        except (serial.SerialException, OSError) as e:
            log_with_timestamp(f"Serial error on {ph_probe_path}: {e}. Reconnecting in 5s...")
            eventlet.sleep(5)

def send_configuration_commands(ser):
    try:
        log_with_timestamp("Sending configuration commands to the pH probe...")
        command = "C,2"
        send_command_to_probe(ser, command)
    except Exception as e:
        log_with_timestamp(f"Error sending configuration commands: {e}")

def calibrate_ph(ser, level):
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
    valid_levels = {
        'low': 'Cal,low,4.00',
        'mid': 'Cal,mid,7.00',
        'high': 'Cal,high,10.00',
        'clear': 'Cal,clear'
    }

    if level not in valid_levels:
        return {"status": "failure", "message": f"Invalid calibration level: {level}. Must be one of {list(valid_levels.keys())}."}

    command = valid_levels[level]
    command_queue.put({"command": command, "type": "calibration"})
    return {"status": "success", "message": f"Calibration command '{command}' enqueued."}

def get_last_sent_command():
    global last_sent_command
    if last_sent_command:
        return last_sent_command
    return "No command has been sent yet."

def start_serial_reader():
    eventlet.spawn(serial_reader)
    log_with_timestamp("Serial reader started.")

def stop_serial_reader():
    log_with_timestamp("Stopping serial reader...")
    stop_event.send()  # Fire the event so loops can break
    log_with_timestamp("Serial reader stopped.")

def get_latest_ph_reading():
    global latest_ph_value
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

# Uncomment and add proper signal handling if needed.
# signal.signal(signal.SIGINT, graceful_exit)
# signal.signal(signal.SIGTERM, graceful_exit)
# signal.signal(signal.SIGTSTP, handle_stop_signal)
