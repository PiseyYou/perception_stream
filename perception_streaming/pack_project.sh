#!/bin/bash
# 项目打包脚本 - 准备迁移到其他机器

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PACKAGE_NAME="perception_streaming_${TIMESTAMP}.tar.gz"

echo "=========================================="
echo "项目打包脚本"
echo "=========================================="
echo ""
echo "项目根目录: $PROJECT_ROOT"
echo "打包文件名: $PACKAGE_NAME"
echo ""

# 检查必要的文件和目录
echo "1. 检查必要文件..."
REQUIRED_ITEMS=(
    "bin/offline_perception_debug_432"
    "lib/dnn_x86/libdnn.so"
    "models/dsg_multi_20260407_640x384.bin"
    "night_offline_debug/build/run_cdt_dsg_fusion_dir"
    "data/conf/bestmow_rsa_202604"
    "data/conf/ssh_config.json"
    "robot_monitor/offline_server.py"
    "robot_monitor/ssh_bridge.py"
    "vite.config.ts"
    "package.json"
)

MISSING=0
for item in "${REQUIRED_ITEMS[@]}"; do
    if [ -e "$item" ]; then
        echo "  ✓ $item"
    else
        echo "  ✗ $item (缺失)"
        MISSING=$((MISSING + 1))
    fi
done

if [ $MISSING -gt 0 ]; then
    echo ""
    echo "错误: 有 $MISSING 个必要文件缺失，无法打包"
    exit 1
fi

echo ""
echo "2. 检查硬编码路径..."
HARDCODED=$(find . -type f \( -name "*.py" -o -name "*.ts" -o -name "*.json" \) \
    ! -path "*/node_modules/*" \
    ! -path "*/.git/*" \
    ! -path "*/dist/*" \
    ! -path "*/.claude/*" \
    ! -path "*/cmake-build-debug/*" \
    ! -name "*MIGRATION*.md" \
    ! -name "*DEPLOYMENT*.md" \
    ! -name "*REPORT*.md" \
    -exec grep -l "CLionProjects\|anaconda3\|\.nvm" {} \; 2>/dev/null | wc -l)

if [ "$HARDCODED" -gt 0 ]; then
    echo "  ⚠ 警告: 发现 $HARDCODED 个文件仍包含硬编码路径（可能是测试脚本）"
    find . -type f \( -name "*.py" -o -name "*.ts" -o -name "*.json" \) \
        ! -path "*/node_modules/*" \
        ! -path "*/.git/*" \
        ! -path "*/dist/*" \
        ! -path "*/.claude/*" \
        ! -path "*/cmake-build-debug/*" \
        ! -name "*MIGRATION*.md" \
        ! -name "*DEPLOYMENT*.md" \
        ! -name "*REPORT*.md" \
        -exec grep -l "CLionProjects\|anaconda3\|\.nvm" {} \; 2>/dev/null | sed 's/^/    /'
else
    echo "  ✓ 核心文件无硬编码路径"
fi

echo ""
echo "3. 计算项目大小..."
TOTAL_SIZE=$(du -sh . 2>/dev/null | cut -f1)
echo "  当前项目大小: $TOTAL_SIZE"

echo ""
echo "4. 开始打包..."
cd "$PROJECT_ROOT/.."
tar -czf "$PACKAGE_NAME" \
    --exclude='node_modules' \
    --exclude='.git' \
    --exclude='dist' \
    --exclude='data/bag_debug' \
    --exclude='data/log_debug' \
    --exclude='data/stereo_debug' \
    --exclude='data/visualization' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.log' \
    --exclude='cmake-build-debug' \
    --exclude='.claude' \
    --exclude='*.tar.gz' \
    "$(basename "$PROJECT_ROOT")"

PACKAGE_SIZE=$(du -h "$PACKAGE_NAME" | cut -f1)
PACKAGE_PATH="$(pwd)/$PACKAGE_NAME"

echo ""
echo "=========================================="
echo "打包完成！"
echo "=========================================="
echo ""
echo "打包文件: $PACKAGE_PATH"
echo "文件大小: $PACKAGE_SIZE"
echo ""
echo "下一步："
echo "1. 将 $PACKAGE_NAME 上传到目标机器"
echo "2. 解压: tar -xzf $PACKAGE_NAME"
echo "3. 进入目录: cd $(basename "$PROJECT_ROOT")"
echo "4. 安装依赖: pip3 install paramiko websockets Pillow && npm install"
echo "5. 配置SSH: 编辑 data/conf/ssh_config.json"
echo "6. 启动服务: ./start.sh"
echo ""
