#!/bin/bash
# monitor_mow_obstacle.sh
# 同时监控 robot_decision 和 stereo_perception_multi 日志
# 触发条件（两者同时满足）：
#   1. 机器处于割草状态（Work:COVERING 或 Work:MOVING）
#   2. DSG 点云感知到障碍物：back(label=1) > BACK_THRESH 或 stat(label=5) > STAT_THRESH
# 冷却机制：触发后 COOLDOWN 秒内不重复执行（默认开启）
#
# 日志格式参考：
#   robot_decision:         Mode:COVERAGE Work:COVERING Prev work:...
#   stereo_perception_multi: ==========[Dsg]back: 37  road: 3291  stat: 8 ==========

# Source ROS2 环境
for setup in /opt/ros/*/setup.bash; do
    # shellcheck source=/dev/null
    source "$setup" 2>/dev/null && break
done
# shellcheck source=/dev/null
source /app/BestMow/install/setup.bash 2>/dev/null

# ── 可调参数 ────────────────────────────────────────────────────────────────
COOLDOWN=10                   # 触发冷却时间（秒）
# 距离阈值（米）：近于此值的障碍物才触发（需要感知节点输出 near_back/near_stat 字段）
# 设为负数（如 -1）则只用点数阈值，不做距离判断
DIST_THRESH=0.35              # 35cm
# 点数阈值（仅当日志不含距离字段时使用，或距离字段为 -1 时的兜底判断）
BACK_THRESH=200               # label=1 (back) 点数阈值
STAT_THRESH=10                # label=5 (stat) 点数阈值
CHECK_INTERVAL=5              # 检查是否有更新日志文件的间隔（秒）
LOG_DIR="/userdata/log_dir/ros2_log"

# ── 状态变量 ────────────────────────────────────────────────────────────────
is_mowing=0                   # 当前是否处于割草状态
last_trigger_time=0           # 上次触发时间（秒级时间戳）

# ── 日志函数 ────────────────────────────────────────────────────────────────
log() {
    echo "[$(date '+%Y/%m/%d %H:%M:%S')] $*"
}

# ── 执行 service call ───────────────────────────────────────────────────────
trigger_service() {
    local reason="$1"
    local now
    now=$(date +%s)
    local elapsed=$(( now - last_trigger_time ))

    if (( elapsed >= COOLDOWN )); then
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
        log "障碍物触发条件满足（$reason），冷却中，还需 ${remaining}s"
    fi
}

# ── 处理 robot_decision 日志行 ──────────────────────────────────────────────
process_decision_line() {
    local line="$1"

    # 匹配 Work: 状态行
    if [[ "$line" =~ Work:([A-Z_]+) ]]; then
        local work_state="${BASH_REMATCH[1]}"
        case "$work_state" in
            COVERING|MOVING)
                if (( is_mowing == 0 )); then
                    log "[decision] 进入割草状态: Work:$work_state"
                    is_mowing=1
                fi
                ;;
            *)
                if (( is_mowing == 1 )); then
                    log "[decision] 退出割草状态: Work:$work_state"
                    is_mowing=0
                fi
                ;;
        esac
    fi
}

# ── 处理 stereo_perception 日志行 ────────────────────────────────────────────
process_perception_line() {
    local line="$1"

    # 新格式（含距离）：[Dsg]back: X  road: Y  stat: Z  near_back: A.AAm  near_stat: B.BBm
    # 旧格式（不含距离）：[Dsg]back: X  road: Y  stat: Z
    if [[ "$line" != *"[Dsg]"* ]]; then
        return
    fi

    local back_val=0 stat_val=0
    local near_z1=-1 near_z5=-1

    [[ "$line" =~ \[Dsg\]back:[[:space:]]*([0-9]+) ]]         && back_val="${BASH_REMATCH[1]}"
    [[ "$line" =~ stat:[[:space:]]*([0-9]+) ]]                 && stat_val="${BASH_REMATCH[1]}"
    [[ "$line" =~ near_back:[[:space:]]*(-?[0-9]+\.[0-9]+) ]] && near_z1="${BASH_REMATCH[1]}"
    [[ "$line" =~ near_stat:[[:space:]]*(-?[0-9]+\.[0-9]+) ]] && near_z5="${BASH_REMATCH[1]}"

    # ── 距离判断（优先使用距离字段） ─────────────────────────────────────────
    local has_obstacle=0
    local obstacle_reason=""

    # awk 浮点比较：0 < dist <= DIST_THRESH
    dist_ok() {
        local d="$1"
        awk -v d="$d" -v th="$DIST_THRESH" 'BEGIN { exit !(d > 0 && d <= th) }'
    }

    if dist_ok "$near_z1"; then
        has_obstacle=1
        obstacle_reason="near_back=${near_z1}m(label=1)"
    fi
    if dist_ok "$near_z5"; then
        has_obstacle=1
        local r="near_stat=${near_z5}m(label=5)"
        obstacle_reason="${obstacle_reason:+$obstacle_reason,}$r"
    fi

    # ── 兜底：无距离字段时回退到点数阈值 ────────────────────────────────────
    if (( has_obstacle == 0 )) && [[ "$near_z1" == "-1" && "$near_z5" == "-1" ]]; then
        if (( back_val > BACK_THRESH )); then
            has_obstacle=1
            obstacle_reason="back=${back_val}(label=1)"
        fi
        if (( stat_val > STAT_THRESH )); then
            has_obstacle=1
            local r="stat=${stat_val}(label=5)"
            obstacle_reason="${obstacle_reason:+$obstacle_reason,}$r"
        fi
    fi

    if (( has_obstacle )); then
        if (( is_mowing )); then
            trigger_service "割草中+障碍物 [$obstacle_reason]"
        fi
    fi
}

# ── 查找最新 robot_decision_*.log ──────────────────────────────────────────
find_decision_log() {
    if [[ ! -d "$LOG_DIR" ]]; then
        return 1
    fi
    find "$LOG_DIR" -type f -name "robot_decision_*.log" -printf '%T@ %p\n' 2>/dev/null \
        | sort -rn | head -n 1 | awk '{print $2}'
}

# ── 查找最新 stereo_perception_multi_* 日志 ─────────────────────────────────
find_perception_log() {
    if [[ ! -d "$LOG_DIR" ]]; then
        return 1
    fi
    find "$LOG_DIR" -type f -name "stereo_perception_multi_*" ! -name "*.gz" \
        -printf '%T@ %p\n' 2>/dev/null \
        | sort -rn | head -n 1 | awk '{print $2}'
}

# ── 主逻辑 ─────────────────────────────────────────────────────────────────
# 参数：可指定固定文件（两个，分别为 decision 和 perception 日志）
FIXED_DECISION="${1:-}"
FIXED_PERCEPTION="${2:-}"

log "冷却时间: ${COOLDOWN}s"
log "障碍物阈值: back(label=1) > $BACK_THRESH 或 stat(label=5) > $STAT_THRESH"

# ── 固定文件模式 ────────────────────────────────────────────────────────────
if [[ -n "$FIXED_DECISION" && -n "$FIXED_PERCEPTION" ]]; then
    log "固定文件模式"
    log "  decision  : $FIXED_DECISION"
    log "  perception: $FIXED_PERCEPTION"

    # 用 FIFO 合并两路 tail 输出，带前缀区分来源
    FIFO_D=$(mktemp -u)
    FIFO_P=$(mktemp -u)
    mkfifo "$FIFO_D" "$FIFO_P"
    trap 'rm -f "$FIFO_D" "$FIFO_P"' EXIT

    tail -n 0 -F "$FIXED_DECISION"    | sed 's/^/D:/' > "$FIFO_D" &
    tail -n 0 -F "$FIXED_PERCEPTION"  | sed 's/^/P:/' > "$FIFO_P" &

    while IFS= read -r tagged_line; do
        prefix="${tagged_line:0:2}"
        line="${tagged_line:2}"
        echo "$line"
        if [[ "$prefix" == "D:" ]]; then
            process_decision_line "$line"
        else
            process_perception_line "$line"
        fi
    done < <(cat "$FIFO_D" "$FIFO_P")
    exit 0
fi

# ── 自动模式：轮询追踪最新日志，自动处理文件轮转 ──────────────────────────
DECISION_FILE=""
PERCEPTION_FILE=""
DECISION_OFFSET=0
PERCEPTION_OFFSET=0
last_check=0

# 等待日志文件出现
log "等待日志文件..."
while true; do
    [[ -z "$DECISION_FILE" ]] && DECISION_FILE=$(find_decision_log)
    [[ -z "$PERCEPTION_FILE" ]] && PERCEPTION_FILE=$(find_perception_log)
    if [[ -n "$DECISION_FILE" && -n "$PERCEPTION_FILE" ]]; then
        break
    fi
    log "  decision: ${DECISION_FILE:-(未找到)}  perception: ${PERCEPTION_FILE:-(未找到)}"
    sleep 5
done

DECISION_OFFSET=$(wc -l < "$DECISION_FILE" 2>/dev/null || echo 0)
PERCEPTION_OFFSET=$(wc -l < "$PERCEPTION_FILE" 2>/dev/null || echo 0)
log "开始监控"
log "  decision  : $DECISION_FILE (跳过 $DECISION_OFFSET 行)"
log "  perception: $PERCEPTION_FILE (跳过 $PERCEPTION_OFFSET 行)"

# ── 通用：读取文件新增行 ────────────────────────────────────────────────────
read_new_lines() {
    local file="$1"
    local -n offset_ref="$2"   # nameref
    local processor="$3"       # 函数名

    if [[ ! -f "$file" ]]; then
        return
    fi

    local total
    total=$(wc -l < "$file" 2>/dev/null || echo 0)

    # 文件轮转检测
    if (( total < offset_ref )); then
        log "检测到文件轮转（$file），重置偏移"
        offset_ref=0
    fi

    if (( total > offset_ref )); then
        while IFS= read -r line; do
            echo "$line"
            "$processor" "$line"
        done < <(tail -n +$(( offset_ref + 1 )) "$file" 2>/dev/null)
        offset_ref=$total
    fi
}

# ── 主循环 ──────────────────────────────────────────────────────────────────
while true; do
    read_new_lines "$DECISION_FILE"    DECISION_OFFSET    process_decision_line
    read_new_lines "$PERCEPTION_FILE"  PERCEPTION_OFFSET  process_perception_line

    # 定期检查是否有更新的日志文件
    now=$(date +%s)
    if (( now - last_check >= CHECK_INTERVAL )); then
        last_check=$now

        latest_d=$(find_decision_log)
        if [[ -n "$latest_d" && "$latest_d" != "$DECISION_FILE" ]]; then
            log "切换 decision 日志: $latest_d"
            DECISION_FILE="$latest_d"
            DECISION_OFFSET=$(wc -l < "$DECISION_FILE" 2>/dev/null || echo 0)
        fi

        latest_p=$(find_perception_log)
        if [[ -n "$latest_p" && "$latest_p" != "$PERCEPTION_FILE" ]]; then
            log "切换 perception 日志: $latest_p"
            PERCEPTION_FILE="$latest_p"
            PERCEPTION_OFFSET=$(wc -l < "$PERCEPTION_FILE" 2>/dev/null || echo 0)
        fi
    fi

    sleep 1
done
