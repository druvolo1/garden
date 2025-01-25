from datetime import datetime
import time
import threading
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

def parse_buffer():
    """
    Parse the shared buffer for pH readings and calibration responses (*OK, *ER).
    Unexpected lines are discarded if they end with '\r'.
    """
    global buffer, latest_ph_value

    log_with_timestamp(f"Starting buffer parsing. Current buffer: '{buffer}'")

    while '\r' in buffer:  # Process complete lines
        # Split the buffer at the first '\r'
        line, buffer = buffer.split('\r', 1)
        line = line.strip()

        # Log the line being processed
        log_with_timestamp(f"Processing line: '{line}'")

        # Skip empty lines
        if not line:
            log_with_timestamp("Skipping empty line.")
            continue

        # Handle calibration responses
        if line == "*OK":
            log_with_timestamp("Calibration successful.")
            return {"status": "success", "message": "Calibration successful"}
        elif line == "*ER":
            log_with_timestamp("Calibration failed.")
            return {"status": "failure", "message": "Calibration failed"}

        # Process pH values
        try:
            # Validate line as pH value
            if len(line) < 3 or len(line) > 6 or not line.replace('.', '', 1).isdigit():
                raise ValueError(f"Unexpected response or invalid line format: {line}")

            ph_value = round(float(line), 2)
            if not (0.0 <= ph_value <= 14.0):  # Validate pH range
                raise ValueError(f"pH value out of range: {ph_value}")

            # Update latest pH value and add to queue
            log_with_timestamp(f"Valid pH value identified: {ph_value}")
            latest_ph_value = ph_value
            if ph_reading_queue.full():
                log_with_timestamp("Queue is full. Removing oldest value.")
                ph_reading_queue.get_nowait()  # Remove the oldest entry
            ph_reading_queue.put(ph_value)
            log_with_timestamp(f"pH value {ph_value} added to queue. Queue size: {ph_reading_queue.qsize()}")

        except ValueError as e:
            # Log unexpected or invalid lines and discard them
            log_with_timestamp(f"Discarding unexpected response: '{line}' ({e})")

    # Log if buffer still contains partial data
    if buffer:
        log_with_timestamp(f"Partial data retained in buffer: '{buffer}'")


calibration_command = None  # Shared variable to hold the calibration command

def serial_reader():
    """
    Centralized thread to manage the serial connection and populate the buffer.
    Handles both pH readings and calibration commands.
    """
    global calibration_command

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
                        # Handle calibration commands
                        if calibration_command:
                            log_with_timestamp(f"Sending calibration command: {calibration_command}")
                            ser.write((calibration_command + '\r').encode())
                            calibration_command = None  # Clear the command after sending

                        # Read data from the serial port
                        raw_data = ser.read(100)
                        if raw_data:
                            decoded_data = raw_data.decode('utf-8', errors='replace')
                            log_with_timestamp(f"Raw data received: {raw_data}")
                            with ph_lock:
                                global buffer
                                buffer += decoded_data  # Append to buffer
                                log_with_timestamp(f"Decoded data appended to buffer: '{decoded_data}'")

                                # Trim the buffer if it exceeds the maximum length
                                if len(buffer) > MAX_BUFFER_LENGTH:
                                    log_with_timestamp("Buffer exceeded maximum length. Clearing excess.")
                                    buffer = buffer[-MAX_BUFFER_LENGTH:]  # Retain the last MAX_BUFFER_LENGTH characters

                                # Parse the buffer for new data
                                parse_buffer()

                        else:
                            log_with_timestamp("No data received in this read.")
                    except (serial.SerialException, OSError) as e:
                        log_with_timestamp(f"Serial error: {e}. Reconnecting in 5 seconds...")
                        time.sleep(5)
                        break  # Exit inner loop to reconnect
        except (serial.SerialException, OSError) as e:
            log_with_timestamp(f"Failed to connect to pH probe: {e}. Retrying in 10 seconds...")
            time.sleep(10)

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

    global calibration_command, last_command_sent

    command = valid_levels[level]
    calibration_command = command  # Set the command to be sent by `serial_reader`
    last_command_sent = command  # Track the last command for logging and debugging
    log_with_timestamp(f"Calibration command '{command}' queued for execution.")

    # Wait for the response from the probe
    response_timeout = time.time() + 5  # 5-second timeout
    while time.time() < response_timeout:
        with ph_lock:
            if "*OK" in buffer:
                log_with_timestamp(f"Calibration successful for command: {command}")
                buffer = buffer.replace("*OK", "", 1)  # Remove processed response
                return {"status": "success", "message": "Calibration successful"}
            elif "*ER" in buffer:
                log_with_timestamp(f"Calibration failed for command: {command}")
                buffer = buffer.replace("*ER", "", 1)  # Remove processed response
                return {"status": "failure", "message": "Calibration failed"}
        time.sleep(0.1)  # Small delay to prevent busy waiting

    log_with_timestamp(f"No calibration response received for command: {command}")
    return {"status": "failure", "message": "No response from pH probe"}


def start_serial_reader():
    """Start the serial reader thread."""
    stop_event.clear()
    thread = threading.Thread(target=serial_reader, daemon=True)
    thread.start()
    return thread


def stop_serial_reader():
    """Stop the serial reader thread gracefully."""
    log_with_timestamp("Stopping serial reader...")
    stop_event.set()
    time.sleep(2)  # Allow thread to exit gracefully
    log_with_timestamp("Serial reader stopped.")


def get_latest_ph_reading():
    """
    Get the most recent pH value from the queue or fallback to the latest known value.
    """
    global latest_ph_value
    try:
        # Get the most recent value from the queue
        return ph_reading_queue.get_nowait()
    except Empty:
        # If the queue is empty, fallback to the global latest value
        if latest_ph_value is not None:
            return latest_ph_value
        log_with_timestamp("No pH reading available.")
        return None

