# File: services/valve_relay_service.py

import os
import json
import eventlet
import serial
from eventlet import semaphore, event
from services.error_service import set_error, clear_error
from status_namespace import emit_status_update, is_debug_enabled  
from datetime import datetime

# 8-channel ON commands
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

# 8-channel OFF commands
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

# Local reflection of valve states
valve_status = {i: "off" for i in range(1, 9)}

SETTINGS_FILE = os.path.join(os.getcwd(), "data", "settings.json")
DEBUG_SETTINGS_FILE = os.path.join(os.getcwd(), "data", "debug_settings.json")

# Global variables for persistent serial connection and thread management
serial_lock = semaphore.Semaphore()  # to synchronize USB access
valve_ser = None      # persistent serial port; None if not open
polling_thread = None # reference to the polling thread
stop_event_instance = None  # an Event to signal the polling thread to stop

def log_with_timestamp(msg):
    """Logs messages only if debugging is enabled for valve_relay_service."""
    if is_debug_enabled("valve_relay_service"): 
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def get_valve_device_path():
    with open(SETTINGS_FILE, "r") as f:
        settings = json.load(f)
    valve_device = settings.get("usb_roles", {}).get("valve_relay")
    if not valve_device:
        raise RuntimeError("No valve relay device configured in settings.")
    return valve_device

def open_valve_serial():
    """
    Opens the serial port for the valve relay device and returns the Serial object.
    """
    global valve_ser
    device_path = get_valve_device_path()
    valve_ser = serial.Serial(device_path, baudrate=9600, timeout=1)
    clear_error("VALVE_RELAY_OFFLINE")
    log_with_timestamp(f"[Valve] Serial port opened on {device_path}")
    return valve_ser

def close_valve_serial():
    """
    Closes the persistent valve serial port.
    """
    global valve_ser
    if valve_ser:
        try:
            valve_ser.close()
            log_with_timestamp("[Valve] Serial port closed.")
        except Exception as e:
            log_with_timestamp(f"[Valve] Error closing serial port: {e}")
        valve_ser = None

def parse_hardware_response(response):
    """
    Parses the first 8 bytes of the response (ignoring any trailing bytes)
    and updates valve_status accordingly.
    Expected response (example): {0x01}{0x00}{0x00}{0x00}{0x00}{0x00}{0x00}{0x01}{0xFF}
    """
    log_with_timestamp(f"[Valve] parse_hardware_response got raw: {response.hex(' ')}")

    if not response:
        return
    data = response[:8]
    for i in range(1, 9):
        idx = i - 1
        valve_status[i] = "on" if idx < len(data) and data[idx] == 1 else "off"
    
    log_with_timestamp(f"[Valve] Updated valve_status: {valve_status}")

# 1) At the top, import emit_status_update so we can call it:
from status_namespace import emit_status_update

def valve_polling_loop():
    global valve_ser
    log_with_timestamp("[Valve] Polling loop started.")

    # Keep a snapshot of what valve_status was last time
    old_status_snapshot = dict(valve_status)

    while not stop_event_instance.ready():
        with serial_lock:
            try:
                valve_ser.write(b'\xFF')
                eventlet.sleep(0.05)
                response = valve_ser.read(10)
                
                # Keep a copy of the old statuses:
                old_status_snapshot_before = dict(valve_status)
                
                # parse the new response
                parse_hardware_response(response)

                # Compare old vs. new
                something_changed = False
                for i in range(1, 9):
                    if valve_status[i] != old_status_snapshot_before[i]:
                        something_changed = True
                        break

                if something_changed:
                    log_with_timestamp("[Valve] Detected a local valve status change. Emitting status update.")
                    emit_status_update()

            except Exception as e:
                log_with_timestamp(f"[Valve] Polling error: {e}")
                set_error("VALVE_RELAY_OFFLINE")

        eventlet.sleep(1)

    log_with_timestamp("[Valve] Polling loop exiting.")


def init_valve_thread():
    """
    Opens the valve serial port (if not already open) and starts the polling thread.
    Only runs if a device is assigned.
    """
    global valve_ser, polling_thread, stop_event_instance
    try:
        device_path = get_valve_device_path()
    except Exception as e:
        log_with_timestamp(f"[Valve] init_valve_thread: {e}")
        return
    if not device_path:
        log_with_timestamp("[Valve] No valve relay device assigned. Not starting thread.")
        return
    if valve_ser is None:
        open_valve_serial()
    # Create a new Event instance to signal thread stopping
    stop_event_instance = event.Event()
    polling_thread = eventlet.spawn(valve_polling_loop)
    log_with_timestamp("[Valve] Polling thread spawned.")

def stop_valve_thread():
    """
    Signals the polling thread to stop and closes the persistent serial port.
    """
    global polling_thread, stop_event_instance
    if polling_thread:
        log_with_timestamp("[Valve] Stopping polling thread...")
        stop_event_instance.send()  # signal the thread to exit
        eventlet.sleep(1)  # allow it to finish
        polling_thread = None
    close_valve_serial()

def turn_on_valve(valve_id):
    global valve_ser
    if valve_id < 1 or valve_id > 8:
        raise ValueError(f"Invalid valve_id {valve_id}, must be 1..8")
    if valve_ser is None:
        raise RuntimeError("Valve serial port is not open.")

    with serial_lock:
        # 1) Send the ON command
        valve_ser.write(VALVE_ON_COMMANDS[valve_id])
        # 2) Poll the board to see if it really turned on
        valve_ser.write(b'\xFF')
        eventlet.sleep(0.05)
        response = valve_ser.read(10)
        parse_hardware_response(response)

    # 3) parse_hardware_response(...) sets valve_status[i] = "on" if successful
    #    But if the board didn't respond or returned some unexpected data,
    #    parse_hardware_response might leave it as "off" or "unknown".
    #    So we check the final outcome:
    final_state = valve_status.get(valve_id, "unknown")
    log_with_timestamp(f"[Valve] Valve {valve_id} turned {final_state.upper()} (requested ON).")

    # 4) Now let the rest of the system see the new state:
    from status_namespace import emit_status_update
    emit_status_update()


def turn_off_valve(valve_id):
    global valve_ser
    if valve_id < 1 or valve_id > 8:
        raise ValueError(f"Invalid valve_id {valve_id}, must be 1..8")
    if valve_ser is None:
        raise RuntimeError("Valve serial port is not open.")

    with serial_lock:
        valve_ser.write(VALVE_OFF_COMMANDS[valve_id])
        # Poll for actual hardware state
        valve_ser.write(b'\xFF')
        eventlet.sleep(0.05)
        response = valve_ser.read(10)
        parse_hardware_response(response)

    final_state = valve_status.get(valve_id, "unknown")
    log_with_timestamp(f"[Valve] Valve {valve_id} turned {final_state.upper()} (requested OFF).")

    from status_namespace import emit_status_update
    emit_status_update()


def get_valve_status(valve_id):
    return valve_status.get(valve_id, "unknown")
