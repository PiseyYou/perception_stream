#!/bin/bash
# Quick restart script for offline_server and ssh_bridge services

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"

echo "=== Stopping old services ==="
pkill -f offline_server.py
pkill -f ssh_bridge.py
sleep 2

echo ""
echo "=== Starting services ==="
cd "$PROJECT_DIR"

# Start offline_server
nohup python3 robot_monitor/offline_server.py > /tmp/offline_server.log 2>&1 &
OFFLINE_PID=$!
echo "Started offline_server (PID: $OFFLINE_PID)"

# Start ssh_bridge
nohup python3 robot_monitor/ssh_bridge.py > /tmp/ssh_bridge.log 2>&1 &
SSH_BRIDGE_PID=$!
echo "Started ssh_bridge (PID: $SSH_BRIDGE_PID)"

sleep 3

echo ""
echo "=== Verifying services ==="
ps aux | grep -E "offline_server|ssh_bridge" | grep -v grep

echo ""
echo "=== Checking ports ==="
netstat -tlnp 2>/dev/null | grep -E "8769|8765" || ss -tlnp 2>/dev/null | grep -E "8769|8765"

echo ""
echo "=== Service status ==="
if ps -p $OFFLINE_PID > /dev/null 2>&1; then
    echo "✓ offline_server is running (port 8769)"
else
    echo "✗ offline_server failed to start"
fi

if ps -p $SSH_BRIDGE_PID > /dev/null 2>&1; then
    echo "✓ ssh_bridge is running (port 8765)"
else
    echo "✗ ssh_bridge failed to start"
fi

echo ""
echo "=== Log files ==="
echo "  offline_server: /tmp/offline_server.log"
echo "  ssh_bridge: /tmp/ssh_bridge.log"
echo ""
echo "To view logs:"
echo "  tail -f /tmp/offline_server.log"
echo "  tail -f /tmp/ssh_bridge.log"
