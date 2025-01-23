import time

# Mock GPIO setup for demonstration
# Replace with actual GPIO library (RPi.GPIO or similar) if working with real hardware
try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
except ImportError:
    print("RPi.GPIO library not available. Using mock GPIO.")

# Define GPIO pin mappings for pumps (change these as needed)
PUMP_GPIO_PINS = {
    "ph_up": 17,   # GPIO pin for pH Up pump
    "ph_down": 27  # GPIO pin for pH Down pump
}

# Initialize GPIO pins for the pumps
def setup_pump_pins():
    try:
        for pin in PUMP_GPIO_PINS.values():
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)  # Set pump OFF initially
    except NameError:
        print("Skipping GPIO setup (mock environment).")

# Run the setup function
setup_pump_pins()

# Function to run a pump for a specified duration
def run_pump(pump, time_sec):
    """
    Runs a pump (ph_up or ph_down) for the specified duration.

    Args:
        pump (str): Either "ph_up" or "ph_down".
        time_sec (int/float): Duration in seconds to run the pump.

    Returns:
        bool: True if the pump was successfully run, False otherwise.
    """
    if pump not in PUMP_GPIO_PINS:
        print(f"Invalid pump: {pump}")
        return False

    pump_pin = PUMP_GPIO_PINS[pump]
    try:
        # Turn on the pump
        print(f"Turning on pump: {pump}")
        GPIO.output(pump_pin, GPIO.HIGH)

        # Run the pump for the specified duration
        time.sleep(time_sec)

        # Turn off the pump
        print(f"Turning off pump: {pump}")
        GPIO.output(pump_pin, GPIO.LOW)
        return True
    except NameError:
        print(f"Simulating pump {pump} for {time_sec} seconds (mock environment).")
        time.sleep(time_sec)
        return True
    except Exception as e:
        print(f"Error running pump: {e}")
        return False
