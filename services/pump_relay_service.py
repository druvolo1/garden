# services/pump_relay_service.py

import serial
import json
import os
from services.error_service import set_error, clear_error

# USB Relay Commands
RELAY_ON_COMMANDS = {
    1: b'\xA0\x01\x01\xA2',  # Turn relay 1 ON
    2: b'\xA0\x02\x01\xA3'   # Turn relay 2 ON
}

RELAY_OFF_COMMANDS = {
    1: b'\xA0\x01\x00\xA1',  # Turn relay 1 OFF
    2: b'\xA0\x02\x00\xA2'   # Turn relay 2 OFF
}

relay_status = {
    1: "off",
    2: "off"
}

SETTINGS_FILE = os.path.join(os.getcwd(), "data", "settings.json")

def get_relay_device_path():
    with open(SETTINGS_FILE, "r") as f:
        settings = json.load(f)

    relay_device = settings.get("usb_roles", {}).get("relay")  # 'relay' is the dosing relay role
    if not relay_device:
        raise RuntimeError("No dosing relay device configured in settings.")
    return relay_device

def reinitialize_relay_service():
    try:
        device_path = get_relay_device_path()
        with serial.Serial(device_path, baudrate=9600, timeout=1) as ser:
            # Turn off both relays for a quick test
            ser.write(RELAY_OFF_COMMANDS[1])
            ser.write(RELAY_OFF_COMMANDS[2])
        print("Dosing Relay service reinitialized successfully.")
        clear_error("PUMP_RELAY_OFFLINE")
    except Exception as e:
        print(f"Error reinitializing dosing relay service: {e}")
        set_error("PUMP_RELAY_OFFLINE")

def turn_on_relay(relay_id):
    try:
        device_path = get_relay_device_path()
        with serial.Serial(device_path, baudrate=9600, timeout=1) as ser:
            ser.write(RELAY_ON_COMMANDS[relay_id])
        print(f"Dosing Relay {relay_id} turned ON.")
        relay_status[relay_id] = "on"
        clear_error("PUMP_RELAY_OFFLINE")
    except Exception as e:
        print(f"Error turning on dosing relay {relay_id}: {e}")
        set_error("PUMP_RELAY_OFFLINE")

def turn_off_relay(relay_id):
    try:
        device_path = get_relay_device_path()
        with serial.Serial(device_path, baudrate=9600, timeout=1) as ser:
            ser.write(RELAY_OFF_COMMANDS[relay_id])
        print(f"Dosing Relay {relay_id} turned OFF.")
        relay_status[relay_id] = "off"
        clear_error("PUMP_RELAY_OFFLINE")
    except Exception as e:
        print(f"Error turning off dosing relay {relay_id}: {e}")
        set_error("PUMP_RELAY_OFFLINE")

def get_relay_status(relay_id):
    return relay_status.get(relay_id, "unknown")
