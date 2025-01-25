import serial

# Specify the USB device and baud rate
device = "/dev/serial/by-id/usb-FTDI_FT230X_Basic_UART_DK0IH05U-if00-port0"
baud_rate = 9600

try:
    # Open the serial connection
    with serial.Serial(device, baud_rate, timeout=1) as ser:
        print(f"Connected to {device} at {baud_rate} baud.")
        print("Listening for data. Press Ctrl+C to stop.")
        
        while True:
            # Read a line from the serial device
            line = ser.readline().decode('utf-8', errors='replace').strip()
            if line:
                print(f"Received: {line}")

except serial.SerialException as e:
    print(f"Error accessing the serial device: {e}")
except KeyboardInterrupt:
    print("Exiting...")
