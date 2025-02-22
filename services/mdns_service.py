import socket
from zeroconf import Zeroconf, ServiceInfo

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # We won't actually send any data to 8.8.8.8
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()

def register_mdns_service(system_name="ZoneX", port=8000):
    zeroconf = Zeroconf()
    service_type = "_http._tcp.local."
    full_service_name = f"{system_name}.{service_type}"
    server_hostname = f"{system_name}.local."

    # Use the more robust method:
    host_ip = get_local_ip()
    ip_bytes = socket.inet_aton(host_ip)

    info = ServiceInfo(
        type_=service_type,
        name=full_service_name,
        addresses=[ip_bytes],
        port=port,
        properties={},
        server=server_hostname,
    )

    zeroconf.register_service(info)
    print(f"mDNS service registered: {full_service_name} at {server_hostname}:{port} (advertising {host_ip})")

    return zeroconf, info


if __name__ == "__main__":
    # For testing: register using "MyCustomName" until Enter is pressed.
    zc, info = register_mdns_service(system_name="MyCustomName", port=8000)
    try:
        input("Press Enter to unregister service and exit...\n")
    finally:
        zc.unregister_service(info)
        zc.close()
