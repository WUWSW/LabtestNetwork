#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "=========================================================="
echo " Starting AI-Driven Network Automation System (OSPF)"
echo "=========================================================="

# 1. Start Kafka & Kafka UI
echo "[1/4] Starting Apache Kafka & Kafka UI via Docker Compose..."
docker compose up -d

# 2. Wait for Kafka to become available
echo "[2/4] Waiting for Kafka broker on port 9092..."
MAX_RETRIES=30
COUNT=0
while ! nc -z localhost 9092 2>/dev/null && [ $COUNT -lt $MAX_RETRIES ]; do
    sleep 1
    COUNT=$((COUNT+1))
done

if [ $COUNT -eq $MAX_RETRIES ]; then
    echo "Warning: Kafka port 9092 not ready after 30s. Checking container status..."
    docker compose ps
fi
echo "Kafka broker is online!"

# 3. Start Backend
echo "[3/4] Starting FastAPI Backend on http://localhost:8000..."
nohup "$DIR/venv/bin/uvicorn" backend.main:app --host 0.0.0.0 --port 8000 > "$DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > "$DIR/backend.pid"

# 4. Start Worker
echo "[4/4] Starting Python Automation Worker..."
nohup "$DIR/venv/bin/python3" "$DIR/worker/worker.py" > "$DIR/worker.log" 2>&1 &
WORKER_PID=$!
echo $WORKER_PID > "$DIR/worker.pid"

echo ""
echo "=========================================================="
echo " SYSTEM STARTED SUCCESSFULLY!"
echo "=========================================================="
echo " - Web Application Dashboard: http://localhost:8000"
echo " - Apache Kafka UI:          http://localhost:8085"
echo " - Backend PID:               $BACKEND_PID (logs in backend.log)"
echo " - Worker PID:                $WORKER_PID (logs in worker.log)"
echo "=========================================================="
echo " To stop the system, run: ./stop_all.sh"
echo "=========================================================="
