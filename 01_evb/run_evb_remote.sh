#!/bin/bash

# Docker 环境启动脚本 - 远程服务器版本
# 目标服务器: 192.168.55.247
# 用户: server
# 代码路径: 01_evb
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 设置路径变量
export ai_toolchain_package_path="${PROJECT_ROOT}/01_evb/evb_test"
export dataset_path="${PROJECT_ROOT}/01_evb/data"
export offline_debug="${PROJECT_ROOT}/01_evb/project"

# 启动 Docker 容器
docker run --cap-add=NET_ADMIN -it --rm \
  -v "$ai_toolchain_package_path":/open_explorer \
  -v "$dataset_path":/data \
  -v "$offline_debug":/offline_debug \
  evb_x5_system:v1.6 /bin/bash
