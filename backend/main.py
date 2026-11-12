"""
FastAPI Backend Application
AI-Driven Network Automation System with OSPF, Kafka, and Paramiko.
"""

import os
import sys
import uuid
import shutil
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] (Backend) %(message)s")
logger = logging.getLogger("backend")

# Workspace root
workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from backend.database import (
    save_proposal, get_proposal, update_proposal_status,
    save_router_config, get_router_configs,
    create_job, get_job, get_all_jobs, update_job_status
)
from backend.ai_service import analyze_diagram_image
from backend.config_generator import generate_router_configurations
from backend.validator import validate_topology_and_config
from backend.kafka_producer import NetworkConfigProducer
from worker.ssh_deployer import CiscoSSHDeployer
from worker.verifier import AutomatedOSPFVerifier

# Create uploads and static dirs
UPLOAD_DIR = os.path.join(workspace_dir, "uploads")
FRONTEND_DIR = os.path.join(workspace_dir, "frontend")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(FRONTEND_DIR, exist_ok=True)

app = FastAPI(title="AI Network Automation System", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Kafka producer
kafka_producer = NetworkConfigProducer()

# Pydantic models
class ReconfigureRequest(BaseModel):
    r1_lan_int: str
    r1_wan_int: str
    r2_wan_int: str
    r2_lan_int: str
    r1_mgmt_ip: str
    r2_mgmt_ip: str

class ApproveRequest(BaseModel):
    approved_by: str = "Administrator"
    comment: Optional[str] = "Approved after manual review of OSPF parameters and addressing plan."

class JobStatusUpdate(BaseModel):
    status: str
    deployment_log: Optional[str] = None
    verification_log: Optional[str] = None
    verification_status: Optional[str] = None
    error_message: Optional[str] = None

# -------------------------------------------------------------
# REST API Endpoints
# -------------------------------------------------------------

@app.post("/api/upload")
async def upload_diagram(file: UploadFile = File(...)):
    """
    Task 1 & 2:
    Uploads network diagram image, triggers AI vision analysis,
    generates proposed Cisco IOS configurations, and runs pre-deployment validation.
    """
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".png", ".jpg", ".jpeg"]:
        raise HTTPException(status_code=400, detail="Only PNG and JPG/JPEG diagram images are supported.")

    proposal_id = str(uuid.uuid4())[:8]
    save_filename = f"{proposal_id}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, save_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    logger.info(f"Received diagram upload: {file.filename} -> {file_path}")

    # Task 2: AI Diagram Analysis
    ai_result = analyze_diagram_image(file_path)

    # Save initial proposal
    save_proposal(proposal_id, file.filename, file_path, ai_result, json_dump := "")

    # Default Interface Mappings and Management IPs from .env
    r1_lan_int = os.getenv("R1_LAN_INTERFACE", "FastEthernet0/1")
    r1_wan_int = os.getenv("R1_WAN_INTERFACE", "FastEthernet0/0")
    r2_wan_int = os.getenv("R2_WAN_INTERFACE", "FastEthernet0/0")
    r2_lan_int = os.getenv("R2_LAN_INTERFACE", "FastEthernet0/1")
    
    r1_mgmt_ip = os.getenv("ROUTER_R1_MGMT_IP", "192.168.122.111")
    r2_mgmt_ip = os.getenv("ROUTER_R2_MGMT_IP", "192.168.122.102")

    # Task 3: Generate Cisco IOS Configs
    configs = generate_router_configurations(
        ai_result, r1_lan_int, r1_wan_int, r2_wan_int, r2_lan_int
    )

    save_router_config(f"{proposal_id}_R1", proposal_id, "R1", r1_mgmt_ip, r1_lan_int, r1_wan_int, configs["R1"])
    save_router_config(f"{proposal_id}_R2", proposal_id, "R2", r2_mgmt_ip, r2_lan_int, r2_wan_int, configs["R2"])

    # Task 4: Validate proposed topology and parameters
    val_report = validate_topology_and_config(
        ai_result, r1_lan_int, r1_wan_int, r2_wan_int, r2_lan_int, r1_mgmt_ip, r2_mgmt_ip
    )

    return {
        "proposal_id": proposal_id,
        "filename": file.filename,
        "image_url": f"/uploads/{save_filename}",
        "topology": ai_result,
        "ambiguities": ai_result.get("ambiguities", []),
        "interfaces": {
            "r1_lan": r1_lan_int,
            "r1_wan": r1_wan_int,
            "r2_wan": r2_wan_int,
            "r2_lan": r2_lan_int,
            "r1_mgmt_ip": r1_mgmt_ip,
            "r2_mgmt_ip": r2_mgmt_ip
        },
        "configurations": configs,
        "validation": val_report
    }

@app.post("/api/proposals/{proposal_id}/reconfigure")
async def reconfigure_proposal(proposal_id: str, req: ReconfigureRequest):
    """
    Allows administrator to edit interface mappings or management IPs,
    re-generating configs and re-validating before approval.
    """
    proposal = get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    topology = proposal.get("topology", {})
    
    # Re-generate configs
    configs = generate_router_configurations(
        topology, req.r1_lan_int, req.r1_wan_int, req.r2_wan_int, req.r2_lan_int
    )

    save_router_config(f"{proposal_id}_R1", proposal_id, "R1", req.r1_mgmt_ip, req.r1_lan_int, req.r1_wan_int, configs["R1"])
    save_router_config(f"{proposal_id}_R2", proposal_id, "R2", req.r2_mgmt_ip, req.r2_lan_int, req.r2_wan_int, configs["R2"])

    # Re-validate
    val_report = validate_topology_and_config(
        topology, req.r1_lan_int, req.r1_wan_int, req.r2_wan_int, req.r2_lan_int, req.r1_mgmt_ip, req.r2_mgmt_ip
    )

    return {
        "proposal_id": proposal_id,
        "configurations": configs,
        "validation": val_report
    }

