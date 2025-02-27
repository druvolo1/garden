#!/usr/bin/env python3
import RPi.GPIO as GPIO
import time

def pin_callback(channel):
    state = GPIO.input(channel)
    print(f"[DEBUG] GPIO {channel} changed to {'HIGH' if state else 'LOW'}")

def main():
    GPIO.setmode(GPIO.BCM)
    # Try monitoring a range of pins (2..27 covers most usable GPIOs on Pi)
    for pin in range(2, 28):
        try:
            # Use no internal pull in this example (PUD_OFF),
            # or PUD_UP / PUD_DOWN if you know your circuit
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_OFF)
            GPIO.add_event_detect(pin, GPIO.BOTH, callback=pin_callback, bouncetime=50)
        except Exception as e:
            print(f"[INFO] Pin {pin} not available or not set up properly: {e}")
    
    print("[INFO] Monitoring all pins from 2 to 27. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
        print("[INFO] Exiting.")

if __name__ == "__main__":
    main()
