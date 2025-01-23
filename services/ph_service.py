import serial

def get_ph_reading():
    """Read the pH value from the sensor."""
    with serial.Serial('/dev/ttyUSB0', 9600, timeout=1) as ser:
        ser.write(b'R\r')
        response = ser.readline().decode().strip()
        return float(response)

def calibrate_ph(level):
    """Calibrate the pH sensor at the specified level (low/mid/high)."""
    valid_levels = ['low', 'mid', 'high']
    if level not in valid_levels:
        return False
    command = {'low': 'Cal,low', 'mid': 'Cal,mid', 'high': 'Cal,high'}[level]
    with serial.Serial('/dev/ttyUSB0', 9600, timeout=1) as ser:
        ser.write((command + '\r').encode())
    return True
