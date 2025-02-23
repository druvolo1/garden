# File: services/error_service.py
import serial
import time

# We'll also use set_error, clear_error, get_current_errors from this module

error_codes = {
    "PH_USB_OFFLINE": "pH probe not found or offline",
    "RELAY_USB_OFFLINE": "Relay device not found or offline",
    "PH_OUT_OF_RANGE": "pH reading is outside configured min/max range"
}

_error_state = set()

def set_error(code):
    if code in error_codes:
        _error_state.add(code)

def clear_error(code):
    if code in _error_state:
        _error_state.remove(code)

def get_current_errors():
    return [error_codes[code] for code in _error_state]

def check_relay_offline():
    """
    Attempt to open the relay device path. If it fails, mark `RELAY_USB_OFFLINE`.
    If it succeeds, clear that error.
    """
    from services.pump_relay_service import get_relay_device_path
    try:
        device_path = get_relay_device_path()  # from relay_service
        with serial.Serial(device_path, baudrate=9600, timeout=1) as ser:
            # If open worked, we assume device is present
            pass
        clear_error("RELAY_USB_OFFLINE")
    except Exception as e:
        set_error("RELAY_USB_OFFLINE")

def check_for_hardware_errors():
    """
    Main loop that periodically checks hardware availability.
    We can add more checks (like pH hardware) here as the code evolves.
    """
    import eventlet
    while True:
        check_relay_offline()
        # If we want to add more checks, do them here.
        eventlet.sleep(10)  # check every 10 seconds
