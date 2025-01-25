import serial

def test_serial_reading():
    ph_device = "/dev/serial/by-id/usb-FTDI_FT230X_Basic_UART_DK0IH05U-if00-port0"  # Replace with the device path
    try:
        with serial.Serial(ph_device, 9600, timeout=1) as ser:
            while True:
                line = ser.readline().decode('utf-8').strip()
                if line:
                    print(f"Received pH value: {line}")
    except Exception as e:
        print(f"Error accessing pH probe device: {e}")

if __name__ == "__main__":
    test_serial_reading()
