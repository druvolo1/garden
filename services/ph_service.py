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


def log_with_timestamp(message):
    """Helper function to log messages with a timestamp."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")


def parse_buffer():
    """
    Parse the shared buffer for pH readings and calibration responses (*OK, *ER).
    """
    global buffer, latest_ph_value
    with ph_lock:
        while '\r' in buffer:
            # Split the buffer at the first '\r'
            line, buffer = buffer.split('\r', 1)
            line = line.strip()

            if not line:
                continue  # Skip empty lines

            # Handle calibration responses
            if line == "*OK":
                log_with_timestamp("Calibration successful.")
                continue  # Keep parsing the buffer
            elif line == "*ER":
                log_with_timestamp("Calibration failed.")
                continue  # Keep parsing the buffer

            # Handle pH readings
            try:
                if line.replace('.', '', 1).isdigit():  # Check if line is a numeric value
                    ph_value = round(float(line), 2)
                    if 0.0 <= ph_value <= 14.0:  # Validate pH range
                        latest_ph_value = ph_value  # Update the global latest value
                        if ph_reading_queue.full():
                            ph_reading_queue.get_nowait()  # Remove the oldest entry
                        ph_reading_queue.put(ph_value)  # Add to the queue
                        log_with_timestamp(f"Valid pH value received: {ph_value}")
                    else:
                        log_with_timestamp(f"Invalid pH value out of range: {ph_value}")
                else:
                    log_with_timestamp(f"Invalid line format: {line}")
            except ValueError as e:
                log_with_timestamp(f"Error parsing line: {line} ({e})")


def serial_reader():
    """
    Centralized thread to manage the serial connection and populate the buffer.
    """
    settings = load_settings()
    ph_device = settings.get("usb_roles", {}).get("ph_probe")

    if not ph_device:
        log_with_timestamp("No pH probe device assigned.")
        return

    MAX_BUFFER_LENGTH = 1024  # Limit buffer size to prevent excessive growth

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
                        raw_data = ser.read(100)
                        if raw_data:
                            decoded_data = raw_data.decode('utf-8', errors='replace')
                            with ph_lock:
                                global buffer
                                buffer += decoded_data  # Append incoming data to the buffer
                                log_with_timestamp(f"Decoded data appended to buffer: {decoded_data}")

                                # Trim the buffer if it exceeds the maximum length
                                if len(buffer) > MAX_BUFFER_LENGTH:
                                    buffer = buffer[-MAX_BUFFER_LENGTH:]

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
