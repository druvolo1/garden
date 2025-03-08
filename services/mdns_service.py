import socket
from zeroconf import Zeroconf, ServiceInfo

_zeroconf = None
_service_info = None

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
    Register an mDNS service so that this device appears under:
        <system_name>._garden._tcp.local.
    at port=service_port.

    If a previous name was registered, it’s unregistered first.
    """
    global _zeroconf, _service_info

    # If we previously had a service registered, remove it
    if _service_info and _zeroconf:
        try:
            _zeroconf.unregister_service(_service_info)
        except Exception:
            pass
        _service_info = None

    if not _zeroconf:
        _zeroconf = Zeroconf()

    local_ip = _get_local_ip()
    # For the service type, pick whatever meets your needs. 
    # _garden._tcp.local. is just an example:
    service_type = "_garden._tcp.local."
    # The "name" must end with the service_type:
    service_name = f"{system_name}.{service_type}"

    # Convert IP string to the 4-byte format:
    address_bytes = socket.inet_aton(local_ip)

    _service_info = ServiceInfo(
        type_=service_type,
        name=service_name,
        addresses=[address_bytes],
        port=service_port,
        # The 'server' argument sets the "host" to something like "MyName.local."
        server=f"{system_name}.local.",
        properties={},  # optional key-value dictionary
    )

    _zeroconf.register_service(_service_info)
    print(f"[mDNS] Registered '{service_name}' pointing to {local_ip}:{service_port}")


def close_mdns():
    """
    Unregister and shut down Zeroconf if running.
    """
    global _zeroconf, _service_info
    if _service_info and _zeroconf:
        try:
            _zeroconf.unregister_service(_service_info)
        except Exception:
            pass
        _service_info = None
    if _zeroconf:
        _zeroconf.close()
        _zeroconf = None
    print("[mDNS] Closed Zeroconf.")
