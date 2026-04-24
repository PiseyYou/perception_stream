#!/bin/bash
# monitor_avoiding.sh
# 监控 robot_decision_*.log 最新日志，一旦出现 AVOIDING 字段立即执行 service call
# 冷却机制：触发后 10 秒内不重复执行（默认关闭，touch /tmp/avoiding_cooldown_enable 开启）

# Source ROS2 环境（自动检测版本）
for setup in /opt/ros/*/setup.bash; do
    # shellcheck source=/dev/null
    source "$setup" 2>/dev/null && break
done
# Source 业务 workspace（含 general_msgs 等自定义消息）
# shellcheck source=/dev/null
source /app/BestMow/install/setup.bash 2>/dev/null

COOLDOWN=10
last_trigger_time=0
COOLDOWN_SWITCH_FILE="/tmp/avoiding_cooldown_enable"

log() {
    echo "[$(date '+%Y/%m/%d %H:%M:%S')] $*"
}

trigger_service() {
    local reason="$1"
    local now
    now=$(date +%s)
    local elapsed=$(( now - last_trigger_time ))

    if [[ ! -f "$COOLDOWN_SWITCH_FILE" ]] || (( elapsed >= COOLDOWN )); then
        log ">>> 触发原因: $reason，执行 service call..."
        if timeout 5s ros2 service call /perception_node/handle_server \
            general_msgs/srv/PerceptionPattern \
            "{mode: 100, filename: \"auto\"}" 2>&1; then
            log ">>> service call 完成"
        else
            local exit_code=$?
            if [ $exit_code -eq 124 ]; then
                log ">>> service call 超时（5秒）"
            else
                log ">>> service call 失败（退出码: $exit_code）"
            fi
        fi
        last_trigger_time=$now
    else
        local remaining=$(( COOLDOWN - elapsed ))
        log "检测到 AVOIDING，冷却中，还需 ${remaining}s"
    fi
}

process_line() {
    local line="$1"
    if [[ "$line" == *"AVOIDING"* ]]; then
        trigger_service "AVOIDING"
    fi
}

# ── 查找最新 robot_decision_*.log ──────────────────────────────────────────
find_robot_decision_log() {
    local log_dir="/userdata/log_dir/ros2_log"
    if [[ ! -d "$log_dir" ]]; then
        log "错误: 日志目录 $log_dir 不存在"
        return 1
    fi
    find "$log_dir" -type f -name "robot_decision_*.log" -printf '%T@ %p\n' 2>/dev/null \
        | sort -rn \
        | head -n 1 \
        | awk '{print $2}'
}

# ── 主逻辑 ─────────────────────────────────────────────────────────────────
FIXED_FILE="${1:-}"

if [[ -f "$COOLDOWN_SWITCH_FILE" ]]; then
    log "冷却机制: 已启用（${COOLDOWN}s），开关文件: $COOLDOWN_SWITCH_FILE"
else
    log "冷却机制: 已禁用（每次 AVOIDING 均触发），开关文件: $COOLDOWN_SWITCH_FILE"
fi

# 固定文件模式：直接跟踪指定文件，不切换
if [[ -n "$FIXED_FILE" ]]; then
    log "开始监控日志文件（固定）: $FIXED_FILE"
    while IFS= read -r line; do
        echo "$line"
        process_line "$line"
    done < <(tail -n 0 -F "$FIXED_FILE")
    exit 0
fi

# 自动模式：轮询追踪最新日志文件，自动处理文件轮转和切换
CURRENT_FILE=""
OFFSET=0
CHECK_INTERVAL=5
last_check=0

# 等待第一个日志文件出现
while true; do
    LATEST=$(find_robot_decision_log)
    if [[ -n "$LATEST" ]]; then
        break
    fi
    log "未找到 robot_decision_*.log，等待中..."
    sleep 5
done

CURRENT_FILE="$LATEST"
OFFSET=$(wc -l < "$CURRENT_FILE" 2>/dev/null || echo 0)
log "开始监控日志文件: $CURRENT_FILE (跳过已有 $OFFSET 行)"

# 主循环：每秒读取新行，自动处理轮转和文件切换
while true; do
    if [[ -f "$CURRENT_FILE" ]]; then
        TOTAL=$(wc -l < "$CURRENT_FILE" 2>/dev/null || echo 0)

        if (( TOTAL < OFFSET )); then
            log "检测到文件轮转（行数从 $OFFSET 降至 $TOTAL），重置偏移"
            OFFSET=0
        fi

        if (( TOTAL > OFFSET )); then
            while IFS= read -r line; do
                echo "$line"
                process_line "$line"
            done < <(tail -n +$((OFFSET + 1)) "$CURRENT_FILE" 2>/dev/null)
            OFFSET=$TOTAL
        fi
    fi

    now=$(date +%s)
    if (( now - last_check >= CHECK_INTERVAL )); then
        last_check=$now
        LATEST=$(find_robot_decision_log)
        if [[ -n "$LATEST" && "$LATEST" != "$CURRENT_FILE" ]]; then
            log "切换监控日志文件: $LATEST"
            CURRENT_FILE="$LATEST"
            OFFSET=$(wc -l < "$CURRENT_FILE" 2>/dev/null || echo 0)
            log "跳过已有 $OFFSET 行，监控新增内容"
        fi
    fi

    sleep 1
done
