# File: services/device_config.py

import os
import subprocess

def get_hostname():
    """Retrieve the current hostname."""
    # Example: parse from 'hostnamectl status'
    return subprocess.check_output(["hostnamectl", "status"]).decode().split("Static hostname:")[1].splitlines()[0].strip()

def set_hostname(hostname):
    """Set a new hostname."""
    subprocess.run(["hostnamectl", "set-hostname", hostname], check=True)

def clean_nmcli_field(value):
    """Remove any array-like field identifiers (e.g., IP4.ADDRESS[1])."""
    return value.split(":")[-1].strip()

def get_ip_config(interface):
    """
    Retrieve the IP address, subnet mask, gateway, and DNS server for the specified interface
    using nmcli. Returns a dict with fields:
      {
        "status": "inactive" or "connected",
        "dhcp": bool,
        "ip_address": str,
        "gateway": str,
        "dns1": str or None,
        "dns2": str or None,
        "subnet_mask": "255.255.255.0" # fallback
      }
    """
    try:
        # Check if the interface is active
        active_status = subprocess.run(
            ["nmcli", "-t", "-f", "GENERAL.STATE", "device", "show", interface],
            capture_output=True, text=True
        )
        if "connected" not in active_status.stdout.lower():
            return {"status": "inactive", "dhcp": False, "ip_address": "Not connected"}

        # Check DHCP status
        dhcp_status = subprocess.run(
            ["nmcli", "-t", "-f", "IP4.METHOD", "device", "show", interface],
            capture_output=True, text=True
        )
        dhcp = "auto" in dhcp_status.stdout.lower()

        # Get network details
        ip_output = subprocess.check_output(
            ["nmcli", "-t", "-f", "IP4.ADDRESS,IP4.GATEWAY,IP4.DNS", "device", "show", interface]
        ).decode()

        config = {
            "status": "connected",
            "dhcp": dhcp
        }
        dns_servers = []
        for line in ip_output.splitlines():
            key, value = line.split(":", 1)
            if "IP4.ADDRESS" in key:
                config["ip_address"] = value.strip()
            elif "IP4.GATEWAY" in key:
                config["gateway"] = value.strip()
            elif "IP4.DNS" in key:
                dns_servers.append(value.strip())

        config["dns1"] = dns_servers[0] if len(dns_servers) > 0 else None
        config["dns2"] = dns_servers[1] if len(dns_servers) > 1 else None
        config["subnet_mask"] = "255.255.255.0"  # Placeholder
        return config

    except Exception as e:
        raise RuntimeError(f"Error retrieving configuration for {interface}: {e}")

def set_ip_config(interface, dhcp, ip_address=None, subnet_mask=None, gateway=None, dns1=None, dns2=None):
    """
    Set the IP configuration for a specific interface (e.g., eth0, wlan0).
    If dhcp is True, set nmcli to "auto".
    Otherwise, set manual with the provided IP, gateway, DNS, etc.
    """
    try:
        if dhcp:
            # Configure DHCP
            subprocess.run(
                ["nmcli", "con", "mod", interface, "ipv4.method", "auto"],
                check=True,
            )
        else:
            dns_servers = ",".join(filter(None, [dns1, dns2]))
            # Note: nmcli requires CIDR notation, so we might do 'ip_address/subnet_bits'.
            # If subnet_mask="255.255.255.0", that is /24.
            cidr = mask_to_cidr(subnet_mask or "255.255.255.0")
            address_cidr = f"{ip_address}/{cidr}"
            subprocess.run(
                [
                    "nmcli", "con", "mod", interface,
                    "ipv4.addresses", address_cidr,
                    "ipv4.gateway", gateway,
                    "ipv4.dns", dns_servers,
                    "ipv4.method", "manual"
                ],
                check=True,
            )

        # Bring the interface up with new config
        subprocess.run(["nmcli", "con", "up", interface], check=True)
    except Exception as e:
        raise RuntimeError(f"Failed to set IP configuration for {interface}: {e}")

def mask_to_cidr(netmask):
    """Convert dotted-decimal netmask to CIDR integer."""
    parts = netmask.split('.')
    bits = 0
    for part in parts:
        bits += bin(int(part)).count('1')
    return bits

def get_timezone():
    """Retrieve the current timezone."""
    return subprocess.check_output(["timedatectl", "show", "--value", "--property=Timezone"]).decode().strip()

def set_timezone(timezone):
    """Set the system timezone."""
    valid_timezones = subprocess.check_output(
        ["timedatectl", "list-timezones"]
    ).decode().splitlines()

    if timezone not in valid_timezones:
        raise ValueError(f"Invalid timezone: {timezone}")

    subprocess.run(["timedatectl", "set-timezone", timezone], check=True)

def is_daylight_savings():
    """Check if daylight savings is currently active (based on local time)."""
    # Typically, you'd rely on timezone data for auto-DST. This just checks timedatectl's status.
    return "yes" in subprocess.check_output(["timedatectl", "status"]).decode().lower()

def get_ntp_server():
    """Retrieve the configured NTP server from /etc/ntp.conf (if you use ntp)."""
    ntp_conf_file = "/etc/ntp.conf"
    try:
        with open(ntp_conf_file, "r") as file:
            for line in file:
                if line.startswith("server"):
                    return line.split()[1]
    except FileNotFoundError:
        pass
    return "Not configured"

def set_ntp_server(ntp_server):
    """Set the NTP server."""
    ntp_conf_file = "/etc/ntp.conf"
    with open(ntp_conf_file, "w") as file:
        file.write(f"server {ntp_server} iburst\n")
    subprocess.run(["systemctl", "restart", "ntp"], check=True)

def get_wifi_config():
    """Retrieve the current WiFi SSID from wpa_supplicant.conf."""
    wpa_conf_file = "/etc/wpa_supplicant/wpa_supplicant.conf"
    try:
        with open(wpa_conf_file, "r") as file:
            for line in file:
                if line.strip().startswith("ssid"):
                    return line.split("=")[1].strip().strip('"')
    except FileNotFoundError:
        return None
    return None

def set_wifi_config(ssid, password):
    """Set WiFi SSID and password in /etc/wpa_supplicant/wpa_supplicant.conf."""
    wpa_conf_file = "/etc/wpa_supplicant/wpa_supplicant.conf"
    with open(wpa_conf_file, "w") as file:
        file.write(f"""
network={{
    ssid="{ssid}"
    psk="{password}"
}}
""")
    subprocess.run(["wpa_cli", "-i", "wlan0", "reconfigure"], check=True)

# Additional utility functions if needed...
