from datetime import datetime
import time
import threading
import eventlet
import signal
from api.settings import load_settings
from queue import Queue

# Shared queue for commands sent to the probe
command_queue = Queue()  # Tracks sent commands and their types
stop_event = threading.Event()  # Event to signal threads to stop
ph_lock = threading.Lock()  # Lock for thread-safe operations

buffer = ""  # Centralized buffer for incoming serial data
latest_ph_value = None  # Store the most recent pH reading


def log_with_timestamp(message):
    """Helper function to log messages with a timestamp."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")


def send_configuration_commands(ser):
    """
    Send configuration commands to the pH probe and enqueue them for tracking.
    Example: Set the polling interval to 2 seconds with the command 'C,2\r'.
    """
    try:
        log_with_timestamp("Sending configuration commands to the pH probe...")
        command = "C,2"
        ser.write((command + "\r").encode())  # Send the command as bytes
        command_queue.put({"command": command, "type": "configuration"})  # Track the command
        log_with_timestamp(f"Configuration command sent: {command}")
    except Exception as e:
        log_with_timestamp(f"Error sending configuration commands: {e}")


def parse_buffer():
    """
    Parse the shared buffer for responses and identify the context (e.g., configuration, calibration).
    """
    global buffer, latest_ph_value

    while '\r' in buffer:  # Process complete lines
        # Split the buffer at the first '\r'
        line, buffer = buffer.split('\r', 1)
        line = line.strip()

        # Skip empty lines
        if not line:
            log_with_timestamp("Skipping empty line.")
            continue

        # Handle responses (*OK, *ER)
        if line in ("*OK", "*ER"):
            if not command_queue.empty():
                sent_command = command_queue.get()  # Dequeue the oldest command
                if line == "*OK":
                    log_with_timestamp(f"{sent_command['type'].capitalize()} command '{sent_command['command']}' acknowledged successfully.")
                elif line == "*ER":
                    log_with_timestamp(f"{sent_command['type'].capitalize()} command '{sent_command['command']}' failed.")
            else:
                log_with_timestamp(f"Unexpected response: {line} (no outstanding command)")
            continue

        # Process pH values
        try:
            ph_value = round(float(line), 2)
            if not (0.0 <= ph_value <= 14.0):  # Validate pH range
                raise ValueError(f"pH value out of range: {ph_value}")

            # Update the latest pH value (thread-safe)
            log_with_timestamp(f"Valid pH value identified: {ph_value}")
            with ph_lock:
                latest_ph_value = ph_value  # Overwrite the current value
                log_with_timestamp(f"Updated latest pH value: {latest_ph_value}")

        except ValueError as e:
            log_with_timestamp(f"Discarding unexpected response: '{line}' ({e})")

    if buffer:
        log_with_timestamp(f"Partial data retained in buffer: '{buffer}'")

def serial_reader():
    """
    Centralized thread to manage the serial connection, send commands, and populate the buffer.
    Handles both pH readings and calibration/configuration commands.
    """
    global buffer

    settings = load_settings()
    ph_device = settings.get("usb_roles", {}).get("ph_probe")

    if not ph_device:
        log_with_timestamp("No pH probe device assigned.")
        return

    MAX_BUFFER_LENGTH = 100  # Limit buffer size to prevent excessive growth

    while not stop_event.is_set():
        try:
            import serial  # Only load serial in the reader thread
            with serial.Serial(
                ph_device,
                9600,
                timeout=1,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            ) as ser:
                log_with_timestamp(f"Connected to pH probe device: {ph_device}")
                ser.flushInput()
                ser.flushOutput()

                while not stop_event.is_set():
                    try:
                        # Send any queued commands
                        if not command_queue.empty():
                            command_data = command_queue.get()  # Dequeue the next command
                            command = command_data["command"]
                            log_with_timestamp(f"Sending {command_data['type']} command: {command}")
                            ser.write((command + '\r').encode())  # Send the command

                        # Read data from the serial port
                        raw_data = ser.read(100)
                        if raw_data:
                            decoded_data = raw_data.decode('utf-8', errors='replace')
                            with ph_lock:
                                buffer += decoded_data  # Append to buffer
                                if len(buffer) > MAX_BUFFER_LENGTH:
                                    log_with_timestamp("Buffer exceeded maximum length. Dumping buffer.")
                                    buffer = ""  # Empty the buffer
                            parse_buffer()
                        else:
                            log_with_timestamp("No data received in this read.")

                    except (serial.SerialException, OSError) as e:
                        log_with_timestamp(f"Serial error: {e}. Reconnecting in 5 seconds...")
                        eventlet.sleep(5)
                        break  # Exit the loop to reconnect
        except (serial.SerialException, OSError) as e:
            log_with_timestamp(f"Failed to connect to pH probe: {e}. Retrying in 10 seconds...")
            eventlet.sleep(10)


def calibrate_ph(level):
    """
    Calibrate the pH sensor at the specified level (low/mid/high/clear).
    Sends the calibration command through the existing serial connection
    and waits for a response (*OK or *ER).
    """
    valid_levels = {
        'low': 'Cal,low,4.00',
        'mid': 'Cal,mid,7.00',
        'high': 'Cal,high,10.00',
        'clear': 'Cal,clear'
    }

    if level not in valid_levels:
        log_with_timestamp(f"Invalid calibration level: {level}")
        return {"status": "failure", "message": "Invalid calibration level"}

    global command_queue

    command = valid_levels[level]
    command_queue.put({"command": command, "type": "calibration"})  # Track the command
    log_with_timestamp(f"Calibration command '{command}' queued for execution.")
    return {"status": "success", "message": f"Calibration command '{command}' queued"}

def start_serial_reader():
    stop_event.clear()
    eventlet.spawn(serial_reader)
    log_with_timestamp("Serial reader started with eventlet.")

def stop_serial_reader():
    log_with_timestamp("Stopping serial reader...")
    stop_event.set()
    try:
        eventlet.sleep(2)  # Or time.sleep(2) if using native threads
    except SystemExit:
        log_with_timestamp("SystemExit occurred during serial reader stop.")
    except Exception as e:
        log_with_timestamp(f"Error stopping serial reader: {e}")
    log_with_timestamp("Serial reader stopped.")

def get_latest_ph_reading():
    """
    Retrieve the most recent pH value.
    """
    global latest_ph_value
    with ph_lock:
        if latest_ph_value is not None:
            return latest_ph_value
    log_with_timestamp("No pH reading available.")
    return None

def graceful_exit(signum, frame):
    log_with_timestamp(f"Received signal {signum}. Cleaning up...")
    try:
        # Perform cleanup operations directly
        stop_serial_reader()  # Stop the serial reader gracefully
        stop_event.set()      # Signal other threads to stop
    except Exception as e:
        log_with_timestamp(f"Error during cleanup: {e}")
    log_with_timestamp("Cleanup complete. Exiting application.")
    raise SystemExit()


signal.signal(signal.SIGINT, graceful_exit)
signal.signal(signal.SIGTERM, graceful_exit)
