import sqlite3
import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "automation.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Diagrams and AI analysis proposals
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS proposals (
        id TEXT PRIMARY KEY,
        filename TEXT,
        image_path TEXT,
        topology_json TEXT,
        raw_ai_output TEXT,
        status TEXT, -- DRAFT, VALIDATED, APPROVED, REJECTED
        created_at TEXT,
        updated_at TEXT
    )
    """)
    
    # Generated configurations per router
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS router_configs (
        id TEXT PRIMARY KEY,
        proposal_id TEXT,
        device_id TEXT, -- R1, R2
        mgmt_ip TEXT,
        lan_interface TEXT,
        wan_interface TEXT,
        config_text TEXT,
        status TEXT, -- DRAFT, APPROVED, DISPATCHED, COMPLETED, FAILED
        created_at TEXT,
        FOREIGN KEY (proposal_id) REFERENCES proposals(id)
    )
    """)
    
    # Kafka jobs & execution logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        job_id TEXT PRIMARY KEY,
        proposal_id TEXT,
        device_id TEXT,
        mgmt_ip TEXT,
        config_text TEXT,
        status TEXT, -- PENDING, RUNNING, SUCCESS, FAILED
        approval_status TEXT, -- APPROVED, REJECTED
        approved_by TEXT,
        approved_at TEXT,
        started_at TEXT,
        completed_at TEXT,
        deployment_log TEXT,
        verification_log TEXT,
        verification_status TEXT, -- PASSED, FAILED
        error_message TEXT,
        created_at TEXT
    )
    """)
    
    conn.commit()
    conn.close()

def save_proposal(proposal_id: str, filename: str, image_path: str, topology: Dict[str, Any], raw_output: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
    INSERT OR REPLACE INTO proposals (id, filename, image_path, topology_json, raw_ai_output, status, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (proposal_id, filename, image_path, json.dumps(topology), raw_output, "DRAFT", now, now))
    conn.commit()
    conn.close()

def get_proposal(proposal_id: str) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["topology"] = json.loads(d["topology_json"]) if d["topology_json"] else {}
    return d

def update_proposal_status(proposal_id: str, status: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE proposals SET status = ?, updated_at = ? WHERE id = ?", (status, datetime.utcnow().isoformat(), proposal_id))
    conn.commit()
    conn.close()

def save_router_config(config_id: str, proposal_id: str, device_id: str, mgmt_ip: str, 
                       lan_interface: str, wan_interface: str, config_text: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
    INSERT OR REPLACE INTO router_configs (id, proposal_id, device_id, mgmt_ip, lan_interface, wan_interface, config_text, status, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (config_id, proposal_id, device_id, mgmt_ip, lan_interface, wan_interface, config_text, "DRAFT", now))
    conn.commit()
    conn.close()

def get_router_configs(proposal_id: str) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM router_configs WHERE proposal_id = ?", (proposal_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_job(job_id: str, proposal_id: str, device_id: str, mgmt_ip: str, config_text: str, approved_by: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
    INSERT OR REPLACE INTO jobs 
    (job_id, proposal_id, device_id, mgmt_ip, config_text, status, approval_status, approved_by, approved_at, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (job_id, proposal_id, device_id, mgmt_ip, config_text, "PENDING", "APPROVED", approved_by, now, now))
    conn.commit()
    conn.close()

def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_jobs() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_job_status(job_id: str, status: str, deployment_log: Optional[str] = None, 
                      verification_log: Optional[str] = None, verification_status: Optional[str] = None, 
                      error_message: Optional[str] = None) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    
    updates = ["status = ?"]
    params = [status]
    
    if status == "RUNNING":
        updates.append("started_at = ?")
        params.append(now)
    elif status in ["SUCCESS", "FAILED"]:
        updates.append("completed_at = ?")
        params.append(now)
        
    if deployment_log is not None:
        updates.append("deployment_log = ?")
        params.append(deployment_log)
    if verification_log is not None:
        updates.append("verification_log = ?")
        params.append(verification_log)
    if verification_status is not None:
        updates.append("verification_status = ?")
        params.append(verification_status)
    if status == "SUCCESS":
        updates.append("error_message = NULL")
    elif error_message is not None:
        updates.append("error_message = ?")
        params.append(error_message)
        
    params.append(job_id)
    sql = f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?"
    cursor.execute(sql, params)
    conn.commit()
    conn.close()

# Initialize DB on load
init_db()
