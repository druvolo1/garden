from datetime import datetime
import serial
import time
import threading
from api.settings import load_settings
from queue import Queue, Empty

# Shared queue for pH readings
ph_reading_queue = Queue(maxsize=10)  # Limit queue size to avoid memory issues
stop_event = threading.Event()  # Event to signal threads to stop
ph_lock = threading.Lock()  # Lock for thread-safe operations

def log_with_timestamp(message):
    """Helper function to log messages with a timestamp."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def serial_reader():
    """
    Centralized thread to manage the serial connection and buffer incoming data.
    """
    settings = load_settings()
    ph_device = settings.get("usb_roles", {}).get("ph_probe")

    if not ph_device:
        log_with_timestamp("No pH probe device assigned.")
        return

    MAX_BUFFER_LENGTH = 1024  # Limit buffer size to prevent excessive growth

    while not stop_event.is_set():
        try:
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

                buffer = ""  # Buffer for accumulating incoming data

                while not stop_event.is_set():
                    try:
                        raw_data = ser.read(100)
                        if raw_data:
                            decoded_data = raw_data.decode('utf-8', errors='replace')
                            buffer += decoded_data
                            log_with_timestamp(f"Decoded data appended to buffer: {decoded_data}")

                            # Process complete lines (ending with '\r')
                            while '\r' in buffer:
                                line, buffer = buffer.split('\r', 1)
                                line = line.strip()

                                # Skip invalid or corrupted lines
                                if not line or not line.replace('.', '', 1).isdigit():
                                    log_with_timestamp(f"Skipping invalid line: {line}")
                                    continue

                                try:
                                    # Validate length and value range
                                    if len(line) < 3 or len(line) > 6:
                                        raise ValueError(f"Line length out of bounds: {line}")

                                    ph_value = round(float(line), 2)
                                    if not (0.0 <= ph_value <= 14.0):  # Validate pH range
                                        raise ValueError(f"pH value out of range: {ph_value}")

                                    # Add the valid value to the queue
                                    with ph_lock:
                                        if ph_reading_queue.full():
                                            ph_reading_queue.get_nowait()  # Remove the oldest entry
                                        ph_reading_queue.put(ph_value)
                                    log_with_timestamp(f"Valid pH value received: {ph_value}")

                                except ValueError as e:
                                    log_with_timestamp(f"Invalid line: {line} ({e})")

                            # Trim buffer if it exceeds the maximum allowed length
                            if len(buffer) > MAX_BUFFER_LENGTH:
                                buffer = buffer[-MAX_BUFFER_LENGTH:]
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
    Get the most recent pH value from the queue.
    """
    try:
        return ph_reading_queue.get_nowait()
    except Empty:
        log_with_timestamp("No pH reading available.")
        return None

def calibrate_ph(level):
    """Calibrate the pH sensor at the specified level (low/mid/high)."""
    valid_levels = ['low', 'mid', 'high']
    if level not in valid_levels:
        log_with_timestamp(f"Invalid calibration level: {level}")
        return False

    settings = load_settings()
    ph_probe_device = settings["usb_roles"].get("ph_probe")

    if not ph_probe_device:
        log_with_timestamp("No pH probe assigned. Skipping calibration.")
        return False

    command = {'low': 'Cal,low', 'mid': 'Cal,mid', 'high': 'Cal,high'}[level]

    try:
        with serial.Serial(ph_probe_device, 9600, timeout=1) as ser:
            ser.write((command + '\r').encode())
        log_with_timestamp(f"pH probe calibrated at {level} level.")
        return True
    except serial.SerialException as e:
        log_with_timestamp(f"Error calibrating pH probe on device {ph_probe_device}: {e}")
        return False

def update_ph_device(device):
    """Update the current pH probe device."""
    global current_ph_device
    with ph_lock:
        current_ph_device = device
        log_with_timestamp(f"Updated pH probe device: {current_ph_device}")
