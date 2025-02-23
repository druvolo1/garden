# File: services/valve_relay_service.py

import serial
import json
import os
from services.error_service import set_error, clear_error

# Example commands. Adjust if your valve relay uses different hex codes:
VALVE_ON_COMMANDS = {
    1: b'\xA0\x01\x01\xA2',  
    2: b'\xA0\x02\x01\xA3'
}

VALVE_OFF_COMMANDS = {
    1: b'\xA0\x01\x00\xA1',  
    2: b'\xA0\x02\x00\xA2'
}

valve_status = {
    1: "off",
    2: "off"
}

SETTINGS_FILE = os.path.join(os.getcwd(), "data", "settings.json")

def get_valve_device_path():
    with open(SETTINGS_FILE, "r") as f:
        settings = json.load(f)

    valve_device = settings.get("usb_roles", {}).get("valve_relay")
    if not valve_device:
        raise RuntimeError("No valve relay device configured in settings.")
    return valve_device

def reinitialize_valve_relay_service():
    try:
        device_path = get_valve_device_path()
        with serial.Serial(device_path, baudrate=9600, timeout=1) as ser:
            # Example: turn off both valves
            ser.write(VALVE_OFF_COMMANDS[1])
            ser.write(VALVE_OFF_COMMANDS[2])
        print("Valve Relay service reinitialized successfully.")
        clear_error("VALVE_RELAY_OFFLINE")
    except Exception as e:
        print(f"Error reinitializing valve relay service: {e}")
        set_error("VALVE_RELAY_OFFLINE")

def turn_on_valve(valve_id):
    try:
        device_path = get_valve_device_path()
        with serial.Serial(device_path, baudrate=9600, timeout=1) as ser:
            ser.write(VALVE_ON_COMMANDS[valve_id])
        print(f"Valve {valve_id} turned ON.")
        valve_status[valve_id] = "on"
        clear_error("VALVE_RELAY_OFFLINE")
    except Exception as e:
        print(f"Error turning on valve {valve_id}: {e}")
        set_error("VALVE_RELAY_OFFLINE")

def turn_off_valve(valve_id):
    try:
        device_path = get_valve_device_path()
        with serial.Serial(device_path, baudrate=9600, timeout=1) as ser:
            ser.write(VALVE_OFF_COMMANDS[valve_id])
        print(f"Valve {valve_id} turned OFF.")
        valve_status[valve_id] = "off"
        clear_error("VALVE_RELAY_OFFLINE")
    except Exception as e:
        print(f"Error turning off valve {valve_id}: {e}")
        set_error("VALVE_RELAY_OFFLINE")

def get_valve_status(valve_id):
    return valve_status.get(valve_id, "unknown")
