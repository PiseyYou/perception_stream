#!/bin/bash

# 测试避障分析工具配置
# 使用方法: ./test_setup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== 避障分析工具配置测试 ==="
echo ""

# 1. 检查目录结构
echo "1. 检查目录结构..."
REQUIRED_DIRS=("config" "scripts" "reports" "logs")
for dir in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$PROJECT_ROOT/$dir" ]; then
        echo -e "  ${GREEN}✓${NC} $dir/"
    else
        echo -e "  ${RED}✗${NC} $dir/ (缺失)"
        exit 1
    fi
done

# 2. 检查配置文件
echo ""
echo "2. 检查配置文件..."
CONFIG_FILE="$PROJECT_ROOT/config/machine_config.json"
if [ -f "$CONFIG_FILE" ]; then
    echo -e "  ${GREEN}✓${NC} machine_config.json"

    # 验证JSON格式
    if cat "$CONFIG_FILE" | jq . > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} JSON格式正确"
    else
        echo -e "  ${RED}✗${NC} JSON格式错误"
        exit 1
    fi

    # 列出配置的机器
    echo ""
    echo "  配置的机器:"
    cat "$CONFIG_FILE" | jq -r '.machines | keys[]' | while read machine; do
        echo "    - $machine"
    done
else
    echo -e "  ${RED}✗${NC} machine_config.json (缺失)"
    exit 1
fi

# 3. 检查脚本文件
echo ""
echo "3. 检查脚本文件..."
SCRIPTS=("analyze_avoidance.sh" "analyze_avoidance.py")
for script in "${SCRIPTS[@]}"; do
    SCRIPT_PATH="$PROJECT_ROOT/scripts/$script"
    if [ -f "$SCRIPT_PATH" ]; then
        if [ -x "$SCRIPT_PATH" ]; then
            echo -e "  ${GREEN}✓${NC} $script (可执行)"
        else
            echo -e "  ${YELLOW}!${NC} $script (不可执行，正在修复...)"
            chmod +x "$SCRIPT_PATH"
            echo -e "  ${GREEN}✓${NC} $script (已修复)"
        fi
    else
        echo -e "  ${RED}✗${NC} $script (缺失)"
        exit 1
    fi
done

# 4. 检查系统依赖
echo ""
echo "4. 检查系统依赖..."
DEPS=("jq" "ssh" "python3")
for dep in "${DEPS[@]}"; do
    if command -v $dep &> /dev/null; then
        VERSION=$($dep --version 2>&1 | head -1)
        echo -e "  ${GREEN}✓${NC} $dep ($VERSION)"
    else
        echo -e "  ${RED}✗${NC} $dep (未安装)"
        echo "    安装命令: sudo apt-get install $dep"
    fi
done

# 5. 测试SSH连接（如果配置了机器）
echo ""
echo "5. 测试SSH连接..."
FIRST_MACHINE=$(cat "$CONFIG_FILE" | jq -r '.machines | keys[0]')
if [ "$FIRST_MACHINE" != "null" ] && [ "$FIRST_MACHINE" != "machine_template" ]; then
    echo "  测试机器: $FIRST_MACHINE"

    HOST=$(cat "$CONFIG_FILE" | jq -r ".machines.\"$FIRST_MACHINE\".host")
    PORT=$(cat "$CONFIG_FILE" | jq -r ".machines.\"$FIRST_MACHINE\".port")
    SSH_KEY=$(cat "$CONFIG_FILE" | jq -r ".machines.\"$FIRST_MACHINE\".ssh_key")
    USER=$(cat "$CONFIG_FILE" | jq -r ".machines.\"$FIRST_MACHINE\".user")

    if [ -f "$SSH_KEY" ]; then
        echo -e "  ${GREEN}✓${NC} SSH密钥存在: $SSH_KEY"

        # 测试连接
        if ssh -i "$SSH_KEY" "$USER@$HOST" -p "$PORT" "echo 'test'" &> /dev/null; then
            echo -e "  ${GREEN}✓${NC} SSH连接成功"
        else
            echo -e "  ${YELLOW}!${NC} SSH连接失败 (可能需要配置)"
        fi
    else
        echo -e "  ${YELLOW}!${NC} SSH密钥不存在: $SSH_KEY"
    fi
else
    echo -e "  ${YELLOW}!${NC} 未配置机器，跳过SSH测试"
fi

# 6. 检查文档
echo ""
echo "6. 检查文档..."
DOCS=("AVOIDANCE_ANALYSIS_README.md" "QUICKSTART.md" "requirements.txt")
for doc in "${DOCS[@]}"; do
    if [ -f "$PROJECT_ROOT/$doc" ]; then
        echo -e "  ${GREEN}✓${NC} $doc"
    else
        echo -e "  ${YELLOW}!${NC} $doc (缺失)"
    fi
done

# 总结
echo ""
echo "=== 测试完成 ==="
echo ""
echo "下一步:"
echo "1. 编辑 config/machine_config.json 添加你的机器配置"
echo "2. 运行: ./scripts/analyze_avoidance.sh <machine_name>"
echo "3. 查看报告: cat reports/avoidance_*.md"
echo ""
echo "详细文档:"
echo "- 完整文档: AVOIDANCE_ANALYSIS_README.md"
echo "- 快速开始: QUICKSTART.md"
echo ""
