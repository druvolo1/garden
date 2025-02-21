from zeroconf import Zeroconf, ServiceInfo
import socket

def register_mdns_service(system_name="Zone1", port=8000):
    """
    Registers an mDNS service so that it can be discovered as <system_name>.local on the network.
    In mDNS tools, this may appear as "<system_name>._http._tcp.local." or similar.
    """
    zeroconf = Zeroconf()
    
    # mDNS service type for an HTTP server (adjust if needed)
    service_type = "_http._tcp.local."

    # The "instance name" in Zeroconf. Typically something like "MyGardenService._http._tcp.local."
    # Here, we'll just use system_name for clarity.
    full_service_name = f"{system_name}.{service_type}"

    # Use system_name for the "server" field, appended with '.local.'
    # This way, it will advertise itself as system_name.local instead of <actual-hostname>.local
    server_hostname = f"{system_name}.local."

    # Get your local IP address. If your machine has multiple interfaces, you may
    # need a more robust approach than just gethostbyname.
    # Or you could pass in the IP you want to advertise.
    host_ip = socket.gethostbyname(socket.gethostname())
    ip_bytes = socket.inet_aton(host_ip)

    info = ServiceInfo(
        type_=service_type,
        name=full_service_name,
        addresses=[ip_bytes],
        port=port,
        properties={},
        server=server_hostname,  # <--- The key part
    )

    # Register the service on the network
    zeroconf.register_service(info)
    print(f"mDNS service registered: {full_service_name} at {server_hostname}:{port}")

    # Return them if you want to manage them later.
    return zeroconf, info

if __name__ == "__main__":
    # For testing: register using "MyCustomName" until Enter is pressed.
    zc, info = register_mdns_service(system_name="MyCustomName", port=8000)
    try:
        input("Press Enter to unregister service and exit...\n")
    finally:
        zc.unregister_service(info)
        zc.close()
