# AI-Driven Network Configuration and Automation System Using OSPF

[![Kafka](https://img.shields.io/badge/Kafka-3.8.0-black?logo=apachekafka)](https://kafka.apache.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Paramiko](https://img.shields.io/badge/Paramiko-SSH-blue)](https://www.paramiko.org/)
[![OSPFv2](https://img.shields.io/badge/Routing-OSPFv2%20Area%200-orange)](https://en.wikipedia.org/wiki/Open_Shortest_Path_First)

---

## 1. Project Overview & Architecture

This system implements an end-to-end, web-based AI network automation pipeline according to the **Final Practical Lab Examination: AI-Driven Network Configuration and Automation Using OSPF** (20 Points / 10 Tasks).

### Workflow:
1. **Upload & Preview Diagram (Task 1)**: User uploads topology diagram (PNG/JPG).
2. **AI Diagram Analysis (Task 2)**: Vision AI extracts topology, addressing plan, and OSPF parameters into structured JSON; flags ambiguities without guessing.
3. **Cisco IOS & OSPF Generation (Task 3)**: Synthesizes Cisco IOS commands for R1 & R2 (OSPF process 1, Area 0, Router IDs 1.1.1.1 & 2.2.2.2, passive LAN interfaces, advertises three /24 subnets).
4. **Validation & Admin Approval (Task 4)**: Validates subnets, gateway matches, interface separation from management IP, and enforces explicit administrator approval.
5. **Kafka Producer (Task 5)**: Dispatches approved configuration jobs to Kafka topic `network-config-jobs`.
6. **Kafka Consumer & Python Worker (Task 6)**: Python worker consumes jobs, re-checks approval with backend, and prevents duplicate execution.
7. **Paramiko SSH Deployment (Task 7)**: Worker connects via out-of-band management IP to deploy configurations without hardcoded credentials.
8. **Automated OSPF Verification (Task 8)**: Automatically executes `show ip ospf neighbor`, `show ip route ospf`, `show ip protocols` and confirms FULL adjacency and remote LAN route learning.
9. **Web Job Monitoring (Task 9)**: Real-time dashboard showing `PENDING`, `RUNNING`, `SUCCESS`, and `FAILED` states with timestamps and command outputs.
10. **End-to-End Connectivity (Task 10)**: Validates that PC1 (`10.0.0.10`) can ping PC2 (`10.2.0.10`) without manual router configuration.

---

## 2. Directory Structure

```
├── docker-compose.yml       # Apache Kafka (KRaft mode) & Kafka UI
├── .env.example             # Configuration template
├── .env                     # Local configuration & credentials
├── requirements.txt         # Python dependencies
├── run_all.sh               # One-click startup script
├── stop_all.sh              # Clean shutdown script
├── test_system.py           # Comprehensive unit & integration test suite
├── backend/
│   ├── main.py              # FastAPI application & REST endpoints
│   ├── ai_service.py        # Vision AI analyzer (Gemini/OpenAI/Deterministic)
│   ├── config_generator.py  # Cisco IOS OSPF CLI syntax generator
│   ├── validator.py         # Subnet & interface validation engine
│   ├── kafka_producer.py    # Kafka message dispatcher
│   └── database.py          # SQLite database storage
├── worker/
│   ├── worker.py            # Kafka consumer worker & approval re-checker
│   ├── ssh_deployer.py      # Paramiko SSH deployment engine
│   └── verifier.py          # Automated OSPF neighbor & route verifier
├── frontend/
│   ├── index.html           # Web UI dashboard
│   └── app.js               # Frontend JavaScript logic
└── sample_diagrams/         # Exam topology diagram images for testing
```

---

## 3. Quick Start & Setup Instructions

### Step 1: Install Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
Copy `.env.example` to `.env` and verify your router management IPs and SSH credentials:
```bash
cp .env.example .env
nano .env
```
Key settings:
* `ROUTER_R1_MGMT_IP`: Out-of-band management IP for R1 (e.g., `192.168.122.111`)
* `ROUTER_R2_MGMT_IP`: Out-of-band management IP for R2 (e.g., `192.168.122.102`)
* `ROUTER_SSH_USER`: SSH username (e.g., `cisco`)
* `ROUTER_SSH_PASSWORD`: SSH password (e.g., `cisco`)
* `ROUTER_ENABLE_PASSWORD`: Enable secret (e.g., `cisco`)
* `AI_API_KEY`: (Optional) Google Gemini API Key for online vision inference. If blank, built-in high-fidelity deterministic engine is used.

### Step 3: Start Services
Run the startup script:
```bash
./run_all.sh
```
This automatically starts:
* **Kafka & Kafka-UI**: `http://localhost:8085`
* **FastAPI Backend**: `http://localhost:8000`
* **Python Worker**: Background consumer process

---

## 4. Live Demonstration Steps (Exam Acceptance Test)

1. **Instructor Resets Routers**:
   * Data-plane configurations on R1 and R2 are reset.
   * Independent management SSH access remains reachable.
2. **Open Web Application**:
   * Navigate to `http://localhost:8000` in a browser.
3. **Upload Diagram (Task 1)**:
   * Select `sample_diagrams/media_1794463651033.png`.
   * Click **Generate AI Plan**.
4. **Review AI Extraction (Task 2 & 3)**:
   * Inspect extracted structured JSON.
   * Review flagged ambiguities and proposed Cisco IOS configurations.
5. **Pre-Deploy Validation (Task 4)**:
   * Confirm all subnet and interface checks show `PASSED`.
6. **Administrator Approval (Task 4 & 5)**:
   * Click **Approve & Dispatch to Kafka**.
   * Confirm Kafka receives the jobs (viewable in Kafka UI at `http://localhost:8085`).
7. **Worker Deployment & Automated Verification (Task 6, 7, 8 & 9)**:
   * Watch live status transition: `PENDING` $\rightarrow$ `RUNNING` $\rightarrow$ `SUCCESS`.
   * Click **View Logs** to show the instructor:
     - Paramiko SSH CLI deployment log.
     - `show ip ospf neighbor` showing `FULL` state.
     - `show ip route ospf` showing remote LAN learned with code `O`.
     - `show ip protocols` showing OSPF 1 and Router ID.
8. **End-to-End Ping Test (Task 10)**:
   * On GNS3 PC1 console, execute:
     ```bash
     ping 10.2.0.10
     ```
   * Confirm 100% reply packets received!

---

## 5. Verification & Testing

To run the automated test suite locally:
```bash
./venv/bin/python3 test_system.py
```
Expected output:
```
Ran 5 tests in 0.034s
OK
```
