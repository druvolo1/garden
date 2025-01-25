import serial
import time

# Specify the USB device and baud rate
device = "/dev/serial/by-id/usb-FTDI_FT230X_Basic_UART_DK0IH05U-if00-port0"
baud_rate = 9600

try:
    print("Attempting to connect to the serial device...")
    # Open the serial connection
    with serial.Serial(device, baud_rate, timeout=5) as ser:
        print(f"Connected to {device} at {baud_rate} baud.")
        print("Listening for data. Press Ctrl+C to stop.")
        
        # Keep the port open and continuously listen for data
        while True:
            try:
                # Read raw bytes from the serial device
                raw_line = ser.readline()

                # Debug: Log raw bytes
                print(f"Raw bytes received: {raw_line}")

                if raw_line:  # If data was received
                    try:
                        # Decode the line to UTF-8
                        decoded_line = raw_line.decode('utf-8', errors='replace').strip()
                        print(f"Decoded line: {decoded_line}")

                        # Check if the decoded line contains valid data
                        if decoded_line:
                            print(f"Valid data: {decoded_line}")
                        else:
                            print("Decoded line is empty.")
                    except Exception as decode_error:
                        print(f"Error decoding line: {decode_error}")
                else:
                    print("No data received in this iteration.")
            except Exception as read_error:
                print(f"Error during reading: {read_error}")
                # Optionally add a delay before retrying
                time.sleep(1)

except serial.SerialException as serial_error:
    print(f"Serial connection error: {serial_error}")
except KeyboardInterrupt:
    print("Exiting...")
