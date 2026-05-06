#!/bin/bash

# 模拟Web界面调用offline_perception_debug_432的测试脚本

echo "=========================================="
echo "模拟Web界面调用测试"
echo "=========================================="

# 创建测试目录和测试图像
TEST_DIR="/tmp/web_test"
mkdir -p "$TEST_DIR"

# 创建一个简单的测试图像（如果没有的话）
if [ ! -f "$TEST_DIR/test.jpg" ]; then
    echo "创建测试图像..."
    # 使用ImageMagick创建一个简单的测试图像
    convert -size 1280x480 xc:gray "$TEST_DIR/test.jpg" 2>/dev/null || {
        echo "警告：无法创建测试图像，跳过图像处理测试"
    }
fi

echo ""
echo "1. 模拟白天离线debug（Mode 6 + K100）"
echo "----------------------------------------"
OFFLINE_INPUT_DIR="$TEST_DIR" \
OFFLINE_INFER_MODE=6 \
OFFLINE_ERODE_PIXEL=205 \
HARDWARE_MODE=K100 \
./bin/offline_perception_debug_432 2>&1 | grep -E "Hardware mode|Inference mode|Configuration|Found.*image"

echo ""
echo "2. 模拟夜间离线debug（Mode 7 + K100）"
echo "----------------------------------------"
OFFLINE_INPUT_DIR="$TEST_DIR" \
OFFLINE_INFER_MODE=7 \
OFFLINE_ERODE_PIXEL=205 \
HARDWARE_MODE=K100 \
DSG_MODEL_PATH=../models/dsg_multi_20260407_640x384.bin \
./bin/offline_perception_debug_432 2>&1 | grep -E "Hardware mode|Inference mode|Configuration|Found.*image"

echo ""
echo "3. 模拟bestmow模式（Mode 6 + bestmow）"
echo "----------------------------------------"
OFFLINE_INPUT_DIR="$TEST_DIR" \
OFFLINE_INFER_MODE=6 \
OFFLINE_ERODE_PIXEL=205 \
HARDWARE_MODE=bestmow \
./bin/offline_perception_debug_432 2>&1 | grep -E "Hardware mode|Inference mode|Configuration|Found.*image"

echo ""
echo "=========================================="
echo "测试完成！"
echo "=========================================="
echo ""
echo "检查输出目录："
ls -la "$TEST_DIR" 2>/dev/null | grep -E "sub_|dsg_|pcd_" || echo "（无输出目录，可能因为没有有效图像）"

echo ""
echo "清理测试目录..."
rm -rf "$TEST_DIR"
echo "完成！"
