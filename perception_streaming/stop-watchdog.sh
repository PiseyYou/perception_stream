#!/bin/bash
# 停止看门狗脚本

PID_FILE="/tmp/vite-watchdog.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "看门狗未运行"
    exit 0
fi

PID=$(cat "$PID_FILE")

if ps -p "$PID" > /dev/null 2>&1; then
    kill "$PID"
    echo "看门狗已停止 (PID: $PID)"
    rm -f "$PID_FILE"
else
    echo "看门狗进程不存在 (PID: $PID)"
    rm -f "$PID_FILE"
fi

# 同时停止Vite服务器
pkill -f "vite" 2>/dev/null && echo "Vite服务器已停止"
