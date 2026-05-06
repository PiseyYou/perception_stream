#!/bin/bash

# 离线测试工具编译脚本

set -e  # 遇到错误立即退出

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${PROJECT_DIR}/build"

echo "========================================="
echo "  Stereo Perception Offline Test Tool"
echo "  Build Script"
echo "========================================="

# 清理旧的构建目录（可选）
if [ "$1" == "clean" ]; then
    echo "[Clean] Removing old build directory..."
    rm -rf "${BUILD_DIR}"
fi

# 创建构建目录
mkdir -p "${BUILD_DIR}"
cd "${BUILD_DIR}"

# CMake 配置
echo ""
echo "[CMake] Configuring project..."
cmake ..

# 编译
echo ""
echo "[Make] Building project..."
make -j$(nproc)

# 检查编译结果
if [ -f "${BUILD_DIR}/offline_test_main" ]; then
    echo ""
    echo "========================================="
    echo "  Build completed successfully!"
    echo "========================================="
    echo "Executable: ${BUILD_DIR}/offline_test_main"
    echo ""
    echo "Usage:"
    echo "  cd ${BUILD_DIR}"
    echo "  ./offline_test_main <input_dir> <output_dir> [infer_mode] [hardware_mode]"
    echo ""
    echo "Example:"
    echo "  ./offline_test_main /path/to/images ./output 7 k100"
    echo "  ./offline_test_main /path/to/images ./output 6 bestmow"
    echo "========================================="
else
    echo ""
    echo "[Error] Build failed - executable not found"
    exit 1
fi
