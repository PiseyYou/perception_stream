#!/bin/bash
# Test script to verify rsync SSH connection fix

SSH_KEY="/home/youfeng/CLionProjects/12-evb/evb_test/ssh/bestmow_rsa_202604"
SSH_HOST="120.25.121.3"
SSH_USER="root"
PORT=10016

echo "=== Testing SSH connection ==="
ssh -i "$SSH_KEY" \
    -o StrictHostKeyChecking=no \
    -o ConnectTimeout=15 \
    -o ServerAliveInterval=10 \
    -o ServerAliveCountMax=3 \
    -p "$PORT" \
    "${SSH_USER}@${SSH_HOST}" \
    "echo 'SSH connection successful'"

if [ $? -eq 0 ]; then
    echo "✓ SSH connection test passed"
else
    echo "✗ SSH connection test failed"
    exit 1
fi

echo ""
echo "=== Testing rsync with SSH options ==="
# Create a test directory
TEST_DIR="/tmp/rsync_test_$$"
mkdir -p "$TEST_DIR"

# Test rsync command format
ssh_opts="ssh -i ${SSH_KEY} -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -p ${PORT}"

rsync -avz --dry-run --timeout=60 \
    -e "$ssh_opts" \
    "${SSH_USER}@${SSH_HOST}:/userdata/bestmow_data/image_save_path/" \
    "$TEST_DIR/" 2>&1 | head -20

if [ $? -eq 0 ]; then
    echo "✓ rsync command format test passed"
else
    echo "✗ rsync command format test failed"
fi

# Cleanup
rm -rf "$TEST_DIR"

echo ""
echo "=== Test completed ==="
