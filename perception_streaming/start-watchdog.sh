#!/bin/bash
# 启动看门狗脚本（后台运行）

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WATCHDOG_SCRIPT="$SCRIPT_DIR/watchdog.sh"
PID_FILE="/tmp/vite-watchdog.pid"

# 检查是否已经在运行
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "看门狗已在运行 (PID: $OLD_PID)"
        exit 0
    fi
fi

# 启动看门狗
nohup "$WATCHDOG_SCRIPT" > /dev/null 2>&1 &
NEW_PID=$!
echo $NEW_PID > "$PID_FILE"

echo "看门狗已启动 (PID: $NEW_PID)"
echo "日志文件: /tmp/vite-watchdog.log"
echo "停止命令: kill $NEW_PID"
