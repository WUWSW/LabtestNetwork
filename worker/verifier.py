"""
Automated OSPF Verification Engine (Task 8)
Executes verification commands on Cisco routers:
- show ip ospf neighbor (confirms FULL adjacency)
- show ip route ospf (confirms remote LAN route learned via OSPF)
- show ip protocols (confirms OSPF process 1, router-id, passive interfaces)
"""

import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("ospf_verifier")

class AutomatedOSPFVerifier:
    def __init__(self, deployer):
        self.deployer = deployer

    def verify_router(self, device_id: str, host: str) -> Dict[str, Any]:
        """
        Run all Task 8 verification commands against the specified router.
        """
        logger.info(f"Running automated OSPF verification on {device_id} ({host})...")
        
        # 1. show ip ospf neighbor
        neighbor_res = self.deployer.run_command(host, "show ip ospf neighbor")
        neighbor_output = neighbor_res.get("output", "")
        
        # 2. show ip route ospf
        route_res = self.deployer.run_command(host, "show ip route ospf")
        route_output = route_res.get("output", "")
        
        # 3. show ip protocols
        proto_res = self.deployer.run_command(host, "show ip protocols")
        proto_output = proto_res.get("output", "")
        
        # Parse neighbor state
        # Expecting line with state containing "FULL" (e.g., FULL/DR, FULL/BDR, FULL/-)
        has_full_neighbor = bool(re.search(r"\bFULL\b", neighbor_output, re.IGNORECASE))
        
        # Parse expected neighbor router ID:
        # If we are R1, expected neighbor is 2.2.2.2
        # If we are R2, expected neighbor is 1.1.1.1
        expected_neighbor_id = "2.2.2.2" if device_id.upper() == "R1" else "1.1.1.1"
        found_expected_neighbor = expected_neighbor_id in neighbor_output
        
        # Parse route ospf:
        # If we are R1, expected remote LAN is 10.2.0.0/24 (or 10.2.0.0) with code O
        # If we are R2, expected remote LAN is 10.0.0.0/24 (or 10.0.0.0) with code O
        expected_remote_lan = "10.2.0.0" if device_id.upper() == "R1" else "10.0.0.0"
        has_remote_lan_route = False
        for line in route_output.splitlines():
            if expected_remote_lan in line and line.strip().startswith("O"):
                has_remote_lan_route = True
                break
        # Also check without strict leading O if line wrapped
        if not has_remote_lan_route and expected_remote_lan in route_output and "via" in route_output:
            has_remote_lan_route = True
            
        # Parse protocols:
        # Expecting "Routing Protocol is \"ospf 1\"" or "ospf 1"
        # Expecting Router ID (1.1.1.1 for R1, 2.2.2.2 for R2)
        expected_router_id = "1.1.1.1" if device_id.upper() == "R1" else "2.2.2.2"
        has_ospf_active = "ospf 1" in proto_output.lower() or "routing protocol is \"ospf 1\"" in proto_output.lower()
        has_correct_router_id = expected_router_id in proto_output
        has_passive_lan = "passive" in proto_output.lower()
        
        # Overall check
        all_passed = has_full_neighbor and has_remote_lan_route and has_ospf_active
        
        summary_lines = [
            f"=== OSPF VERIFICATION REPORT FOR {device_id} ({host}) ===",
            f"1. OSPF Neighbor FULL Adjacency: {'[PASSED] Neighbor state is FULL' if has_full_neighbor else '[FAILED] No FULL neighbor detected'}",
            f"   - Expected Neighbor Router ID: {expected_neighbor_id} ({'Found' if found_expected_neighbor else 'Not Found'})",
            f"2. Remote LAN Learned via OSPF: {'[PASSED] Route to ' + expected_remote_lan + '/24 present' if has_remote_lan_route else '[FAILED] Remote LAN route missing'}",
            f"3. OSPF Process & Router-ID: {'[PASSED] OSPF 1 active with ID ' + expected_router_id if (has_ospf_active and has_correct_router_id) else '[WARNING] Protocol check: OSPF=' + str(has_ospf_active) + ' ID=' + str(has_correct_router_id)}",
            f"   - Passive Interface Configured: {'Yes' if has_passive_lan else 'No'}",
            f"Overall Verification Status: {'PASSED' if all_passed else 'PENDING/FAILED'}",
            "============================================================"
        ]
        
        report_text = "\n".join(summary_lines)
        logger.info(report_text)
        
        return {
            "device_id": device_id,
            "host": host,
            "passed": all_passed,
            "checks": {
                "neighbor_full": has_full_neighbor,
                "neighbor_id_found": found_expected_neighbor,
                "remote_lan_learned": has_remote_lan_route,
                "ospf_active": has_ospf_active,
                "router_id_correct": has_correct_router_id,
                "passive_lan_detected": has_passive_lan
            },
            "report_summary": report_text,
            "raw_commands": {
                "show_ip_ospf_neighbor": neighbor_output,
                "show_ip_route_ospf": route_output,
                "show_ip_protocols": proto_output
            }
        }
