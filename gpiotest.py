#!/usr/bin/env python3

import RPi.GPIO as GPIO
import time

# List the GPIO pins you want to monitor. 
# These are BCM pin numbers. Adjust to your needs.
PINS_TO_MONITOR = [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30]

def pin_callback(channel):
    """
    This callback function is triggered every time one of the monitored pins
    changes state (either going from LOW to HIGH or from HIGH to LOW).
    """
    state = GPIO.input(channel)
    print(f"[DEBUG] GPIO {channel} changed to {'HIGH' if state else 'LOW'}")

def main():
    # Use Broadcom pin-numbering scheme
    GPIO.setmode(GPIO.BCM)

    # Set up each pin in PINS_TO_MONITOR as an input with a pull-down resistor
    for pin in PINS_TO_MONITOR:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        # Detect both rising and falling edges
        GPIO.add_event_detect(pin, GPIO.BOTH, callback=pin_callback, bouncetime=50)

    print("[INFO] Monitoring pins:", PINS_TO_MONITOR)
    print("[INFO] Press Ctrl+C to exit.")

    try:
        # Keep the script running; callbacks will be triggered in the background
        while True:
            time.sleep(1)  # You can do other tasks here
    except KeyboardInterrupt:
        print("\n[INFO] Exiting script...")
    finally:
        # Clean up GPIO settings before exiting
        GPIO.cleanup()
        print("[INFO] GPIO cleanup completed. Goodbye!")

if __name__ == "__main__":
    main()
