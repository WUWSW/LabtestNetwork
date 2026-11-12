"""
Python Kafka Worker (Task 6)
Consumes network-config-jobs, re-checks approval with backend,
prevents duplicate execution, executes Paramiko SSH deployment,
runs automated OSPF verification, and reports progress.
"""

import os
import sys
import json
import time
import logging
import requests
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (Worker) %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("worker")

# Add current workspace to path
workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

try:
    from worker.ssh_deployer import CiscoSSHDeployer
    from worker.verifier import AutomatedOSPFVerifier
except (ImportError, ModuleNotFoundError):
    from ssh_deployer import CiscoSSHDeployer
    from verifier import AutomatedOSPFVerifier

try:
    from kafka import KafkaConsumer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "network-config-jobs")
KAFKA_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "network-worker-group")

class AutomationWorker:
    def __init__(self):
        self.deployer = CiscoSSHDeployer()
        self.verifier = AutomatedOSPFVerifier(self.deployer)
        self.processed_jobs = set()

    def recheck_approval(self, job_id: str) -> bool:
        """
        Recheck approval status with backend API (Requirement: Task 6).
        """
        try:
            url = f"{BACKEND_URL}/api/jobs/{job_id}/approval-status"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                is_approved = data.get("approved", False)
                logger.info(f"Re-checked approval for job {job_id}: {is_approved}")
                return is_approved
            else:
                logger.warning(f"Backend returned status {resp.status_code} when re-checking approval for {job_id}")
                return False
        except Exception as e:
            logger.error(f"Failed to communicate with backend to re-check approval for {job_id}: {e}")
            return False

    def update_job_progress(
        self,
        job_id: str,
        status: str,
        deployment_log: str = None,
        verification_log: str = None,
        verification_status: str = None,
        error_message: str = None
    ):
        """Report job progress back to Backend API."""
        try:
            url = f"{BACKEND_URL}/api/jobs/{job_id}/status"
            payload = {
                "status": status,
                "deployment_log": deployment_log,
                "verification_log": verification_log,
                "verification_status": verification_status,
                "error_message": error_message
            }
            resp = requests.post(url, json=payload, timeout=5)
            if resp.status_code == 200:
                logger.info(f"Updated backend job {job_id} status to {status}")
            else:
                logger.warning(f"Backend update failed with code {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Failed to update backend for job {job_id}: {e}")

    def process_job(self, job_data: dict):
        job_id = job_data.get("job_id")
        device_id = job_data.get("device_id", "Router")
        mgmt_ip = job_data.get("mgmt_ip")
        config_text = job_data.get("config_text", "")

        logger.info(f"==> Received Job {job_id} for {device_id} ({mgmt_ip})")

        # 1. Prevent duplicate execution (Idempotency)
        if job_id in self.processed_jobs:
            logger.warning(f"Job {job_id} already executed locally. Skipping duplicate.")
            return

        # 2. Recheck approval with backend
        if not self.recheck_approval(job_id):
            err_msg = f"Recheck failed: Job {job_id} is NOT approved by administrator! Aborting execution."
            logger.error(err_msg)
            self.update_job_progress(job_id, status="FAILED", error_message=err_msg)
            return

        # 3. Mark job as RUNNING
        self.update_job_progress(job_id, status="RUNNING")

        # 4. Execute Paramiko SSH Deployment (Task 7)
        logger.info(f"Starting Paramiko SSH deployment to {device_id} ({mgmt_ip})...")
        deploy_res = self.deployer.deploy_config(mgmt_ip, config_text)
        
        deployment_log = deploy_res.get("log", "")
        if not deploy_res.get("success"):
            err = deploy_res.get("error", "Deployment failed")
            logger.error(f"Deployment failed for {device_id}: {err}")
            self.update_job_progress(
                job_id,
                status="FAILED",
                deployment_log=deployment_log,
                error_message=err
            )
            return

        logger.info(f"Configuration successfully deployed to {device_id}!")
        
        # 5. Automated OSPF Verification (Task 8)
        # Give OSPF a short time (5-10s) to discover neighbor if both routers are coming up
        logger.info(f"Waiting 8 seconds for OSPF adjacency convergence before verification...")
        time.sleep(8)
        
        verify_res = self.verifier.verify_router(device_id, mgmt_ip)
        verification_log = verify_res.get("report_summary", "")
        v_passed = verify_res.get("passed", False)
        v_status = "PASSED" if v_passed else "FAILED"

        # 6. Mark SUCCESS and register as processed
        self.processed_jobs.add(job_id)
        self.update_job_progress(
            job_id,
            status="SUCCESS",
            deployment_log=deployment_log,
            verification_log=verification_log,
            verification_status=v_status
        )
        logger.info(f"==> Finished Job {job_id} for {device_id}. Verification: {v_status}")

    def run(self):
        logger.info("Starting Python Automation Worker...")
        logger.info(f"Kafka Bootstrap: {KAFKA_BOOTSTRAP}, Topic: {KAFKA_TOPIC}, Group: {KAFKA_GROUP}")
        
        while True:
            try:
                consumer = KafkaConsumer(
                    KAFKA_TOPIC,
                    bootstrap_servers=KAFKA_BOOTSTRAP.split(","),
                    group_id=KAFKA_GROUP,
                    auto_offset_reset="earliest",
                    enable_auto_commit=True,
                    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                    consumer_timeout_ms=3000
                )
                logger.info("Successfully connected Kafka Consumer. Listening for jobs...")
                
                while True:
                    for message in consumer:
                        try:
                            job_data = message.value
                            self.process_job(job_data)
                        except Exception as e:
                            logger.error(f"Error handling job message: {e}")
                    time.sleep(1)
                    
            except Exception as e:
                logger.warning(f"Kafka Consumer connection error: {e}. Retrying in 5 seconds...")
                time.sleep(5)

if __name__ == "__main__":
    worker = AutomationWorker()
    worker.run()
