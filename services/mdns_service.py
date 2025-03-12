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
