import time
import threading
import eventlet
import signal
import serial
from api.settings import load_settings
from queue import Queue
from datetime import datetime, timedelta
from eventlet import tpool

eventlet.monkey_patch()  # Apply monkey patching at the top of the file

# Shared queue for commands sent to the probe
command_queue = Queue()  # Tracks sent commands and their types
stop_event = threading.Event()  # Event to signal threads to stop
ph_lock = threading.Lock()  # Lock for thread-safe operations

buffer = ""  # Centralized buffer for incoming serial data
latest_ph_value = None  # Store the most recent pH reading
last_sent_command = None  # Store the most recent command sent
COMMAND_TIMEOUT = 10  # Timeout in seconds
MAX_RETRIES = 5  # Maximum number of reconnection attempts
RETRY_DELAY = 5  # Delay between retries in seconds
last_command_time = None  # Global variable to track when the last command was sent
MAX_BUFFER_LENGTH = 100  # Prevent excessive buffer growth

def log_with_timestamp(message):
    """Helper function to log messages with a timestamp."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def enqueue_command(command, command_type="general"):
    """Enqueue a command to be sent to the serial device."""
    command_queue.put({"command": command, "type": command_type})

def send_command_to_probe(ser, command):
    global last_sent_command, last_command_time
    try:
        log_with_timestamp(f"Sending command to probe: {command}")
        ser.write((command + '\r').encode())
        last_sent_command = command
        last_command_time = datetime.now()
    except Exception as e:
        log_with_timestamp(f"Error sending command '{command}': {e}")

def check_command_timeout():
    global last_sent_command, last_command_time
    if last_sent_command and last_command_time:
        if (datetime.now() - last_command_time).total_seconds() > COMMAND_TIMEOUT:
            log_with_timestamp(f"Command '{last_sent_command}' timed out. Clearing it.")
            last_sent_command = None
            last_command_time = None

def parse_buffer(ser):
    """
    Parse the shared buffer for responses and identify the context (e.g., configuration, calibration).
    """
    global buffer, latest_ph_value, last_sent_command

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
            if last_sent_command:
                log_with_timestamp(f"Response '{line}' received for command: {last_sent_command}")
                last_sent_command = None  # Reset after a valid response
            else:
                log_with_timestamp(f"Unexpected response: {line} (no command was sent)")

            # Send the next command if the queue is not empty
            if not command_queue.empty():
                next_command = command_queue.get()
                last_sent_command = next_command["command"]  # Update the last command sent
                log_with_timestamp(f"Sending next command: {last_sent_command}")
                send_command_to_probe(ser, next_command["command"])

            continue

        # Process pH values
        try:
            ph_value = round(float(line), 2)
            if not (0.0 <= ph_value <= 14.0):  # Validate pH range
                raise ValueError(f"pH value out of range: {ph_value}")

            # Update the latest pH value (thread-safe)
            #log_with_timestamp(f"Valid pH value identified: {ph_value}")
            with ph_lock:
                latest_ph_value = ph_value  # Overwrite the current value
                log_with_timestamp(f"Updated latest pH value: {latest_ph_value}")

        except ValueError as e:
            log_with_timestamp(f"Discarding unexpected response: '{line}' ({e})")

    if buffer:
        log_with_timestamp(f"Partial data retained in buffer: '{buffer}'")

def serial_reader():
    while not stop_event.is_set():
        try:
            with serial.Serial(...) as ser:
                while not stop_event.is_set():
                    # Use tpool.execute to run blocking calls
                    raw_data = tpool.execute(ser.read, 100)
                    if raw_data:
                        decoded_data = raw_data.decode('utf-8', errors='replace')
                        with ph_lock:
                            buffer += decoded_data
                            if len(buffer) > MAX_BUFFER_LENGTH:
                                log_with_timestamp("Buffer exceeded maximum length. Dumping buffer.")
                                buffer = ""
                        parse_buffer(ser)
        except (serial.SerialException, OSError) as e:
            log_with_timestamp(f"Serial error: {e}. Reconnecting in 5 seconds...")
            eventlet.sleep(5)
    
def send_configuration_commands(ser):
    try:
        log_with_timestamp("Sending configuration commands to the pH probe...")
        command = "C,2"
        send_command_to_probe(ser, command)  # Directly send the command
    except Exception as e:
        log_with_timestamp(f"Error sending configuration commands: {e}")

def calibrate_ph(ser, level):
    valid_levels = {
        'low': 'Cal,low,4.00',
        'mid': 'Cal,mid,7.00',
        'high': 'Cal,high,10.00',
        'clear': 'Cal,clear'
    }

    if level not in valid_levels:
        log_with_timestamp(f"Invalid calibration level: {level}")
        return {"status": "failure", "message": "Invalid calibration level"}

    global last_sent_command

    with ph_lock:  # Protect access to last_sent_command
        command = valid_levels[level]
        if last_sent_command is None:  # Send directly if no pending command
            send_command_to_probe(ser, command)
            last_sent_command = command
            log_with_timestamp(f"Calibration command '{command}' sent.")
            return {"status": "success", "message": f"Calibration command '{command}' sent"}
        else:
            log_with_timestamp(f"Cannot send calibration command '{command}' while waiting for a response.")
            return {"status": "failure", "message": "A command is already in progress"}

def enqueue_calibration(level):
    """
    Add a calibration command to the command queue.
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
    return {
        "status": "success",
        "message": f"Calibration command '{command}' enqueued."
    }



def get_last_sent_command():
    """
    Retrieve the last command sent to the probe.
    """
    global last_sent_command
    if last_sent_command:
        return last_sent_command
    return "No command has been sent yet."

serial_reader_thread = None  # Add this global variable

def start_serial_reader():
    """Start the serial reader in a green thread."""
    eventlet.spawn(serial_reader)
    log_with_timestamp("Serial reader started.")


def stop_serial_reader():
    log_with_timestamp("Stopping serial reader...")
    stop_event.set()
    try:
        eventlet.sleep(2)  
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
        last_sent_command = None  # Clear the last command before exit
    except Exception as e:
        log_with_timestamp(f"Error during cleanup: {e}")
    log_with_timestamp("Cleanup complete. Exiting application.")
    raise SystemExit()

def handle_stop_signal(signum, frame):
    log_with_timestamp(f"Received signal {signum} (SIGTSTP). Cleaning up...")
    graceful_exit(signum, frame)  # Reuse the existing graceful exit logic


signal.signal(signal.SIGINT, graceful_exit)  # Handle CTRL-C
signal.signal(signal.SIGTERM, graceful_exit)  # Handle termination signals
signal.signal(signal.SIGTSTP, handle_stop_signal)  # Handle CTRL-Z

