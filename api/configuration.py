from app import app
from flask import jsonify, request
from services.device_config import (
    get_hostname, set_hostname, get_ip_config, set_ip_config, get_timezone, set_timezone,
    is_daylight_savings, get_ntp_server, set_ntp_server, get_wifi_config, set_wifi_config
)

@app.route('/api/device/config', methods=['GET', 'POST'])
def device_config():
    """
    API endpoint to get or set device configuration.
    """
    if request.method == 'GET':
        try:
            # Fetch configuration for Ethernet (eth0)
            eth0_config = get_ip_config(interface="eth0")

            # Fetch configuration for Wi-Fi (wlan0)
            wlan0_config = get_ip_config(interface="wlan0")
            wlan0_config["ssid"] = get_wifi_config()

            # Construct the response
            config = {
                "hostname": get_hostname(),
                "eth0": eth0_config,
                "wlan0": wlan0_config,
                "timezone": get_timezone(),
                "daylight_savings": is_daylight_savings(),
                "ntp_server": get_ntp_server()
            }

            return jsonify({"status": "success", "config": config}), 200
        except Exception as e:
            return jsonify({"status": "failure", "message": str(e)}), 500

    elif request.method == 'POST':
        try:
            # Get the updated configuration from the request
            data = request.get_json()

            # Update hostname
            set_hostname(data.get("hostname"))

            # Update network configuration
            set_ip_config(
                ip_address=data.get("ip_address"),
                subnet_mask=data.get("subnet_mask"),
                gateway=data.get("gateway"),
                dns_server=data.get("dns_server")
            )

            # Update timezone and daylight savings
            set_timezone(data.get("timezone"))
            set_ntp_server(data.get("ntp_server"))

            # Update WiFi configuration only if SSID or password is provided
            if data.get("wifi_ssid"):
                wifi_password = data.get("wifi_password")
                if wifi_password:
                    set_wifi_config(data.get("wifi_ssid"), wifi_password)
                else:
                    set_wifi_config(data.get("wifi_ssid"), None)

            return jsonify({"status": "success", "message": "Configuration applied successfully."}), 200
        except Exception as e:
            return jsonify({"status": "failure", "message": str(e)}), 500
