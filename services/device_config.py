import os
import subprocess

def get_hostname():
    """Retrieve the current hostname."""
    return subprocess.check_output(["hostnamectl", "status"]).decode().split("Static hostname:")[1].splitlines()[0].strip()

def set_hostname(hostname):
    """Set a new hostname."""
    subprocess.run(["hostnamectl", "set-hostname", hostname], check=True)

def clean_nmcli_field(value):
    """Remove any array-like field identifiers (e.g., IP4.ADDRESS[1])."""
    return value.split(":")[-1].strip()

def get_ip_config(interface):
    """
    Retrieve the IP address, subnet mask, gateway, and DNS server for the specified interface.
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

        # Parse the output
        config = {"dhcp": dhcp}
        for line in ip_output.splitlines():
            key, value = line.split(":", 1)
            if "IP4.ADDRESS" in key:
                config["ip_address"] = value.strip()
            elif "IP4.GATEWAY" in key:
                config["gateway"] = value.strip()
            elif "IP4.DNS" in key:
                config["dns_server"] = config.get("dns_server", "") + value.strip() + "\n"

        # Remove trailing newlines in DNS server
        config["dns_server"] = config["dns_server"].strip()

        # Add a default subnet mask if none is provided
        config["subnet_mask"] = "255.255.255.0"  # Placeholder; customize if necessary

        return config
    except Exception as e:
        raise RuntimeError(f"Error retrieving configuration for {interface}: {e}")

def set_ip_config(interface, dhcp, ip_address=None, subnet_mask=None, gateway=None, dns_server=None):
    """
    Set the IP configuration for a specific interface (e.g., eth0, wlan0).
    """
    interface_file = f"/etc/network/interfaces.d/{interface}"
    try:
        with open(interface_file, "w") as file:
            if dhcp:
                # Configure DHCP
                file.write(f"""
auto {interface}
iface {interface} inet dhcp
""")
            else:
                # Configure Static IP
                file.write(f"""
auto {interface}
iface {interface} inet static
    address {ip_address}
    netmask {subnet_mask}
    gateway {gateway}
    dns-nameservers {dns_server}
""")
        subprocess.run(["systemctl", "restart", "networking"], check=True)
    except Exception as e:
        raise RuntimeError(f"Failed to set IP configuration for {interface}: {e}")


def get_timezone():
    """Retrieve the current timezone."""
    return subprocess.check_output(["timedatectl", "show", "--value", "--property=Timezone"]).decode().strip()

def set_timezone(timezone):
    """Set the system timezone."""
    subprocess.run(["timedatectl", "set-timezone", timezone], check=True)

def is_daylight_savings():
    """Check if daylight savings is enabled."""
    return "yes" in subprocess.check_output(["timedatectl", "status"]).decode().lower()

def get_ntp_server():
    """Retrieve the configured NTP server."""
    try:
        with open("/etc/ntp.conf", "r") as file:
            for line in file:
                if line.startswith("server"):
                    return line.split()[1]
    except FileNotFoundError:
        return "Not configured"

def set_ntp_server(ntp_server):
    """Set the NTP server."""
    ntp_conf_file = "/etc/ntp.conf"
    with open(ntp_conf_file, "w") as file:
        file.write(f"server {ntp_server} iburst\n")
    subprocess.run(["systemctl", "restart", "ntp"], check=True)

def get_wifi_config():
    """Retrieve the current WiFi SSID."""
    wpa_conf_file = "/etc/wpa_supplicant/wpa_supplicant.conf"
    try:
        with open(wpa_conf_file, "r") as file:
            for line in file:
                if line.strip().startswith("ssid"):
                    return line.split("=")[1].strip().strip('"')
    except FileNotFoundError:
        return "Not configured"

def set_wifi_config(ssid, password):
    """Set WiFi SSID and password."""
    wpa_conf_file = "/etc/wpa_supplicant/wpa_supplicant.conf"
    with open(wpa_conf_file, "w") as file:
        file.write(f"""
network={{
    ssid="{ssid}"
    psk="{password}"
}}
""")
    subprocess.run(["wpa_cli", "-i", "wlan0", "reconfigure"], check=True)

# Utility functions
def extract_ip_address(ip_output):
    """Extract the IP address from the `ip` command output."""
    for line in ip_output.splitlines():
        if "inet " in line:
            return line.split()[1].split("/")[0]
    return None

def extract_subnet_mask(ip_output):
    """Extract the subnet mask from the `ip` command output."""
    for line in ip_output.splitlines():
        if "inet " in line:
            cidr = int(line.split()[1].split("/")[1])
            return convert_cidr_to_netmask(cidr)
    return None

def convert_cidr_to_netmask(cidr):
    """Convert CIDR notation to a subnet mask."""
    mask = (0xffffffff >> (32 - cidr)) << (32 - cidr)
    return ".".join(map(str, [(mask >> i) & 0xff for i in [24, 16, 8, 0]]))

def read_resolv_conf():
    """Read DNS server addresses from `/etc/resolv.conf`."""
    dns_servers = []
    try:
        with open("/etc/resolv.conf", "r") as file:
            for line in file:
                if line.startswith("nameserver"):
                    dns_servers.append(line.split()[1])
    except FileNotFoundError:
        pass
    return dns_servers

