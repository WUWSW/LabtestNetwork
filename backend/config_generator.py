"""
Cisco IOS & OSPF Configuration Generator (Task 3)
Generates syntax-valid Cisco IOS commands according to topology requirements.
"""

from typing import Dict, Any, List

def generate_r1_config(lan_int: str, wan_int: str, topology: Dict[str, Any] = None) -> str:
    """
    R1 Configuration:
    - LAN: 10.0.0.1/24 (gateway for PC1 10.0.0.10)
    - WAN (R1-R2): 10.1.0.1/24
    - OSPFv2 Process 1, Area 0, Router-ID 1.1.1.1
    - Passive interface on LAN
    - Advertises all three /24 networks (10.0.0.0/24, 10.1.0.0/24, 10.2.0.0/24)
    """
    lines = [
        "configure terminal",
        f"interface {lan_int}",
        " description LAN-Facing interface to PC1",
        " ip address 10.0.0.1 255.255.255.0",
        " no shutdown",
        " exit",
        f"interface {wan_int}",
        " description Inter-Router link to R2",
        " ip address 10.1.0.1 255.255.255.0",
        " no shutdown",
        " exit",
        "router ospf 1",
        " router-id 1.1.1.1",
        f" passive-interface {lan_int}",
        " network 10.0.0.0 0.0.0.255 area 0",
        " network 10.1.0.0 0.0.0.255 area 0",
        " network 10.2.0.0 0.0.0.255 area 0",
        " exit",
        "end",
        "write memory"
    ]
    return "\n".join(lines)

def generate_r2_config(wan_int: str, lan_int: str, topology: Dict[str, Any] = None) -> str:
    """
    R2 Configuration:
    - WAN (R1-R2): 10.1.0.2/24
    - LAN: 10.2.0.2/24 (gateway for PC2 10.2.0.10)
    - OSPFv2 Process 1, Area 0, Router-ID 2.2.2.2
    - Passive interface on LAN
    - Advertises all three /24 networks (10.0.0.0/24, 10.1.0.0/24, 10.2.0.0/24)
    """
    lines = [
        "configure terminal",
        f"interface {wan_int}",
        " description Inter-Router link to R1",
        " ip address 10.1.0.2 255.255.255.0",
        " no shutdown",
        " exit",
        f"interface {lan_int}",
        " description LAN-Facing interface to PC2",
        " ip address 10.2.0.2 255.255.255.0",
        " no shutdown",
        " exit",
        "router ospf 1",
        " router-id 2.2.2.2",
        f" passive-interface {lan_int}",
        " network 10.0.0.0 0.0.0.255 area 0",
        " network 10.1.0.0 0.0.0.255 area 0",
        " network 10.2.0.0 0.0.0.255 area 0",
        " exit",
        "end",
        "write memory"
    ]
    return "\n".join(lines)

def generate_router_configurations(
    topology: Dict[str, Any], 
    r1_lan_int: str, 
    r1_wan_int: str, 
    r2_wan_int: str, 
    r2_lan_int: str
) -> Dict[str, str]:
    """
    Generate configurations for all routers in the topology dictionary.
    """
    r1_cfg = generate_r1_config(r1_lan_int, r1_wan_int, topology)
    r2_cfg = generate_r2_config(r2_wan_int, r2_lan_int, topology)
    return {
        "R1": r1_cfg,
        "R2": r2_cfg
    }
