import serial

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

# Serial Port Configuration
SERIAL_PORT = "/dev/ttyUSB1"  # Adjust this to your relay's actual USB port
BAUD_RATE = 9600


def turn_on_relay(relay):
    """
    Turn on the specified relay (1 or 2).

    Args:
        relay (int): The relay number (1 or 2).
    Returns:
        bool: True if successful, False otherwise.
    """
    if relay not in RELAY_ON_COMMANDS:
        print(f"Invalid relay: {relay}")
        return False

    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
            ser.write(RELAY_ON_COMMANDS[relay])
        relay_status[relay] = "on"
        print(f"Relay {relay} turned ON.")
        return True
    except Exception as e:
        print(f"Error turning on relay {relay}: {e}")
        return False


def turn_off_relay(relay):
    """
    Turn off the specified relay (1 or 2).

    Args:
        relay (int): The relay number (1 or 2).
    Returns:
        bool: True if successful, False otherwise.
    """
    if relay not in RELAY_OFF_COMMANDS:
        print(f"Invalid relay: {relay}")
        return False

    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
            ser.write(RELAY_OFF_COMMANDS[relay])
        relay_status[relay] = "off"
        print(f"Relay {relay} turned OFF.")
        return True
    except Exception as e:
        print(f"Error turning off relay {relay}: {e}")
        return False


def get_relay_status():
    """
    Get the current status of all relays.

    Returns:
        dict: A dictionary with the status of relays (1 and 2).
    """
    return relay_status
