from datetime import datetime
import time
import threading
import eventlet
import signal
from api.settings import load_settings
from queue import Queue, Empty

# Shared queue for pH readings
ph_reading_queue = Queue(maxsize=10)  # Limit queue size to avoid memory issues
stop_event = threading.Event()  # Event to signal threads to stop
ph_lock = threading.Lock()  # Lock for thread-safe operations

buffer = ""  # Centralized buffer for incoming serial data
latest_ph_value = None  # Store the most recent pH reading
last_command_sent = None  # Track the last command sent to the probe


def log_with_timestamp(message):
    """Helper function to log messages with a timestamp."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def send_configuration_commands(ser):
    """
    Send configuration commands to the pH probe and track them.
    Example: Set the polling interval to 2 seconds with the command 'C,2\r'.
    """
    global last_command_sent
    try:
        log_with_timestamp("Sending configuration commands to the pH probe...")
        # Example command to set the polling interval to 2 seconds
        command = "C,2"
        ser.write((command + "\r").encode())  # Send the command as bytes
        last_command_sent = command  # Track the command
        log_with_timestamp("Polling interval set to 2 seconds.")
        # Add more configuration commands here as needed, updating `last_command_sent` for each
    except Exception as e:
        log_with_timestamp(f"Error sending configuration commands: {e}")

def parse_buffer():
    """
    Parse the shared buffer for responses and identify the context (e.g., configuration, calibration).
    """
    global buffer, latest_ph_value, last_command_sent

    while '\r' in buffer:  # Process complete lines
        # Split the buffer at the first '\r'
        line, buffer = buffer.split('\r', 1)
        line = line.strip()

        # Skip empty lines
        if not line:
            log_with_timestamp("Skipping empty line.")
            continue

        # Handle responses based on the last command sent
        if line == "*OK":
            if last_command_sent == "C,2":
                log_with_timestamp("Configuration command (polling interval) acknowledged successfully.")
            elif last_command_sent and last_command_sent.startswith("Cal"):
                log_with_timestamp(f"Calibration successful for command: {last_command_sent}")
            else:
                log_with_timestamp("Unexpected *OK response received.")
            last_command_sent = None  # Clear the last command
            continue
        elif line == "*ER":
            if last_command_sent == "C,2":
                log_with_timestamp("Configuration command (polling interval) failed.")
            elif last_command_sent and last_command_sent.startswith("Cal"):
                log_with_timestamp(f"Calibration failed for command: {last_command_sent}")
            else:
                log_with_timestamp("Unexpected *ER response received.")
            last_command_sent = None  # Clear the last command
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



calibration_command = None  # Shared variable to hold the calibration command

def serial_reader():
    """
    Centralized thread to manage the serial connection and populate the buffer.
    Handles both pH readings and calibration commands.
    """
    global calibration_command, buffer  # Explicitly declare 'buffer' as global

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

                # Call the configuration function after connection
                send_configuration_commands(ser)

                while not stop_event.is_set():
                    try:
                        # Handle calibration commands
                        if calibration_command:
                            log_with_timestamp(f"Sending calibration command: {calibration_command}")
                            ser.write((calibration_command + '\r').encode())
                            calibration_command = None  # Clear the command after sending

                        # Read data from the serial port
                        raw_data = ser.read(100)
                        if raw_data:
                            decoded_data = raw_data.decode('utf-8', errors='replace')
                            #log_with_timestamp(f"Raw data received: '{decoded_data}'")

                            # Append data to the global buffer with the lock
                            with ph_lock:
                                buffer += decoded_data  # Append to buffer
                                if len(buffer) > MAX_BUFFER_LENGTH:
                                    log_with_timestamp("Buffer exceeded maximum length. Dumping buffer.")
                                    buffer = "" #empty the buffer

                            # Process the buffer
                            parse_buffer()

                        else:
                            log_with_timestamp("No data received in this read.")

                    except (serial.SerialException, OSError) as e:
                        log_with_timestamp(f"Serial error: {e}. Reconnecting in 5 seconds...")
                        eventlet.sleep(5)  # Use eventlet.sleep instead of time.sleep
                        break  # Exit the loop to reconnect
        except (serial.SerialException, OSError) as e:
            log_with_timestamp(f"Failed to connect to pH probe: {e}. Retrying in 10 seconds...")
            eventlet.sleep(10)  # Use eventlet.sleep instead of time.sleep



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

    global calibration_command, last_command_sent, buffer

    command = valid_levels[level]
    calibration_command = command
    last_command_sent = command
    log_with_timestamp(f"Calibration command '{command}' queued for execution.")

    response_timeout = time.time() + 5  # Wait for a maximum of 5 seconds
    while time.time() < response_timeout:
        with ph_lock:
            if "*OK" in buffer:
                log_with_timestamp(f"Calibration successful for command: {command}")
                buffer = buffer.replace("*OK", "", 1)  # Remove the processed response
                return {"status": "success", "message": "Calibration successful"}
            elif "*ER" in buffer:
                log_with_timestamp(f"Calibration failed for command: {command}")
                buffer = buffer.replace("*ER", "", 1)  # Remove the processed response
                return {"status": "failure", "message": "Calibration failed"}
        eventlet.sleep(0.1)  # Use eventlet.sleep instead of time.sleep

    log_with_timestamp(f"No calibration response received for command: {command}")
    return {"status": "failure", "message": "No response from pH probe"}

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
