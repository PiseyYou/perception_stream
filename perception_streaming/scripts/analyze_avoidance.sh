#!/bin/bash

# 避障日志分析主脚本
# 使用方法: ./analyze_avoidance.sh <machine_name> [date] [time_range]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$PROJECT_ROOT/config/machine_config.json"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# 检查参数
if [ $# -lt 1 ]; then
    print_error "使用方法: $0 <machine_name> [date] [time_range]"
    echo ""
    echo "示例:"
    echo "  $0 test_machine_1                    # 分析今天的日志"
    echo "  $0 test_machine_1 20260414           # 分析指定日期"
    echo "  $0 test_machine_1 20260414 '03:14-03:36'  # 分析指定时间段"
    exit 1
fi

MACHINE_NAME=$1
DATE=${2:-$(date +%Y%m%d)}
TIME_RANGE=${3:-""}

# 检查配置文件
if [ ! -f "$CONFIG_FILE" ]; then
    print_error "配置文件不存在: $CONFIG_FILE"
    exit 1
fi

# 检查jq是否安装
if ! command -v jq &> /dev/null; then
    print_error "jq 未安装，请运行: sudo apt-get install jq"
    exit 1
fi

# 读取机器配置
MACHINE_CONFIG=$(jq -r ".machines.\"$MACHINE_NAME\"" "$CONFIG_FILE")
if [ "$MACHINE_CONFIG" == "null" ]; then
    print_error "机器配置不存在: $MACHINE_NAME"
    print_info "可用的机器:"
    jq -r '.machines | keys[]' "$CONFIG_FILE"
    exit 1
fi

# 提取配置信息
MACHINE_DISPLAY_NAME=$(echo "$MACHINE_CONFIG" | jq -r '.name')
SSH_HOST=$(echo "$MACHINE_CONFIG" | jq -r '.host')
SSH_PORT=$(echo "$MACHINE_CONFIG" | jq -r '.port')
SSH_KEY=$(echo "$MACHINE_CONFIG" | jq -r '.ssh_key')
SSH_USER=$(echo "$MACHINE_CONFIG" | jq -r '.user')
LOG_BASE_PATH=$(echo "$MACHINE_CONFIG" | jq -r '.log_base_path')
IMAGE_BASE_PATH=$(echo "$MACHINE_CONFIG" | jq -r '.image_base_path')

# SSH命令前缀
SSH_CMD="ssh -i $SSH_KEY $SSH_USER@$SSH_HOST -p $SSH_PORT"

# 打印分析信息
echo ""
echo "=== 避障日志分析 ==="
print_info "机器: $MACHINE_DISPLAY_NAME ($SSH_HOST:$SSH_PORT)"
print_info "日期: $DATE"
if [ -n "$TIME_RANGE" ]; then
    print_info "时间段: $TIME_RANGE"
fi
echo ""

# 测试SSH连接
print_info "测试SSH连接..."
if ! $SSH_CMD "echo 'SSH连接成功'" &> /dev/null; then
    print_error "SSH连接失败"
    exit 1
fi
print_success "SSH连接正常"

# 创建输出目录
REPORT_DIR="$PROJECT_ROOT/reports"
LOG_CACHE_DIR="$PROJECT_ROOT/logs"
mkdir -p "$REPORT_DIR" "$LOG_CACHE_DIR"

# 阶段1: 数据收集
echo ""
print_info "[1/4] 数据收集..."

# 列出避障图片
IMAGE_DIR="$IMAGE_BASE_PATH/$DATE"
print_info "检查避障图片: $IMAGE_DIR"

IMAGE_COUNT=$($SSH_CMD "ls $IMAGE_DIR/*.jpg 2>/dev/null | wc -l" || echo "0")
if [ "$IMAGE_COUNT" -eq 0 ]; then
    print_warning "未找到避障图片"
    exit 0
fi

print_success "找到 $IMAGE_COUNT 张避障图片"

# 统计DSG和SUB类型
DSG_COUNT=$($SSH_CMD "ls $IMAGE_DIR/*_avoiding_DSG.jpg 2>/dev/null | wc -l" || echo "0")
SUB_COUNT=$($SSH_CMD "ls $IMAGE_DIR/*_avoiding_SUB.jpg 2>/dev/null | wc -l" || echo "0")

print_success "DSG避障: ${DSG_COUNT}次"
print_success "SUB避障: ${SUB_COUNT}次"

# 提取时间戳
print_info "提取时间戳..."
TIMESTAMPS_FILE="$LOG_CACHE_DIR/timestamps_${DATE}.txt"
$SSH_CMD "ls $IMAGE_DIR/*.jpg | sed 's/.*perception_stereo_//' | sed 's/_avoiding.*//' | sort" > "$TIMESTAMPS_FILE"
TIMESTAMP_COUNT=$(wc -l < "$TIMESTAMPS_FILE")
print_success "提取了 $TIMESTAMP_COUNT 个时间戳"

# 阶段2: 日志关联分析
echo ""
print_info "[2/4] 日志关联分析..."

# 调用Python分析脚本
PYTHON_SCRIPT="$SCRIPT_DIR/analyze_avoidance.py"
if [ -f "$PYTHON_SCRIPT" ]; then
    python3 "$PYTHON_SCRIPT" \
        --machine "$MACHINE_NAME" \
        --date "$DATE" \
        --time-range "$TIME_RANGE" \
        --config "$CONFIG_FILE" \
        --timestamps "$TIMESTAMPS_FILE" \
        --output "$REPORT_DIR"
else
    print_warning "Python分析脚本不存在，使用简化分析"

    # 简化分析：直接查询关键日志
    print_info "分析底盘日志..."
    BLADE_WARNING_COUNT=$($SSH_CMD "grep 'cut motor_warning' $LOG_BASE_PATH/chassis_node_*.log 2>/dev/null | grep -c '$DATE' || echo 0")
    print_success "刀片警告: ${BLADE_WARNING_COUNT}次"

    print_info "分析决策日志..."
    AVOIDING_COUNT=$($SSH_CMD "grep 'Work:AVOIDING' $LOG_BASE_PATH/robot_decision_*.log 2>/dev/null | grep -c '$DATE' || echo 0")
    print_success "避障状态切换: ${AVOIDING_COUNT}次"

    print_info "分析覆盖导航日志..."
    BLOCKED_COUNT=$($SSH_CMD "grep 'cut motor maybe blocked' $LOG_BASE_PATH/coverage_navigator_server_*.log 2>/dev/null | grep -c '$DATE' || echo 0")
    print_success "刀片堵转检测: ${BLOCKED_COUNT}次"

    # 生成简化报告
    REPORT_FILE="$REPORT_DIR/avoidance_${DATE}_$(date +%H%M%S).md"
    cat > "$REPORT_FILE" << EOF
# 避障分析报告

**机器**: $MACHINE_DISPLAY_NAME
**日期**: $DATE
**分析时间**: $(date '+%Y-%m-%d %H:%M:%S')

## 执行摘要

- 总避障次数: ${IMAGE_COUNT}次
- DSG避障: ${DSG_COUNT}次
- SUB避障: ${SUB_COUNT}次
- 刀片警告: ${BLADE_WARNING_COUNT}次
- 避障状态切换: ${AVOIDING_COUNT}次
- 刀片堵转检测: ${BLOCKED_COUNT}次

## 初步分析

根据日志统计，主要避障原因可能是:

EOF

    if [ "$BLOCKED_COUNT" -gt 0 ]; then
        echo "1. **刀片电机堵转** (检测到 ${BLOCKED_COUNT} 次)" >> "$REPORT_FILE"
    fi

    if [ "$BLADE_WARNING_COUNT" -gt 0 ]; then
        echo "2. **刀片电机警告** (${BLADE_WARNING_COUNT} 次)" >> "$REPORT_FILE"
    fi

    echo "" >> "$REPORT_FILE"
    echo "## 建议" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    echo "- 安装Python分析脚本以获取详细分析" >> "$REPORT_FILE"
    echo "- 检查刀片高度设置" >> "$REPORT_FILE"
    echo "- 检查工作区域地形" >> "$REPORT_FILE"

    print_success "简化报告已生成: $REPORT_FILE"
fi

# 阶段3: 生成报告
echo ""
print_info "[3/4] 生成报告..."
print_success "报告已保存到: $REPORT_DIR"

# 阶段4: 清理
echo ""
print_info "[4/4] 清理临时文件..."
# 保留时间戳文件供后续使用
print_success "完成"

echo ""
print_success "分析完成！"
echo ""
