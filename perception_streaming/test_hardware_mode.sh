#!/bin/bash

# 测试硬件模式配置脚本

echo "=========================================="
echo "测试 offline_perception_debug_432 硬件模式"
echo "=========================================="

# 创建临时测试目录
TEST_DIR="/tmp/perception_test"
mkdir -p "$TEST_DIR"

echo ""
echo "1. 测试 K100 模式 + Mode 6 (Sub)"
echo "----------------------------------------"
OFFLINE_INPUT_DIR="$TEST_DIR" \
OFFLINE_INFER_MODE=6 \
HARDWARE_MODE=K100 \
./bin/offline_perception_debug_432 2>&1 | grep -E "Hardware mode|Inference mode|K100 mode"

echo ""
echo "2. 测试 K100 模式 + Mode 7 (DSG)"
echo "----------------------------------------"
OFFLINE_INPUT_DIR="$TEST_DIR" \
OFFLINE_INFER_MODE=7 \
HARDWARE_MODE=K100 \
./bin/offline_perception_debug_432 2>&1 | grep -E "Hardware mode|Inference mode|K100 mode"

echo ""
echo "3. 测试 bestmow 模式 + Mode 6 (Sub)"
echo "----------------------------------------"
OFFLINE_INPUT_DIR="$TEST_DIR" \
OFFLINE_INFER_MODE=6 \
HARDWARE_MODE=bestmow \
./bin/offline_perception_debug_432 2>&1 | grep -E "Hardware mode|Inference mode|bestmow mode"

echo ""
echo "4. 测试 bestmow 模式 + Mode 7 (DSG)"
echo "----------------------------------------"
OFFLINE_INPUT_DIR="$TEST_DIR" \
OFFLINE_INFER_MODE=7 \
HARDWARE_MODE=bestmow \
./bin/offline_perception_debug_432 2>&1 | grep -E "Hardware mode|Inference mode|bestmow mode"

echo ""
echo "5. 测试默认模式（无环境变量）"
echo "----------------------------------------"
OFFLINE_INPUT_DIR="$TEST_DIR" \
./bin/offline_perception_debug_432 2>&1 | grep -E "Hardware mode|Inference mode|K100 mode|bestmow mode"

echo ""
echo "=========================================="
echo "测试完成！"
echo "=========================================="

# 清理
rm -rf "$TEST_DIR"
