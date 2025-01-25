import serial

def listen_for_ph_readings():
    """
    Continuously listen for pH values from the sensor and emit them via WebSocket.
    """
    settings = load_settings()
    ph_device = settings.get("usb_roles", {}).get("ph_probe")

    if not ph_device:
        print("No pH probe device assigned. Listening loop will not start.")
        return  # Exit the function if no pH device is assigned

    try:
        print(f"Starting to listen for pH readings on: {ph_device}")
        with serial.Serial(ph_device, 9600, timeout=1) as ser:
            while True:
                print("Waiting for data from the pH probe...")  # Debug statement for every loop
                line = ser.readline().decode('utf-8').strip()  # Read a line and decode it
                if line:
                    try:
                        ph_value = float(line)  # Convert to float
                        print(f"Received pH value: {ph_value}")  # Log the received value
                        socketio.emit('ph_update', {'ph': ph_value}, broadcast=True)
                    except ValueError:
                        print(f"Invalid data received from pH probe: {line}")
                else:
                    print("No data received from pH probe.")
                time.sleep(3)  # Wait for 3 seconds before the next loop
    except serial.SerialException as e:
        print(f"Error accessing pH probe device {ph_device}: {e}")

