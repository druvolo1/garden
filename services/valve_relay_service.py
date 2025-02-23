# File: services/valve_relay_service.py

import os
import json
import eventlet
import serial
from eventlet.queue import Queue
from eventlet import semaphore, event
from services.error_service import set_error, clear_error

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

# Singleton objects to manage the relay thread
serial_lock = semaphore.Semaphore()  # ensures only one read/write at a time
command_queue = Queue()
stop_event = event.Event()  # we'll replace this when starting a new thread
valve_thread_spawned = False  # track if we started the thread

def get_valve_device_path():
    with open(SETTINGS_FILE, "r") as f:
        settings = json.load(f)
    valve_device = settings.get("usb_roles", {}).get("valve_relay")
    if not valve_device:
        raise RuntimeError("No valve relay device configured in settings.")
    return valve_device

def valve_main_loop():
    """
    Runs in a dedicated Eventlet thread:
      1) Open serial port once.
      2) Process any on/off commands from command_queue.
      3) Once per second, send 0xFF to read the hardware status & parse it.
    """
    try:
        device_path = get_valve_device_path()
    except Exception as e:
        print(f"[Valve] Could not open valve device path: {e}")
        set_error("VALVE_RELAY_OFFLINE")
        return

    print(f"[Valve] Starting main loop with device: {device_path}")
    try:
        with serial_lock:
            ser = serial.Serial(device_path, baudrate=9600, timeout=1)

        clear_error("VALVE_RELAY_OFFLINE")

        while not stop_event.ready():
            # 1) Process any queued commands
            while not command_queue.empty():
                cmd = command_queue.get()
                with serial_lock:
                    ser.write(cmd)
                eventlet.sleep(0.01)  # small gap

            # 2) Send 0xFF to query the hardware states
            with serial_lock:
                ser.write(b'\xFF')
                eventlet.sleep(0.05)
                response = ser.read(10)  # read up to 10 bytes

            parse_hardware_response(response)
            eventlet.sleep(1)

    except Exception as e:
        print(f"[Valve] Error in main loop: {e}")
        set_error("VALVE_RELAY_OFFLINE")
    finally:
        with serial_lock:
            try:
                ser.close()
            except:
                pass
        print("[Valve] Exiting valve_main_loop()")

def parse_hardware_response(response):
    """
    Example response: {0x01}{0x00}{0x00}{0x00}{0x00}{0x00}{0x00}{0x01}{0xFF}
    Meaning relay 1 & 8 are on, others off.
    """
    if not response:
        return
    data = response[:8]
    for i in range(1, 9):
        idx = i - 1
        if idx < len(data):
            valve_status[i] = "on" if data[idx] == 1 else "off"

def init_valve_thread():
    """
    Spawns the valve thread if a valve relay device is assigned.
    """
    from utils.settings_utils import load_settings
    global valve_thread_spawned, stop_event
    try:
        device_path = get_valve_device_path()
    except Exception as e:
        print(f"[Valve] init_valve_thread: {e}")
        return

    if not device_path:
        print("[Valve] No valve relay device assigned. Not starting thread.")
        return
    if valve_thread_spawned:
        print("[Valve] Valve thread already running.")
        return
    # Instead of reset(), create a new Event instance
    stop_event = event.Event()
    valve_thread_spawned = True
    eventlet.spawn(valve_main_loop)
    print("[Valve] Valve thread spawned.")

def stop_valve_thread():
    """
    Signals the valve thread to stop.
    """
    global valve_thread_spawned
    if valve_thread_spawned:
        print("[Valve] Stopping valve thread...")
        stop_event.send()
        eventlet.sleep(1)
        valve_thread_spawned = False

def reinitialize_valve_relay_service():
    """
    Stops the old thread, clears command queue, enqueues commands to turn all valves OFF,
    and starts a new thread if a device is assigned.
    """
    global valve_thread_spawned, stop_event
    print("[Valve] reinitialize_valve_relay_service called.")
    try:
        stop_valve_thread()
        while not command_queue.empty():
            command_queue.get()
        for i in range(1, 9):
            command_queue.put(VALVE_OFF_COMMANDS[i])
        valve_thread_spawned = False
        init_valve_thread()
        print("Valve Relay service reinitialized successfully.")
        clear_error("VALVE_RELAY_OFFLINE")
    except Exception as e:
        print(f"Error reinitializing valve relay service: {e}")
        set_error("VALVE_RELAY_OFFLINE")

def turn_on_valve(valve_id):
    if valve_id < 1 or valve_id > 8:
        raise ValueError(f"Invalid valve_id {valve_id}, must be 1..8")
    command_queue.put(VALVE_ON_COMMANDS[valve_id])
    valve_status[valve_id] = "on"

def turn_off_valve(valve_id):
    if valve_id < 1 or valve_id > 8:
        raise ValueError(f"Invalid valve_id {valve_id}, must be 1..8")
    command_queue.put(VALVE_OFF_COMMANDS[valve_id])
    valve_status[valve_id] = "off"

def get_valve_status(valve_id):
    return valve_status.get(valve_id, "unknown")
