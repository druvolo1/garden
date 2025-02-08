# File: services/relay_service.py

import serial
import json
import os

# USB Relay Commands
RELAY_ON_COMMANDS = {
    1: b'\xA0\x01\x01\xA2',  # Turn relay 1 ON
    2: b'\xA0\x02\x01\xA3'   # Turn relay 2 ON
}

RELAY_OFF_COMMANDS = {
    1: b'\xA0\x01\x00\xA1',  # Turn relay 1 OFF
    2: b'\xA0\x02\x00\xA2'   # Turn relay 2 OFF
}

# Status of relays (mock storage for state)
relay_status = {
    1: "off",
    2: "off"
}

# Path to the settings file
SETTINGS_FILE = os.path.join(os.getcwd(), "data", "settings.json")

def get_relay_device_path():
    """
    Load the relay USB device path from settings.json.
    (Make sure settings.json has usb_roles.relay set)
    """
    import os
    import json

    SETTINGS_FILE = os.path.join(os.getcwd(), "data", "settings.json")
    with open(SETTINGS_FILE, "r") as f:
        settings = json.load(f)

    relay_device = settings.get("usb_roles", {}).get("relay")
    if not relay_device:
        raise RuntimeError("No relay device configured in settings.")
    return relay_device

def turn_on_relay(relay_id):
    try:
        device_path = get_relay_device_path()
        with serial.Serial(device_path, baudrate=9600, timeout=1) as ser:
            ser.write(RELAY_ON_COMMANDS[relay_id])
        print(f"Relay {relay_id} turned ON.")
    except Exception as e:
        print(f"Error turning on relay {relay_id}: {e}")

def turn_off_relay(relay_id):
    try:
        device_path = get_relay_device_path()
        with serial.Serial(device_path, baudrate=9600, timeout=1) as ser:
            ser.write(RELAY_OFF_COMMANDS[relay_id])
        print(f"Relay {relay_id} turned OFF.")
    except Exception as e:
        print(f"Error turning off relay {relay_id}: {e}")

def get_relay_status(relay_id):
    # If you maintain a dictionary for on/off status, or read from device
    # For now just mock it
    return "unknown"
