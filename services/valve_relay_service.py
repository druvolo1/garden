# File: services/valve_relay_service.py

import serial
import json
import os
from services.error_service import set_error, clear_error

# 8-channel ON commands:
#  A0 01 01 A2  -> Relay #1 ON
#  A0 02 01 A3  -> Relay #2 ON
#  A0 03 01 A4  -> Relay #3 ON
#  A0 04 01 A5  -> Relay #4 ON
#  A0 05 01 A6  -> Relay #5 ON
#  A0 06 01 A7  -> Relay #6 ON
#  A0 07 01 A8  -> Relay #7 ON
#  A0 08 01 A9  -> Relay #8 ON

VALVE_ON_COMMANDS = {
    1: b'\xA0\x01\x01\xA2',
    2: b'\xA0\x02\x01\xA3',
    3: b'\xA0\x03\x01\xA4',
    4: b'\xA0\x04\x01\xA5',
    5: b'\xA0\x05\x01\xA6',
    6: b'\xA0\x06\x01\xA7',
    7: b'\xA0\x07\x01\xA8',
    8: b'\xA0\x08\x01\xA9'
}

# 8-channel OFF commands:
#  A0 01 00 A1  -> Relay #1 OFF
#  A0 02 00 A2  -> Relay #2 OFF
#  A0 03 00 A3  -> Relay #3 OFF
#  A0 04 00 A4  -> Relay #4 OFF
#  A0 05 00 A5  -> Relay #5 OFF
#  A0 06 00 A6  -> Relay #6 OFF
#  A0 07 00 A7  -> Relay #7 OFF
#  A0 08 00 A8  -> Relay #8 OFF

VALVE_OFF_COMMANDS = {
    1: b'\xA0\x01\x00\xA1',
    2: b'\xA0\x02\x00\xA2',
    3: b'\xA0\x03\x00\xA3',
    4: b'\xA0\x04\x00\xA4',
    5: b'\xA0\x05\x00\xA5',
    6: b'\xA0\x06\x00\xA6',
    7: b'\xA0\x07\x00\xA7',
    8: b'\xA0\x08\x00\xA8'
}

# Keeps track of on/off status for each relay
valve_status = {
    1: "off",
    2: "off",
    3: "off",
    4: "off",
    5: "off",
    6: "off",
    7: "off",
    8: "off"
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
    """
    Reinitialize (open/close) the valve relay device.
    """
    try:
        device_path = get_valve_device_path()
        with serial.Serial(device_path, baudrate=9600, timeout=1) as ser:
            # Example: turn off all 8 valves as a quick test
            for i in range(1, 9):
                ser.write(VALVE_OFF_COMMANDS[i])
        print("Valve Relay service reinitialized successfully.")
        clear_error("VALVE_RELAY_OFFLINE")
    except Exception as e:
        print(f"Error reinitializing valve relay service: {e}")
        set_error("VALVE_RELAY_OFFLINE")

def turn_on_valve(valve_id):
    """
    Turns on the given channel (1-8) of the valve relay.
    """
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
    """
    Turns off the given channel (1-8) of the valve relay.
    """
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
    """
    Returns the current 'on'/'off' status from our local dictionary.
    Note: If you want actual hardware status, you can send 0xFF (0xFF in hex)
    to query the relay, then parse the returned bytes.
    """
    return valve_status.get(valve_id, "unknown")
