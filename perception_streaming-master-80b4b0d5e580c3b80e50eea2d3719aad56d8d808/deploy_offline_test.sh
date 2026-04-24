#!/bin/bash
# 离线测试环境部署脚本

PROJECT_ROOT="/home/youfeng/CLionProjects/07_openclaw_auto/project/perception_streaming-master-80b4b0d5e580c3b80e50eea2d3719aad56d8d808"

cd "$PROJECT_ROOT" || exit 1

echo "=========================================="
echo "离线测试环境部署脚本"
echo "=========================================="
echo ""

# 创建目录
echo "1. 创建目录结构..."
mkdir -p bin lib/dnn_x86 models

# 复制可执行文件
echo ""
echo "2. 复制可执行文件..."

if [ -f "/home/youfeng/CLionProjects/07_openclaw_auto/claude_project/offline_perception_debug/build/offline_perception_debug_432" ]; then
    cp /home/youfeng/CLionProjects/07_openclaw_auto/claude_project/offline_perception_debug/build/offline_perception_debug_432 \
       bin/offline_perception_debug_432
    chmod +x bin/offline_perception_debug_432
    echo "  ✓ offline_perception_debug_432"
else
    echo "  ✗ offline_perception_debug_432 源文件不存在"
fi

if [ -f "/home/youfeng/CLionProjects/05-offline_debug_fusion/offline_perception_debug/cmake-build-debug/dsg_mono_perception" ]; then
    cp /home/youfeng/CLionProjects/05-offline_debug_fusion/offline_perception_debug/cmake-build-debug/dsg_mono_perception \
       bin/dsg_mono_perception
    chmod +x bin/dsg_mono_perception
    echo "  ✓ dsg_mono_perception"
else
    echo "  ✗ dsg_mono_perception 源文件不存在"
fi

# 复制依赖库
echo ""
echo "3. 复制依赖库..."
if [ -d "/home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/lib" ]; then
    cp -r /home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/lib/* \
       lib/dnn_x86/
    lib_count=$(ls lib/dnn_x86/ | wc -l)
    echo "  ✓ 复制了 $lib_count 个库文件"
else
    echo "  ✗ 依赖库目录不存在"
fi

# 复制模型文件
echo ""
echo "4. 复制模型文件..."
if [ -f "/home/youfeng/CLionProjects/05-offline_debug_fusion/offline_perception_debug/models/dsg_multi_20260407_640x384.bin" ]; then
    cp /home/youfeng/CLionProjects/05-offline_debug_fusion/offline_perception_debug/models/dsg_multi_20260407_640x384.bin \
       models/dsg_multi_20260407_640x384.bin
    echo "  ✓ dsg_multi_20260407_640x384.bin"
else
    echo "  ✗ dsg_multi_20260407_640x384.bin 不存在"
fi

if [ -f "/home/youfeng/CLionProjects/06_claude_debug/02_debug/offline_perception_debug/models/cdt_20251125_640x384.bin" ]; then
    cp /home/youfeng/CLionProjects/06_claude_debug/02_debug/offline_perception_debug/models/cdt_20251125_640x384.bin \
       models/cdt_20251125_640x384.bin
    echo "  ✓ cdt_20251125_640x384.bin"
else
    echo "  ✗ cdt_20251125_640x384.bin 不存在"
fi

if [ -f "/home/youfeng/CLionProjects/06_claude_debug/02_debug/offline_perception_debug/models/dsg_20260211_640x384.bin" ]; then
    cp /home/youfeng/CLionProjects/06_claude_debug/02_debug/offline_perception_debug/models/dsg_20260211_640x384.bin \
       models/dsg_20260211_640x384.bin
    echo "  ✓ dsg_20260211_640x384.bin"
else
    echo "  ✗ dsg_20260211_640x384.bin 不存在"
fi

# 验证部署
echo ""
echo "=========================================="
echo "部署验证"
echo "=========================================="
echo ""

echo "可执行文件："
if [ -f "bin/offline_perception_debug_432" ]; then
    ls -lh bin/offline_perception_debug_432
else
    echo "  ✗ bin/offline_perception_debug_432 不存在"
fi

if [ -f "bin/dsg_mono_perception" ]; then
    ls -lh bin/dsg_mono_perception
else
    echo "  ✗ bin/dsg_mono_perception 不存在"
fi

echo ""
echo "依赖库："
if [ -d "lib/dnn_x86" ]; then
    lib_count=$(ls lib/dnn_x86/ | wc -l)
    echo "  lib/dnn_x86/ 包含 $lib_count 个文件"
    ls lib/dnn_x86/ | head -5
    if [ $lib_count -gt 5 ]; then
        echo "  ... (还有 $((lib_count - 5)) 个文件)"
    fi
else
    echo "  ✗ lib/dnn_x86/ 不存在"
fi

echo ""
echo "模型文件："
if [ -f "models/dsg_multi_20260407_640x384.bin" ]; then
    ls -lh models/dsg_multi_20260407_640x384.bin
else
    echo "  ✗ models/dsg_multi_20260407_640x384.bin 不存在"
fi

echo ""
echo "=========================================="
echo "部署完成！"
echo "=========================================="
