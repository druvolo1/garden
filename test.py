import serial
import time
import fcntl

# Specify the USB device and baud rate
device = "/dev/serial/by-id/usb-FTDI_FT230X_Basic_UART_DK0IH05U-if00-port0"
baud_rate = 9600

with open('/tmp/serial_lock', 'w') as lock_file:
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)  # Acquire exclusive lock
        # Proceed with serial communication
    except IOError:
        print("Another instance is already running. Exiting.")
        exit(1)

try:
    print("Attempting to connect to the serial device...")
    # Open the serial connection
    with serial.Serial(device, baud_rate, timeout=1) as ser:  # Reduced timeout to 1 second
        print(f"Connected to {device} at {baud_rate} baud.")
        print("Listening for data. Press Ctrl+C to stop.")
        
        while True:
            try:
                # Read raw bytes from the serial device
                raw_line = ser.readline()

                if raw_line:  # If data was received
                    print(f"Raw bytes received: {raw_line}")
                    try:
                        # Decode the line to UTF-8
                        decoded_line = raw_line.decode('utf-8', errors='replace').strip()
                        print(f"Decoded line: {decoded_line}")
                    except Exception as decode_error:
                        print(f"Error decoding line: {decode_error}")
                else:
                    print("Timeout: No data received.")
            except Exception as read_error:
                print(f"Error during reading: {read_error}")

except serial.SerialException as serial_error:
    print(f"Serial connection error: {serial_error}")
except KeyboardInterrupt:
    print("Exiting...")
