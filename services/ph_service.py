import serial
import time
import threading
from api.settings import load_settings
from queue import Queue

# Globals to track the current pH device and lock
current_ph_device = None
ph_lock = threading.Lock()
latest_ph_value = None

# Shared queue for pH readings
ph_reading_queue = Queue()

def listen_for_ph_readings():
    """
    Background thread to listen for pH readings and add them to the queue.
    """
    settings = load_settings()
    ph_device = settings.get("usb_roles", {}).get("ph_probe")

    if not ph_device:
        print("No pH probe device assigned.")
        return

    try:
        with serial.Serial(ph_device, 9600, timeout=1) as ser:
            print(f"Listening on pH probe device: {ph_device}")
            while True:
                line = ser.readline().decode('utf-8').strip()
                if line:
                    try:
                        ph_value = float(line)
                        print(f"Queueing pH value: {ph_value}")
                        ph_reading_queue.put(ph_value)
                    except ValueError:
                        print(f"Invalid data received: {line}")
                else:
                    print("No data received from pH probe.")
    except serial.SerialException as e:
        print(f"Error accessing pH probe device {ph_device}: {e}")

def get_ph_reading():
    """
    Retrieve the latest pH value from the queue.
    """
    try:
        return ph_reading_queue.get_nowait()  # Get the latest value without blocking
    except Queue.Empty:
        print("No pH value available in the queue.")
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
            with serial.Serial(ph_device, 9600, timeout=2) as ser:
                line = ser.readline().decode('utf-8').strip()
                if line:
                    try:
                        ph_value = float(line)
                        print(f"pH value: {ph_value}")
                        if callback:
                            callback(ph_value)
                    except ValueError:
                        print(f"Invalid pH value received: {line}")
        except serial.SerialException as e:
            print(f"Error accessing pH probe device {ph_device}: {e}")
        time.sleep(1)  # Small delay to prevent high CPU usage
