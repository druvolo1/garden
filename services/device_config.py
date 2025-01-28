import os
import subprocess

def get_hostname():
    """Retrieve the current hostname."""
    return subprocess.check_output(["hostnamectl", "status"]).decode().split("Static hostname:")[1].splitlines()[0].strip()

def set_hostname(hostname):
    """Set a new hostname."""
    subprocess.run(["hostnamectl", "set-hostname", hostname], check=True)

def get_ip_config(interface="wlan0"):
    """
    Retrieve the IP configuration for the specified interface.
    """
    try:
        # Check if DHCP is enabled
        dhcp_method = subprocess.check_output(
            ["nmcli", "-t", "-f", "IP4.METHOD", "device", "show", interface]
        ).decode().strip()
        dhcp_enabled = dhcp_method == "auto"

        # Extract IPv4 address
        ip_output = subprocess.check_output(
            ["nmcli", "-t", "-f", "IP4.ADDRESS", "device", "show", interface]
        ).decode().strip()
        ip_address = ip_output.split("/")[0] if ip_output else "Not available"

        # Extract gateway
        gateway_output = subprocess.check_output(
            ["nmcli", "-t", "-f", "IP4.GATEWAY", "device", "show", interface]
        ).decode().strip()
        gateway = gateway_output if gateway_output else "Not available"

        # Extract DNS servers
        dns_output = subprocess.check_output(
            ["nmcli", "-t", "-f", "IP4.DNS", "device", "show", interface]
        ).decode().strip()
        dns_server = dns_output if dns_output else "Not available"

        # Set a default subnet mask if not explicitly provided
        subnet_mask = "255.255.255.0"  # Modify if dynamic subnet mask extraction is required

        return {
            "dhcp": dhcp_enabled,
            "ip_address": ip_address,
            "subnet_mask": subnet_mask,
            "gateway": gateway,
            "dns_server": dns_server
        }
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error retrieving IP configuration for {interface}: {str(e)}")

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