@app.post("/api/proposals/{proposal_id}/approve-and-deploy")
async def approve_and_deploy(proposal_id: str, req: ApproveRequest):
    """
    Task 4 & 5:
    Administrator explicit approval gate.
    Creates pending jobs and publishes them to Kafka topic 'network-config-jobs'.
    """
    proposal = get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    router_configs = get_router_configs(proposal_id)
    if not router_configs:
        raise HTTPException(status_code=400, detail="No router configurations found for proposal.")

    dispatched_jobs = []

    for rc in router_configs:
        job_id = f"JOB-{proposal_id}-{rc['device_id']}-{str(uuid.uuid4())[:4]}"
        
        # Save Job in DB with status PENDING, approved_status APPROVED
        create_job(
            job_id=job_id,
            proposal_id=proposal_id,
            device_id=rc["device_id"],
            mgmt_ip=rc["mgmt_ip"],
            config_text=rc["config_text"],
            approved_by=req.approved_by
        )

        # Task 5: Kafka Producer dispatch
        try:
            kafka_res = kafka_producer.publish_job(
                job_id=job_id,
                proposal_id=proposal_id,
                device_id=rc["device_id"],
                mgmt_ip=rc["mgmt_ip"],
                config_text=rc["config_text"],
                approved_by=req.approved_by,
                metadata={"lan_interface": rc["lan_interface"], "wan_interface": rc["wan_interface"]}
            )
            dispatched_jobs.append({
                "job_id": job_id,
                "device_id": rc["device_id"],
                "mgmt_ip": rc["mgmt_ip"],
                "kafka_status": "DISPATCHED",
                "kafka_info": kafka_res
            })
        except Exception as e:
            logger.error(f"Failed to publish to Kafka for {rc['device_id']}: {e}")
            update_job_status(job_id, status="FAILED", error_message=f"Kafka dispatch failed: {str(e)}")
            dispatched_jobs.append({
                "job_id": job_id,
                "device_id": rc["device_id"],
                "mgmt_ip": rc["mgmt_ip"],
                "kafka_status": "FAILED",
                "error": str(e)
            })

    update_proposal_status(proposal_id, "APPROVED")

    return {
        "success": True,
        "proposal_id": proposal_id,
        "message": f"Configurations for {len(dispatched_jobs)} routers approved and sent to Kafka topic.",
        "jobs": dispatched_jobs
    }

@app.get("/api/jobs/{job_id}/approval-status")
async def get_job_approval_status(job_id: str):
    """
    Task 6:
    Endpoint called by Worker to recheck that the job was explicitly approved by Admin.
    """
    job = get_job(job_id)
    if not job:
        return {"approved": False, "reason": "Job not found"}
    is_approved = (job.get("approval_status") == "APPROVED")
    return {
        "job_id": job_id,
        "approved": is_approved,
        "approved_by": job.get("approved_by"),
        "approved_at": job.get("approved_at")
    }

@app.post("/api/jobs/{job_id}/status")
async def update_job_status_endpoint(job_id: str, update: JobStatusUpdate):
    """
    Task 6 & 9:
    Endpoint called by Worker to report status (RUNNING, SUCCESS, FAILED) and logs.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    update_job_status(
        job_id=job_id,
        status=update.status,
        deployment_log=update.deployment_log,
        verification_log=update.verification_log,
        verification_status=update.verification_status,
        error_message=update.error_message
    )
    return {"success": True, "job_id": job_id, "status": update.status}

@app.get("/api/jobs")
async def list_jobs():
    """
    Task 9:
    Web job monitoring list: returns all jobs with status, timestamps, and logs.
    """
    return get_all_jobs()

@app.get("/api/jobs/{job_id}")
async def get_job_detail(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.post("/api/jobs/{job_id}/reverify")
async def reverify_job(job_id: str):
    """
    On-demand re-verification trigger.
    Allows re-running OSPF checks (show ip ospf neighbor, show ip route ospf)
    without reapplying the configuration.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    device_id = job.get("device_id", "Router")
    mgmt_ip = job.get("mgmt_ip")

    deployer = CiscoSSHDeployer()
    verifier = AutomatedOSPFVerifier(deployer)
    v_res = verifier.verify_router(device_id, mgmt_ip)

    v_passed = v_res.get("passed", False)
    v_status = "PASSED" if v_passed else "FAILED"
    v_log = v_res.get("report_summary", "")

    update_job_status(
        job_id=job_id,
        status="SUCCESS" if v_passed else job.get("status", "SUCCESS"),
        verification_log=v_log,
        verification_status=v_status
    )

    return {
        "job_id": job_id,
        "device_id": device_id,
        "verification_status": v_status,
        "report": v_res
    }

# Mount static frontend and uploads
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("BACKEND_HOST", "0.0.0.0")
    port = int(os.getenv("BACKEND_PORT", "8000"))
    uvicorn.run("backend.main:app", host=host, port=port, reload=True)
