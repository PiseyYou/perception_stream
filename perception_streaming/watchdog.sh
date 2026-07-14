#!/bin/bash
# Vite Dev Server Watchdog
# 监控Vite开发服务器状态，不自动重启运行中的服务

PROJECT_DIR="${PROJECT_DIR:-/media/sda1/perception_process/perception_streaming}"
LOG_FILE="${VITE_WATCHDOG_LOG:-/tmp/vite-watchdog.log}"
VITE_LOG="${VITE_DEV_LOG:-/tmp/vite-dev.log}"
CHECK_INTERVAL="${VITE_WATCHDOG_CHECK_INTERVAL:-10}"  # 检查间隔（秒）
VITE_URL="${VITE_WATCHDOG_URL:-https://127.0.0.1:5173/}"
STARTUP_TIMEOUT="${VITE_WATCHDOG_STARTUP_TIMEOUT:-120}"
STARTUP_CHECK_INTERVAL="${VITE_WATCHDOG_STARTUP_CHECK_INTERVAL:-2}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

check_vite_running() {
    # 检查进程是否存在
    if ! pgrep -f "$PROJECT_DIR/node_modules/.bin/vite" > /dev/null; then
        return 1
    fi

    # 检查端口是否监听
    if command -v ss >/dev/null 2>&1; then
        if ! ss -ltn 2>/dev/null | grep -Eq '(^|[[:space:]])[^[:space:]]*:5173[[:space:]]'; then
            return 1
        fi
    elif ! netstat -tln 2>/dev/null | grep -Eq '(^|[[:space:]])[^[:space:]]*:5173[[:space:]]'; then
        return 1
    fi

    # 检查 HTTPS 响应；开发证书为自签名证书，健康检查允许本机证书。
    http_code=$(curl -k -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "$VITE_URL" 2>/dev/null)
    if [ "$http_code" != "200" ]; then
        return 1
    fi

    return 0
}

start_vite() {
    log "启动Vite开发服务器..."
    cd "$PROJECT_DIR" || exit 1

    # 清理旧进程
    pkill -f "vite" 2>/dev/null
    sleep 2

    # 启动新进程
    npm run dev > "$VITE_LOG" 2>&1 &

    # 等待启动完成。Vite 在当前项目里需要启动多个插件，冷启动常超过 8 秒。
    local waited=0
    while [ "$waited" -lt "$STARTUP_TIMEOUT" ]; do
        if check_vite_running; then
            log "✓ Vite服务器启动成功"
            return 0
        fi
        sleep "$STARTUP_CHECK_INTERVAL"
        waited=$((waited + STARTUP_CHECK_INTERVAL))
    done

    log "✗ Vite服务器启动失败"
    return 1
}

# 主循环
log "========================================="
log "Vite看门狗启动"
log "项目目录: $PROJECT_DIR"
log "检查间隔: ${CHECK_INTERVAL}秒"
log "========================================="

# 首次启动
if ! check_vite_running; then
    log "初始检查：Vite服务未运行"
    start_vite
else
    log "初始检查：Vite服务正常运行"
fi

# 监控循环
while true; do
    sleep $CHECK_INTERVAL

    if ! check_vite_running; then
        log "⚠ 检测到服务不可用；自动重启已禁用"
    fi
done
