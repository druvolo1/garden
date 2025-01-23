try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)  # Disable warnings about pins already in use
except ImportError:
    print("RPi.GPIO not available. Using mock environment.")

# Define GPIO pins for water level sensors
WATER_LEVEL_GPIO_PINS = {
    "reservoir_empty": 22,  # Pin for "Reservoir Empty" sensor
    "reservoir_full": 23    # Pin for "Reservoir Full" sensor
}

# Initialize GPIO pins
def setup_water_level_pins():
    try:
        for pin in WATER_LEVEL_GPIO_PINS.values():
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # Set as input with pull-up resistor
    except NameError:
        print("Skipping GPIO setup (mock environment).")

# Run setup on import
setup_water_level_pins()

# Function to get the status of water level sensors
def get_water_level_status():
    """
    Get the current status of water level sensors.

    Returns:
        dict: A dictionary with the status of the "reservoir_empty" and "reservoir_full" sensors.
    """
    try:
        status = {
            "reservoir_empty": not GPIO.input(WATER_LEVEL_GPIO_PINS["reservoir_empty"]),  # True = sensor triggered
            "reservoir_full": not GPIO.input(WATER_LEVEL_GPIO_PINS["reservoir_full"])    # True = sensor triggered
        }
    except NameError:
        # Mock status for testing in non-Pi environments
        status = {
            "reservoir_empty": False,
            "reservoir_full": True
        }
    return status
