#!/usr/bin/env bash

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "Stopping AI Network Automation System..."

# Stop Backend
if [ -f "$DIR/backend.pid" ]; then
    PID=$(cat "$DIR/backend.pid")
    echo "Stopping Backend (PID $PID)..."
    kill $PID 2>/dev/null || true
    rm -f "$DIR/backend.pid"
fi

# Stop Worker
if [ -f "$DIR/worker.pid" ]; then
    PID=$(cat "$DIR/worker.pid")
    echo "Stopping Worker (PID $PID)..."
    kill $PID 2>/dev/null || true
    rm -f "$DIR/worker.pid"
fi

# Stop Docker Compose
echo "Stopping Docker containers..."
docker compose down

echo "All services stopped cleanly."
