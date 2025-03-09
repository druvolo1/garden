import socket
from zeroconf import Zeroconf, ServiceInfo

_zeroconf = None

# We'll keep two global references so we can unregister them independently:
_service_info_pc = None     # For "<system_name>-pc.local"
_service_info_pure = None   # For "system_name.local"


def _get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def register_mdns_pc_hostname(system_name: str, service_port=8000):
    """
    Advertise an mDNS entry for <system_name>-pc._garden._tcp.local,
    with the “server” field set to <system_name>-pc.local.
    This matches the OS hostname if you renamed it to “system_name-pc.”

    Example: if system_name == "Zone4",
      we register "Zone4-pc._garden._tcp.local." => "Zone4-pc.local"
    """
    global _zeroconf, _service_info_pc

    # Unregister old if needed
    if _service_info_pc and _zeroconf:
        try:
            _zeroconf.unregister_service(_service_info_pc)
        except Exception:
            pass
        _service_info_pc = None

    if not _zeroconf:
        _zeroconf = Zeroconf()

    appended_hostname = f"{system_name}-pc"  # e.g. "Zone4-pc"
    local_ip = _get_local_ip()

    service_type = "_http._tcp.local."
    service_name = f"{appended_hostname}.{service_type}"  # e.g. "Zone4-pc._garden._tcp.local."
    address_bytes = socket.inet_aton(local_ip)

    _service_info_pc = ServiceInfo(
        type_=service_type,
        name=service_name,
        addresses=[address_bytes],
        port=service_port,
        server=f"{appended_hostname}.local.",  # "Zone4-pc.local."
        properties={},
    )

    _zeroconf.register_service(_service_info_pc)
    print(f"[mDNS] Registered PC host '{service_name}' => {local_ip}:{service_port}")


def register_mdns_pure_system_name(system_name: str, service_port=8000):
    """
    Advertise an mDNS entry for the pure system name <system_name>._garden._tcp.local,
    with “server” field set to <system_name>.local. No “-pc” appended.

    Example: if system_name == "Zone4",
      we register "Zone4._garden._tcp.local." => "Zone4.local"
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

    service_type = "_http._tcp.local."
    service_name = f"{system_name}.{service_type}"  # e.g. "Zone4._garden._tcp.local."
    address_bytes = socket.inet_aton(local_ip)

    _service_info_pure = ServiceInfo(
        type_=service_type,
        name=service_name,
        addresses=[address_bytes],
        port=service_port,
        server=f"{system_name}.local.",  # "Zone4.local."
        properties={},
    )

    _zeroconf.register_service(_service_info_pure)
    print(f"[mDNS] Registered pure '{service_name}' => {local_ip}:{service_port}")


def close_mdns():
    """
    Unregister everything and shut down Zeroconf.
    """
    global _zeroconf, _service_info_pc, _service_info_pure

    # 1) The PC hostname (system_name-pc.local)
    if _service_info_pc and _zeroconf:
        try:
            _zeroconf.unregister_service(_service_info_pc)
        except Exception:
            pass
        _service_info_pc = None

    # 2) The pure system name (system_name.local)
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
