#!/bin/bash
# Test script to verify SCP upload fix

SSH_KEY="/home/youfeng/CLionProjects/12-evb/evb_test/ssh/bestmow_rsa_202604"
SSH_HOST="120.25.121.3"
SSH_USER="root"
PORT=10016

echo "=== Testing SCP upload (alternative to SFTP) ==="

# Create test files
TEST_SCRIPT="/tmp/test_script_$$.sh"
TEST_SERVICE="/tmp/test_service_$$.service"

cat > "$TEST_SCRIPT" << 'SCRIPT_EOF'
#!/bin/bash
echo "Test script $(date)"
SCRIPT_EOF

cat > "$TEST_SERVICE" << 'SERVICE_EOF'
[Unit]
Description=Test Service
After=network.target

[Service]
Type=simple
ExecStart=/bin/bash /tmp/test_script.sh

[Install]
WantedBy=multi-user.target
SERVICE_EOF

echo "Created test files:"
echo "  - $TEST_SCRIPT"
echo "  - $TEST_SERVICE"

# Test 1: Create remote directory
echo ""
echo "Test 1: Creating remote directory..."
ssh -i "$SSH_KEY" \
    -o StrictHostKeyChecking=no \
    -o ConnectTimeout=30 \
    -o ServerAliveInterval=10 \
    -o ServerAliveCountMax=3 \
    -p "$PORT" \
    "${SSH_USER}@${SSH_HOST}" \
    "mkdir -p /tmp/test_upload_dir"

if [ $? -eq 0 ]; then
    echo "✓ Remote directory created"
else
    echo "✗ Failed to create remote directory"
    exit 1
fi

# Test 2: Upload script file
echo ""
echo "Test 2: Uploading script file..."
scp -i "$SSH_KEY" \
    -o StrictHostKeyChecking=no \
    -o ConnectTimeout=30 \
    -o ServerAliveInterval=10 \
    -o ServerAliveCountMax=3 \
    -P "$PORT" \
    "$TEST_SCRIPT" \
    "${SSH_USER}@${SSH_HOST}:/tmp/test_upload_dir/test_script.sh"

if [ $? -eq 0 ]; then
    echo "✓ Script file uploaded"
else
    echo "✗ Failed to upload script file"
    exit 1
fi

# Test 3: Set executable permission
echo ""
echo "Test 3: Setting executable permission..."
ssh -i "$SSH_KEY" \
    -o StrictHostKeyChecking=no \
    -o ConnectTimeout=30 \
    -p "$PORT" \
    "${SSH_USER}@${SSH_HOST}" \
    "chmod 755 /tmp/test_upload_dir/test_script.sh"

if [ $? -eq 0 ]; then
    echo "✓ Permission set"
else
    echo "✗ Failed to set permission"
    exit 1
fi

# Test 4: Upload service file
echo ""
echo "Test 4: Uploading service file..."
scp -i "$SSH_KEY" \
    -o StrictHostKeyChecking=no \
    -o ConnectTimeout=30 \
    -o ServerAliveInterval=10 \
    -o ServerAliveCountMax=3 \
    -P "$PORT" \
    "$TEST_SERVICE" \
    "${SSH_USER}@${SSH_HOST}:/tmp/test_upload_dir/test.service"

if [ $? -eq 0 ]; then
    echo "✓ Service file uploaded"
else
    echo "✗ Failed to upload service file"
    exit 1
fi

# Test 5: Verify files exist
echo ""
echo "Test 5: Verifying uploaded files..."
ssh -i "$SSH_KEY" \
    -o StrictHostKeyChecking=no \
    -o ConnectTimeout=30 \
    -p "$PORT" \
    "${SSH_USER}@${SSH_HOST}" \
    "ls -lh /tmp/test_upload_dir/"

if [ $? -eq 0 ]; then
    echo "✓ Files verified"
else
    echo "✗ Failed to verify files"
    exit 1
fi

# Cleanup
rm -f "$TEST_SCRIPT" "$TEST_SERVICE"

echo ""
echo "=== All SCP upload tests passed ==="
echo ""
echo "Summary:"
echo "  ✓ Remote directory creation"
echo "  ✓ Script file upload"
echo "  ✓ Permission setting"
echo "  ✓ Service file upload"
echo "  ✓ File verification"
echo ""
echo "The SCP-based upload is working correctly!"
