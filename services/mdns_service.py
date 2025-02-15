from zeroconf import Zeroconf, ServiceInfo
import socket

def register_mdns_service(service_name="MyGardenService", port=8000):
    """
    Registers an mDNS service so that it can be discovered as service_name.local on the network.
    """
    zeroconf = Zeroconf()
    
    # Service type for an HTTP server; change if needed.
    service_type = "_http._tcp.local."
    full_service_name = f"{service_name}.{service_type}"
    
    # Get your local hostname and IP address.
    # The hostname for the mDNS advertisement should typically end in '.local.'
    host_name = socket.gethostname()
    local_hostname = f"{host_name}.local."
    
    # Get local IP address (you might need a more robust method if there are multiple interfaces)
    ip_address = socket.gethostbyname(host_name)
    ip_bytes = socket.inet_aton(ip_address)
    
    info = ServiceInfo(
        type_=service_type,
        name=full_service_name,
        addresses=[ip_bytes],
        port=port,
        properties={},
        server=local_hostname,
    )
    
    # Register the service
    zeroconf.register_service(info)
    print(f"mDNS service registered: {full_service_name} at {local_hostname}:{port}")
    
    # Optionally, return the zeroconf instance and info so you can unregister later.
    return zeroconf, info

if __name__ == "__main__":
    # For testing purposes: register the service until Enter is pressed.
    zc, info = register_mdns_service()
    try:
        input("Press Enter to unregister service and exit...\n")
    finally:
        zc.unregister_service(info)
        zc.close()
