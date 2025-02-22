import socket
from zeroconf import Zeroconf, ServiceInfo

# We'll keep module-level references so we can unregister/re-register
_zeroconf = None
_service_info = None

def get_local_ip():
    """
    Returns the primary IP address for outbound connections.
    Useful for picking the correct LAN IP even if multiple interfaces exist.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()

def update_mdns_service(system_name="ZoneX", port=8000):
    """
    (Re)registers the mDNS service under the given system_name.
    If an existing service is registered, it will be unregistered first.
    """
    global _zeroconf, _service_info

    # If we've already registered a service, unregister it to remove the old name
    if _zeroconf and _service_info:
        _zeroconf.unregister_service(_service_info)
        _service_info = None
        print("[mDNS] Unregistered old service.")

    # If we haven't created a Zeroconf instance yet, do so
    if not _zeroconf:
        _zeroconf = Zeroconf()

    # Construct new service info
    service_type = "_http._tcp.local."
    full_service_name = f"{system_name}.{service_type}"
    server_hostname = f"{system_name}.local."

    host_ip = get_local_ip()            # e.g. "192.168.1.50"
    ip_bytes = socket.inet_aton(host_ip)

    service_info = ServiceInfo(
        type_=service_type,
        name=full_service_name,
        addresses=[ip_bytes],
        port=port,
        properties={},
        server=server_hostname,
    )

    # Register the new service
    _zeroconf.register_service(service_info)
    _service_info = service_info

    print(f"[mDNS] Registered service: {full_service_name} at {server_hostname}:{port} (IP: {host_ip})")

def stop_mdns_service():
    """
    Unregisters and closes the Zeroconf service if running.
    """
    global _zeroconf, _service_info

    if _zeroconf:
        if _service_info:
            _zeroconf.unregister_service(_service_info)
            _service_info = None
            print("[mDNS] Service unregistered.")
        _zeroconf.close()
        _zeroconf = None
        print("[mDNS] Zeroconf closed.")


# Optional: If you run mdns_service.py directly for testing
if __name__ == "__main__":
    print("[mDNS] Testing direct run with 'MyCustomName' ...")
    update_mdns_service(system_name="MyCustomName", port=8000)
    try:
        input("Press Enter to unregister and exit...\n")
    finally:
        stop_mdns_service()
