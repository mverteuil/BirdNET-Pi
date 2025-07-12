from dataclasses import dataclass


@dataclass
class NetworkConfig:
    # Network-related settings
    ip_address: str = ""
    port: int = 80
    # Add other network configurations as needed
