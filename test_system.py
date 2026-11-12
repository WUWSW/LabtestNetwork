"""
Unit & Integration Test Suite
Validates all backend and automation modules before deployment.
"""

import os
import sys
import unittest
import json

# Set workspace root
workspace_dir = os.path.dirname(os.path.abspath(__file__))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from backend.config_generator import generate_r1_config, generate_r2_config, generate_router_configurations
from backend.validator import validate_topology_and_config
from backend.ai_service import analyze_diagram_image
from backend.database import init_db, save_proposal, get_proposal, create_job, get_job, update_job_status
from worker.verifier import AutomatedOSPFVerifier

class MockDeployer:
    """Mock SSH deployer returning sample Cisco IOS outputs for verification testing."""
    def run_command(self, host: str, command: str):
        if "neighbor" in command:
            return {
                "success": True,
                "output": (
                    "Neighbor ID     Pri   State           Dead Time   Address         Interface\n"
                    "2.2.2.2           1   FULL/DR         00:00:34    10.1.0.2        FastEthernet1/0\n"
                )
            }
        elif "route ospf" in command:
            return {
                "success": True,
                "output": (
                    "Codes: C - connected, S - static, R - RIP, M - mobile, B - BGP\n"
                    "       O - OSPF, IA - OSPF inter area, N1 - OSPF NSSA external type 1\n"
                    "\n"
                    "Gateway of last resort is not set\n"
                    "\n"
                    "O    10.2.0.0/24 [110/2] via 10.1.0.2, 00:05:12, FastEthernet1/0\n"
                )
            }
        elif "protocols" in command:
            return {
                "success": True,
                "output": (
                    "Routing Protocol is \"ospf 1\"\n"
                    "  Outgoing update filter list for all interfaces is not set\n"
                    "  Incoming update filter list for all interfaces is not set\n"
                    "  Router ID 1.1.1.1\n"
                    "  Number of areas in this router is 1. 1 normal 0 stub 0 nssa\n"
                    "  Passive Interface(s):\n"
                    "    FastEthernet0/1\n"
                )
            }
        return {"success": False, "output": ""}

class TestNetworkAutomationSystem(unittest.TestCase):

    def setUp(self):
        init_db()

    def test_01_config_generator(self):
        """Task 3: Verify Cisco IOS command generation for R1 and R2."""
        r1_cfg = generate_r1_config("FastEthernet0/1", "FastEthernet1/0")
        self.assertIn("ip address 10.0.0.1 255.255.255.0", r1_cfg)
        self.assertIn("ip address 10.1.0.1 255.255.255.0", r1_cfg)
        self.assertIn("router ospf 1", r1_cfg)
        self.assertIn("router-id 1.1.1.1", r1_cfg)
        self.assertIn("passive-interface FastEthernet0/1", r1_cfg)
        self.assertIn("network 10.0.0.0 0.0.0.255 area 0", r1_cfg)
        self.assertIn("network 10.1.0.0 0.0.0.255 area 0", r1_cfg)
        self.assertIn("network 10.2.0.0 0.0.0.255 area 0", r1_cfg)

        r2_cfg = generate_r2_config("FastEthernet1/0", "FastEthernet0/1")
        self.assertIn("ip address 10.1.0.2 255.255.255.0", r2_cfg)
        self.assertIn("ip address 10.2.0.2 255.255.255.0", r2_cfg)
        self.assertIn("router-id 2.2.2.2", r2_cfg)
        self.assertIn("passive-interface FastEthernet0/1", r2_cfg)

    def test_02_validator(self):
        """Task 4: Validation checks for IP overlap, management interface conflict, and gateways."""
        topology = {"test": True}
        
        # Valid configuration
        res_valid = validate_topology_and_config(
            topology, "FastEthernet0/1", "FastEthernet1/0", "FastEthernet1/0", "FastEthernet0/1",
            "192.168.122.111", "192.168.122.102", protected_interfaces=["fastethernet0/0", "fa0/0"]
        )
        self.assertTrue(res_valid["valid"])

        # Invalid configuration: attempting to use protected management interface fa0/0
        res_invalid = validate_topology_and_config(
            topology, "FastEthernet0/0", "FastEthernet1/0", "FastEthernet1/0", "FastEthernet0/1",
            "192.168.122.111", "192.168.122.102", protected_interfaces=["fastethernet0/0", "fa0/0"]
        )
        self.assertFalse(res_invalid["valid"])
        failed_checks = [c for c in res_invalid["checks"] if c["status"] == "FAILED"]
        self.assertTrue(len(failed_checks) > 0)
        self.assertIn("Management Interface Protection", failed_checks[0]["name"])

    def test_03_ai_service_deterministic(self):
        """Task 2: Vision AI structured JSON and ambiguity flagging."""
        test_img = os.path.join(workspace_dir, "sample_diagrams", "media_1794463651033.png")
        self.assertTrue(os.path.exists(test_img))
        
        result = analyze_diagram_image(test_img)
        self.assertIn("devices", result)
        self.assertIn("links", result)
        self.assertIn("routing", result)
        self.assertIn("ambiguities", result)
        self.assertTrue(len(result["ambiguities"]) > 0, "Task 2 requires flagging ambiguous info")
        
        # Check OSPF specifics
        self.assertEqual(result["routing"]["process_id"], 1)
        self.assertEqual(result["routing"]["area"], 0)

    def test_04_database_operations(self):
        """Database CRUD and state transitions."""
        prop_id = "test_prop_01"
        save_proposal(prop_id, "test.png", "/path/to/test.png", {"devices": []}, "raw")
        prop = get_proposal(prop_id)
        self.assertIsNotNone(prop)
        self.assertEqual(prop["filename"], "test.png")

        job_id = "test_job_01"
        create_job(job_id, prop_id, "R1", "192.168.122.111", "conf t", "Instructor")
        job = get_job(job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "PENDING")
        self.assertEqual(job["approval_status"], "APPROVED")

        update_job_status(job_id, "SUCCESS", deployment_log="OK", verification_status="PASSED")
        updated_job = get_job(job_id)
        self.assertEqual(updated_job["status"], "SUCCESS")
        self.assertEqual(updated_job["verification_status"], "PASSED")

    def test_05_automated_ospf_verifier(self):
        """Task 8: Automated OSPF verification parser."""
        mock_deployer = MockDeployer()
        verifier = AutomatedOSPFVerifier(mock_deployer)
        report = verifier.verify_router("R1", "192.168.122.111")
        
        self.assertTrue(report["passed"])
        self.assertTrue(report["checks"]["neighbor_full"])
        self.assertTrue(report["checks"]["remote_lan_learned"])
        self.assertTrue(report["checks"]["ospf_active"])
        self.assertTrue(report["checks"]["router_id_correct"])

if __name__ == "__main__":
    unittest.main()
