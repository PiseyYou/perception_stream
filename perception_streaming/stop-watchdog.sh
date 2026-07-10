#!/bin/bash
# 停止看门狗脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WATCHDOG_SCRIPT="$SCRIPT_DIR/watchdog.sh"
PID_FILE="/tmp/vite-watchdog.pid"

stop_pid() {
    local pid="$1"
    [ -n "$pid" ] || return 1
    if ps -p "$pid" -o args= 2>/dev/null | grep -F -- "$WATCHDOG_SCRIPT" >/dev/null; then
        kill "$pid"
        echo "看门狗已停止 (PID: $pid)"
        return 0
    fi
    return 1
}

STOPPED=0

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if stop_pid "$PID"; then
        STOPPED=1
    else
        echo "看门狗进程不存在或PID文件已过期 (PID: $PID)"
    fi
fi

for PID in $(pgrep -f "/bin/bash $WATCHDOG_SCRIPT" || true); do
    if stop_pid "$PID"; then
        STOPPED=1
    fi
done

rm -f "$PID_FILE"

if [ "$STOPPED" -eq 0 ]; then
    echo "看门狗未运行"
fi

# 同时停止Vite服务器
pkill -f "vite" 2>/dev/null && echo "Vite服务器已停止"
