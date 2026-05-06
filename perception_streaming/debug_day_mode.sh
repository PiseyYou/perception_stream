#!/bin/bash
# 诊断白天离线debug问题的脚本

echo "=== 诊断白天离线debug问题 ==="
echo ""

# 1. 检查输入目录
INPUT_DIR="data/stereo_debug/0016/20260420"
echo "1. 检查输入目录: $INPUT_DIR"
if [ -d "$INPUT_DIR" ]; then
    echo "   ✓ 目录存在"
    echo "   文件数量: $(find "$INPUT_DIR" -maxdepth 1 -type f -name "*.jpg" -o -name "*.pcd" | wc -l)"
else
    echo "   ✗ 目录不存在"
    exit 1
fi
echo ""

# 2. 检查 Docker 镜像
echo "2. 检查 Docker 镜像"
if docker images | grep -q "perception-runtime.*latest"; then
    echo "   ✓ Docker 镜像存在"
else
    echo "   ✗ Docker 镜像不存在"
    exit 1
fi
echo ""

# 3. 检查后端服务
echo "3. 检查后端服务"
if ps aux | grep -q "[o]ffline_server.py"; then
    echo "   ✓ 后端服务运行中"
    PID=$(ps aux | grep "[o]ffline_server.py" | awk '{print $2}')
    echo "   PID: $PID"
else
    echo "   ✗ 后端服务未运行"
    exit 1
fi
echo ""

# 4. 测试后端 API
echo "4. 测试后端 API"
RESPONSE=$(curl -s -X POST http://localhost:8769/offline/run \
    -H "Content-Type: application/json" \
    -d "{\"input_dir\":\"$INPUT_DIR\",\"infer_mode\":6,\"erode_pixel\":205,\"resume\":false}")
echo "   响应: $RESPONSE"
echo ""

# 5. 等待并检查容器状态
echo "5. 等待5秒并检查容器状态"
sleep 5
if docker ps | grep -q "perception_offline_runner"; then
    echo "   ✓ 容器正在运行"
    docker logs perception_offline_runner 2>&1 | tail -20
else
    echo "   ✗ 容器未运行（可能已完成或崩溃）"
fi
echo ""

# 6. 检查输出目录
echo "6. 检查输出目录"
OUTPUT_DIR="$INPUT_DIR/sub_6_205_432"
if [ -d "$OUTPUT_DIR" ]; then
    echo "   ✓ 输出目录存在: $OUTPUT_DIR"
    echo "   子目录:"
    ls -lh "$OUTPUT_DIR" | grep "^d"
else
    echo "   ✗ 输出目录不存在"
fi
echo ""

echo "=== 诊断完成 ==="
