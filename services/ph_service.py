import serial
import time
import threading
from api.settings import load_settings
from queue import Queue, Empty

# Globals to track the current pH device and lock
current_ph_device = None
ph_lock = threading.Lock()
serial_lock = threading.Lock()  # Prevent multiple access to the serial port
latest_ph_value = None

# Shared queue for pH readings
ph_reading_queue = Queue()


def listen_for_ph_readings():
    """
    Background thread to listen for pH readings and put them in the queue.
    Reconnects automatically if the serial device is disconnected.
    """
    settings = load_settings()
    ph_device = settings.get("usb_roles", {}).get("ph_probe")

    if not ph_device:
        print("No pH probe device assigned.")
        return

    consecutive_no_data = 0  # Track consecutive empty reads

    while True:
        try:
            with serial_lock, serial.Serial(
                ph_device,
                9600,
                timeout=1,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            ) as ser:
                print(f"Listening on pH probe device: {ph_device}")
                ser.flushInput()
                ser.flushOutput()

                buffer = b""  # Buffer for accumulating incoming bytes

                while True:
                    try:
                        raw_data = ser.read(100)
                        if raw_data:
                            consecutive_no_data = 0  # Reset the counter
                            buffer += raw_data
                            print(f"Raw bytes received: {raw_data}")  # Debug raw data

                            while b'\r' in buffer:
                                line, buffer = buffer.split(b'\r', 1)
                                line = line.decode('utf-8', errors='replace').strip()
                                if line:
                                    try:
                                        ph_value = float(line)
                                        print(f"Received pH value: {ph_value}")
                                        ph_reading_queue.put(ph_value)
                                    except ValueError:
                                        print(f"Invalid pH value: {line}")
                        else:
                            consecutive_no_data += 1
                            if consecutive_no_data > 5:
                                print("No data received in multiple reads.")
                    except serial.SerialException as e:
                        print(f"Error reading from serial: {e}")
                        break  # Exit inner loop to retry the connection
        except serial.SerialException as e:
            print(f"Serial error: {e}. Retrying in 10 seconds...")
            time.sleep(10)  # Wait before retrying


def get_ph_reading():
    """
    Retrieve the latest pH value from the queue, waiting for new data if necessary.
    """
    try:
        # Wait for up to 2 seconds for new data in the queue
        return ph_reading_queue.get(timeout=2)
    except Empty:
        print("No new pH value available in the queue.")
        return None


def calibrate_ph(level):
    """Calibrate the pH sensor at the specified level (low/mid/high)."""
    valid_levels = ['low', 'mid', 'high']
    if level not in valid_levels:
        print(f"Invalid calibration level: {level}")
        return False

    settings = load_settings()
    ph_probe_device = settings["usb_roles"].get("ph_probe")

    # Check if a pH probe is assigned
    if not ph_probe_device:
        print("No pH probe assigned. Skipping calibration.")
        return False

    command = {'low': 'Cal,low', 'mid': 'Cal,mid', 'high': 'Cal,high'}[level]

    try:
        with serial.Serial(ph_probe_device, 9600, timeout=1) as ser:
            ser.write((command + '\r').encode())
        print(f"pH probe calibrated at {level} level.")
        return True
    except serial.SerialException as e:
        print(f"Error calibrating pH probe on device {ph_probe_device}: {e}")
        return False


def update_ph_device(device):
    """Update the current pH probe device."""
    global current_ph_device
    with ph_lock:
        current_ph_device = device
        print(f"Updated pH probe device: {current_ph_device}")


def monitor_ph(callback):
    """
    Continuously monitor the pH probe for readings.
    If a callback is provided, it will be called with each valid pH value.
    """
    global current_ph_device
    while True:
        with ph_lock:
            ph_device = current_ph_device

        if not ph_device:
            print("No pH probe device assigned. Waiting for assignment.")
            time.sleep(1)
            continue

        try:
            with serial_lock, serial.Serial(
                ph_device,
                9600,
                timeout=1,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            ) as ser:
                ser.flushInput()
                ser.flushOutput()

                buffer = b""  # Buffer for accumulating incoming bytes

                while True:
                    try:
                        raw_data = ser.read(100)
                        if raw_data:
                            buffer += raw_data
                            print(f"Raw bytes received: {raw_data}")
                            while b'\r' in buffer:
                                line, buffer = buffer.split(b'\r', 1)
                                line = line.decode('utf-8', errors='replace').strip()
                                if line:
                                    try:
                                        ph_value = float(line)
                                        print(f"pH value: {ph_value}")
                                        if callback:
                                            callback(ph_value)
                                    except ValueError:
                                        print(f"Invalid pH value: {line}")
                        else:
                            print("Timeout: No data received.")
                    except serial.SerialException as e:
                        print(f"Error reading from serial: {e}")
                        break
        except serial.SerialException as e:
            print(f"Error accessing pH probe device {ph_device}: {e}")
        time.sleep(10)  # Delay before retrying
