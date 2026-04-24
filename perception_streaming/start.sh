#!/bin/bash
# 启动脚本 - 避免文件监视问题

# 清理残留进程
pkill -f "vite|offline_server|ssh_bridge|pcl_proxy" 2>/dev/null
sleep 1

# 增加文件描述符限制
ulimit -n 65536

# 禁用文件监视
export CHOKIDAR_USEPOLLING=false
export VITE_CJS_IGNORE_WARNING=true

echo "Starting Vite dev server..."
npm run dev
