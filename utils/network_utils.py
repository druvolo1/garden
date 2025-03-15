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
      3) socket.gethostbyname()
    Returns the resolved IP string, or None if resolution fails.
    """
    if not hostname:
        return None

    # If it's NOT a .local name, skip avahi and do getaddrinfo() + gethostbyname().
    if not hostname.endswith(".local"):
        ip = fallback_socket_resolve(hostname)
        if ip:
            return ip
        # Now fallback to gethostbyname:
        try:
            return socket.gethostbyname(hostname)
        except:
            return None

    # If it IS a .local, try avahi first:
    try:
        result = subprocess.run(
            ["avahi-resolve-host-name", "-4", hostname],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            # Example stdout: "drain.local\t192.168.1.101"
            ip_address = result.stdout.strip().split()[-1]
            return ip_address
    except:
        pass

    # Then fallback to socket.getaddrinfo():
    ip = fallback_socket_resolve(hostname)
    if ip:
        return ip

    # Finally, fallback to socket.gethostbyname():
    try:
        return socket.gethostbyname(hostname)
    except:
        return None

def fallback_socket_resolve(hostname: str) -> str:
    """
    A helper that tries socket.getaddrinfo() for an IPv4 address.
    """
    try:
        info = socket.getaddrinfo(hostname, None, socket.AF_INET)
        if info:
            return info[0][4][0]  # IP is in [4][0]
    except:
        pass
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

    # If not .local, or resolution failed, just return as-is
    return raw_host_ip
