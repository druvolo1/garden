import socket
import datetime
from zeroconf import Zeroconf, ServiceInfo, NonUniqueNameException

_zeroconf = None
_service_info = None

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()

def update_mdns_service(system_name="ZoneX", port=8000):
    global _zeroconf, _service_info

    # If we previously registered, remove it first
    if _zeroconf and _service_info:
        _zeroconf.unregister_service(_service_info)
        _service_info = None
        print("[mDNS] Unregistered old service.")

    # If we have no Zeroconf instance yet, create one
    if not _zeroconf:
        _zeroconf = Zeroconf()

    service_type = "_http._tcp.local."
    host_ip = get_local_ip()                  # e.g. "192.168.1.50"
    ip_bytes = socket.inet_aton(host_ip)

    def do_register(name):
        """
        Inner function that tries to register a given name,
        returning True on success, or False if conflict.
        """
        full_service_name = f"{name}.{service_type}"
        server_hostname  = f"{name}.local."
        info = ServiceInfo(
            type_=service_type,
            name=full_service_name,
            addresses=[ip_bytes],
            port=port,
            properties={},
            server=server_hostname,
        )
        try:
            _zeroconf.register_service(info)
            return info  # success
        except NonUniqueNameException:
            return None  # conflict

    # First try the user-supplied name
    attempted_name = system_name
    service_info = do_register(attempted_name)

    if service_info is None:
        # Conflict -> construct a fallback name with a timestamp
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        fallback_name = f"{system_name}-{ts}"
        print(f"[mDNS] Detected conflict. Using fallback name: {fallback_name}")
        service_info = do_register(fallback_name)
        if not service_info:
            print("[mDNS] Fallback registration also failed! Some deeper conflict.")
            return  # or raise an exception

    _service_info = service_info
    print(f"[mDNS] Registered service: {_service_info.name} at {host_ip}:{port}")

def stop_mdns_service():
    global _zeroconf, _service_info
    if _zeroconf:
        if _service_info:
            _zeroconf.unregister_service(_service_info)
            _service_info = None
            print("[mDNS] Service unregistered.")
        _zeroconf.close()
        _zeroconf = None
        print("[mDNS] Zeroconf closed.")

if __name__ == "__main__":
    print("[mDNS] Testing direct run with 'MyCustomName' ...")
    update_mdns_service(system_name="MyCustomName", port=8000)
    try:
        input("Press Enter to unregister and exit...\n")
    finally:
        stop_mdns_service()
