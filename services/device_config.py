import os
import subprocess

def get_hostname():
    """Retrieve the current hostname."""
    return subprocess.check_output(["hostnamectl", "status"]).decode().split("Static hostname:")[1].splitlines()[0].strip()

def set_hostname(hostname):
    """Set a new hostname."""
    subprocess.run(["hostnamectl", "set-hostname", hostname], check=True)

def get_ip_config():
    """
    Retrieve the IP address, subnet mask, gateway, DNS server, and whether DHCP is enabled.
    """
    try:
        # Check if DHCP is enabled by inspecting the network configuration file
        dhcp_enabled = False
        with open("/etc/network/interfaces", "r") as f:
            config = f.read()
            if "dhcp" in config:
                dhcp_enabled = True

        # Retrieve IP configuration
        ip_output = subprocess.check_output(["ip", "addr", "show", "dev", "eth0"]).decode()
        gateway_output = subprocess.check_output(["ip", "route", "show", "default"]).decode()
        dns_output = read_resolv_conf()

        ip_address = extract_ip_address(ip_output)
        subnet_mask = extract_subnet_mask(ip_output)  # Calculate dynamically
        gateway = gateway_output.split()[2]
        dns_server = dns_output

        return {
            "dhcp": dhcp_enabled,
            "ip_address": ip_address,
            "subnet_mask": subnet_mask,
            "gateway": gateway,
            "dns_server": dns_server
        }
    except Exception as e:
        raise RuntimeError(f"Error retrieving IP configuration: {e}")

def set_ip_config(ip_address=None, subnet_mask=None, gateway=None, dns_server=None, dhcp=True):
    """
    Set the IP configuration (DHCP or Static).
    If `dhcp` is True, enable DHCP. Otherwise, set static IP configuration.
    """
    try:
        config_path = "/etc/network/interfaces"
        with open(config_path, "w") as f:
            # If DHCP is enabled
            if dhcp:
                f.write(
                    """
                    auto eth0
                    iface eth0 inet dhcp
                    """
                )
                print("Configured eth0 for DHCP.")
            else:
                # Static configuration
                f.write(
                    f"""
                    auto eth0
                    iface eth0 inet static
                    address {ip_address}
                    netmask {subnet_mask}
                    gateway {gateway}
                    """
                )
                print("Configured eth0 for Static IP.")

        # Update DNS configuration
        with open("/etc/resolv.conf", "w") as resolv_file:
            resolv_file.write(f"nameserver {dns_server}\n")

        # Apply the network changes
        subprocess.run(["systemctl", "restart", "networking"], check=True)
    except Exception as e:
        raise RuntimeError(f"Error setting IP configuration: {e}")

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
    """Extract the IP address from the ip command output."""
    for line in ip_output.splitlines():
        if "inet " in line:
            return line.split()[1].split("/")[0]
    return "Not found"

def extract_subnet_mask(ip_output):
    """Extract the subnet mask from the ip command output."""
    for line in ip_output.splitlines():
        if "inet " in line:
            cidr = line.split()[1].split("/")[1]  # CIDR notation
            return cidr_to_subnet_mask(int(cidr))
    return "255.255.255.0"  # Default

def cidr_to_subnet_mask(cidr):
    """Convert CIDR notation to a subnet mask."""
    mask = (0xFFFFFFFF >> (32 - cidr)) << (32 - cidr)
    return ".".join(str((mask >> (i * 8)) & 0xFF) for i in range(4)[::-1])

def read_resolv_conf():
    """Read DNS server from /etc/resolv.conf."""
    with open("/etc/resolv.conf", "r") as file:
        for line in file:
            if line.startswith("nameserver"):
                return line.split()[1]
    return "Not found"
