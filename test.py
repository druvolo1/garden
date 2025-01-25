import serial
import time
import fcntl

# Specify the USB device and baud rate
device = "/dev/serial/by-id/usb-FTDI_FT230X_Basic_UART_DK0IH05U-if00-port0"
baud_rate = 9600

# Acquire a file lock to prevent multiple instances
with open('/tmp/serial_lock', 'w') as lock_file:
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)  # Acquire exclusive lock
    except IOError:
        print("Another instance is already running. Exiting.")
        exit(1)

try:
    print("Attempting to connect to the serial device...")
    # Open the serial connection
    with serial.Serial(
        device,
        baud_rate,
        timeout=1,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE
    ) as ser:
        print(f"Connected to {device} at {baud_rate} baud.")
        print("Flushing serial buffers...")
        ser.flushInput()  # Clear input buffer
        ser.flushOutput()  # Clear output buffer
        print("Listening for data. Press Ctrl+C to stop.")
        
        while True:
            try:
                # Read up to 100 bytes (non-blocking due to timeout)
                raw_data = ser.read(100)
                if raw_data:
                    print(f"Raw bytes received: {raw_data}")
                    try:
                        # Decode the raw data
                        decoded_data = raw_data.decode('utf-8', errors='replace').strip()
                        if decoded_data:
                            print(f"Decoded line: {decoded_data}")
                        else:
                            print("Decoded data is empty.")
                    except Exception as decode_error:
                        print(f"Error decoding data: {decode_error}")
                else:
                    print("Timeout: No data received.")
            except Exception as read_error:
                print(f"Error during reading: {read_error}")
                time.sleep(1)  # Small delay before retrying

except serial.SerialException as serial_error:
    print(f"Serial connection error: {serial_error}")
except KeyboardInterrupt:
    print("Exiting...")
finally:
    print("Script has terminated.")
