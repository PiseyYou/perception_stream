#!/bin/bash
# Test script to verify SFTP upload fix

SSH_KEY="/home/youfeng/CLionProjects/12-evb/evb_test/ssh/bestmow_rsa_202604"
SSH_HOST="120.25.121.3"
SSH_USER="root"
PORT=10016

echo "=== Testing SFTP connection and upload ==="

# Create a test file
TEST_FILE="/tmp/test_upload_$$.txt"
echo "Test content $(date)" > "$TEST_FILE"

# Test SFTP upload using Python paramiko
python3 << 'EOF'
import paramiko
import sys
import time

SSH_KEY = "/home/youfeng/CLionProjects/12-evb/evb_test/ssh/bestmow_rsa_202604"
SSH_HOST = "120.25.121.3"
SSH_USER = "root"
PORT = 10016
TEST_FILE = "/tmp/test_upload_$$.txt"
REMOTE_FILE = "/tmp/test_upload_remote.txt"

max_retries = 3
for attempt in range(max_retries):
    try:
        if attempt > 0:
            print(f"Retry {attempt}/{max_retries}")
            time.sleep(2)

        print(f"Attempt {attempt + 1}: Connecting to {SSH_HOST}:{PORT}...")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey = paramiko.RSAKey.from_private_key_file(SSH_KEY)

        client.connect(
            SSH_HOST, port=PORT,
            username=SSH_USER, pkey=pkey,
            timeout=30, banner_timeout=60, auth_timeout=30,
            look_for_keys=False, allow_agent=False,
        )

        # Set keepalive
        transport = client.get_transport()
        if transport:
            transport.set_keepalive(10)

        print("Connected! Opening SFTP...")
        sftp = client.open_sftp()

        # Create test file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write(f"Test content from Python at {time.time()}\n")
            test_file = f.name

        print(f"Uploading {test_file} to {REMOTE_FILE}...")
        sftp.put(test_file, REMOTE_FILE)

        print("Upload successful!")

        # Verify file exists
        try:
            stat = sftp.stat(REMOTE_FILE)
            print(f"✓ Remote file exists, size: {stat.st_size} bytes")
        except:
            print("✗ Remote file not found")

        sftp.close()
        client.close()

        import os
        os.unlink(test_file)

        print("✓ SFTP upload test passed")
        sys.exit(0)

    except Exception as e:
        print(f"✗ Attempt {attempt + 1} failed: {e}")
        if attempt >= max_retries - 1:
            print("✗ SFTP upload test failed after all retries")
            sys.exit(1)

EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "=== All tests passed ==="
else
    echo ""
    echo "=== Tests failed ==="
    exit 1
fi
