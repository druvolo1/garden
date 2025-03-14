import socket
import subprocess
from utils.settings_utils import load_settings

def get_local_ip_address():
    """
    Return this Pi’s primary LAN IP, or '127.0.0.1' on fallback.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except:
        return "127.0.0.1"
    finally:
        s.close()

def resolve_mdns(hostname: str) -> str:
    """
    Tries to resolve a .local hostname via:
      1) avahi-resolve-host-name -4 <hostname>
      2) socket.getaddrinfo()
    Returns the resolved IP string, or None if resolution fails.
    """
    if not hostname:
        return None
    if not hostname.endswith(".local"):
        # Not a .local domain; skip avahi and let socket handle it
        try:
            info = socket.getaddrinfo(hostname, None, socket.AF_INET)
            return info[0][4][0] if info else None
        except:
            return None

    # 1) Try avahi
    try:
        result = subprocess.run(["avahi-resolve-host-name", "-4", hostname],
                                capture_output=True, text=True, check=False)
        if result.returncode == 0:
            ip_address = result.stdout.strip().split()[-1]
            return ip_address
    except:
        pass

    # 2) Fallback to socket
    try:
        info = socket.getaddrinfo(hostname, None, socket.AF_INET)
        return info[0][4][0] if info else None
    except:
        return None

def standardize_host_ip(raw_host_ip: str) -> str:
    """
    If raw_host_ip is empty, or 'localhost', '127.0.0.1', or '<system_name>.local',
    replace with this Pi’s LAN IP. If .local is anything else, try mDNS lookup.
    Otherwise return raw_host_ip unchanged.
    """
    if not raw_host_ip:
        return None

    settings = load_settings()
    system_name = settings.get("system_name", "Garden").lower()
    lower_host = raw_host_ip.lower()

    # If local host or system_name.local, replace with local IP
    if lower_host in ["localhost", "127.0.0.1", f"{system_name}.local"]:
        return get_local_ip_address()

    # If any other .local, resolve via mDNS
    if lower_host.endswith(".local"):
        resolved = resolve_mdns(lower_host)
        if resolved:
            return resolved

    return raw_host_ip
