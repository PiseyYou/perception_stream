#!/bin/bash
# 在Docker容器内编译offline_test_main

set -e

echo "=========================================="
echo "在Docker容器内编译offline_test_main"
echo "=========================================="

# 创建临时构建容器
docker run --rm \
  -v "$(pwd)/stereo_perception_multi2_offline_test:/build" \
  -v "$(pwd)/offline_perception_debug_src:/offline_perception_debug_src" \
  -v "$(pwd)/lib:/lib_host" \
  -v "$(pwd)/models:/models" \
  -w /build \
  perception-runtime:latest \
  bash -c "
    set -e
    echo '安装编译工具...'
    apt-get update && apt-get install -y cmake g++ make

    echo '清理旧的构建文件...'
    rm -rf build
    mkdir -p build
    cd build

    echo '运行CMake配置...'
    cmake ..

    echo '开始编译...'
    make -j\$(nproc)

    echo '检查编译结果...'
    ls -lh offline_test_main
    ldd offline_test_main || true

    echo '编译完成！'
  "

echo ""
echo "=========================================="
echo "编译完成，复制到bin目录..."
echo "=========================================="

cp stereo_perception_multi2_offline_test/build/offline_test_main bin/
chmod +x bin/offline_test_main

echo "完成！"
