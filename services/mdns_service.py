import socket
from zeroconf import Zeroconf, ServiceInfo

_zeroconf = None

# We'll keep the old references for appended host (like "Garden-pc")
_service_info = None

# We'll also have a second global for the pure system name
_service_info_pure = None


def _get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't actually send packets to 8.8.8.8, just uses it to pick the best local interface
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def register_mdns_name(system_name: str, service_port=8000):
    """
    Register an mDNS service under <system_name>._garden._tcp.local.,
    typically used after appending "-pc" for the OS hostname.
    If a previous one was registered, it’s unregistered first.
    """
    global _zeroconf, _service_info

    # Unregister old if needed
    if _service_info and _zeroconf:
        try:
            _zeroconf.unregister_service(_service_info)
        except Exception:
            pass
        _service_info = None

    if not _zeroconf:
        _zeroconf = Zeroconf()

    local_ip = _get_local_ip()
    service_type = "_garden._tcp.local."
    # This might be something like "Zone4-pc._garden._tcp.local."
    service_name = f"{system_name}.{service_type}"
    address_bytes = socket.inet_aton(local_ip)

    _service_info = ServiceInfo(
        type_=service_type,
        name=service_name,
        addresses=[address_bytes],
        port=service_port,
        server=f"{system_name}.local.",  # Avahi host field
        properties={},
    )

    _zeroconf.register_service(_service_info)
    print(f"[mDNS] Registered appended name '{service_name}' => {local_ip}:{service_port}")


def register_mdns_pure_system_name(system_name: str, service_port=8000):
    """
    Register a second mDNS service exactly matching the user's system_name,
    ignoring the OS-level '-pc' suffix. E.g. "Zone4._garden._tcp.local." -> "Zone4.local."
    So end-users can resolve <system_name>.local directly, regardless of the OS hostname.
    """
    global _zeroconf, _service_info_pure

    # Unregister old if needed
    if _service_info_pure and _zeroconf:
        try:
            _zeroconf.unregister_service(_service_info_pure)
        except Exception:
            pass
        _service_info_pure = None

    if not _zeroconf:
        _zeroconf = Zeroconf()

    local_ip = _get_local_ip()
    service_type = "_garden._tcp.local."
    # This might be "Zone4._garden._tcp.local."
    service_name = f"{system_name}.{service_type}"
    address_bytes = socket.inet_aton(local_ip)

    _service_info_pure = ServiceInfo(
        type_=service_type,
        name=service_name,
        addresses=[address_bytes],
        port=service_port,
        server=f"{system_name}.local.",  # Specifically the user’s system_name
        properties={},
    )

    _zeroconf.register_service(_service_info_pure)
    print(f"[mDNS] Registered pure system name '{service_name}' => {local_ip}:{service_port}")


def close_mdns():
    """
    Unregister everything and shut down Zeroconf.
    """
    global _zeroconf, _service_info, _service_info_pure

    # 1) The appended (like "Zone4-pc") entry
    if _service_info and _zeroconf:
        try:
            _zeroconf.unregister_service(_service_info)
        except Exception:
            pass
        _service_info = None

    # 2) The "pure" system name (like "Zone4")
    if _service_info_pure and _zeroconf:
        try:
            _zeroconf.unregister_service(_service_info_pure)
        except Exception:
            pass
        _service_info_pure = None

    if _zeroconf:
        _zeroconf.close()
        _zeroconf = None

    print("[mDNS] Closed Zeroconf.")
