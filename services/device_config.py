import subprocess

def get_hostname():
    """Retrieve the current hostname."""
    return subprocess.check_output(["hostnamectl", "status"]).decode().split("Static hostname:")[1].splitlines()[0].strip()

def set_hostname(hostname):
    """Set a new hostname."""
    subprocess.run(["hostnamectl", "set-hostname", hostname], check=True)

def get_ip_config():
    """Retrieve the IP address, subnet mask, gateway, and DNS server."""
    ip_output = subprocess.check_output(["ip", "addr", "show", "dev", "eth0"]).decode()
    gateway_output = subprocess.check_output(["ip", "route", "show", "default"]).decode()
    dns_output = read_resolv_conf()

    ip_address = extract_ip_address(ip_output)
    subnet_mask = "255.255.255.0"  # Simplified for now; could be calculated dynamically
    gateway = gateway_output.split()[2]
    dns_server = dns_output

    return ip_address, subnet_mask, gateway, dns_server

def set_ip_config(ip_address, subnet_mask, gateway, dns_server):
    """Set a static IP configuration."""
    interface_file = "/etc/network/interfaces"  # Adjust for your OS
    with open(interface_file, "w") as file:
        file.write(f"""
auto eth0
iface eth0 inet static
    address {ip_address}
    netmask {subnet_mask}
    gateway {gateway}
    dns-nameservers {dns_server}
""")
    subprocess.run(["systemctl", "restart", "networking"], check=True)

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

def read_resolv_conf():
    """Read DNS server from /etc/resolv.conf."""
    with open("/etc/resolv.conf", "r") as file:
        for line in file:
            if line.startswith("nameserver"):
                return line.split()[1]
    return "Not found"
