#!/bin/bash
# 项目打包脚本 - 用于迁移到其他机器

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PACKAGE_NAME="perception_streaming_${TIMESTAMP}.tar.gz"

echo "=========================================="
echo "  项目打包工具"
echo "=========================================="
echo ""

# 检查是否在项目根目录
if [ ! -f "package.json" ]; then
    echo "错误: 请在项目根目录执行此脚本"
    exit 1
fi

echo "[1/3] 准备打包..."
cd "$SCRIPT_DIR"

# 创建临时目录
TEMP_DIR=$(mktemp -d)
PROJECT_DIR="$TEMP_DIR/perception_streaming"
mkdir -p "$PROJECT_DIR"

echo "[2/3] 复制文件..."

# 复制核心文件和目录
cp -r src/ "$PROJECT_DIR/"
cp -r robot_monitor/ "$PROJECT_DIR/"
cp -r script/ "$PROJECT_DIR/"
cp -r scripts/ "$PROJECT_DIR/"
cp -r public/ "$PROJECT_DIR/"
[ -d conf ] && cp -r conf/ "$PROJECT_DIR/"
[ -d config ] && cp -r config/ "$PROJECT_DIR/"

# 复制配置文件
cp package.json package-lock.json "$PROJECT_DIR/"
cp vite.config.ts tsconfig*.json "$PROJECT_DIR/"
cp index.html "$PROJECT_DIR/"
cp requirements.txt "$PROJECT_DIR/" 2>/dev/null || true

# 复制启动脚本
cp start.sh restart_services.sh "$PROJECT_DIR/" 2>/dev/null || true
chmod +x "$PROJECT_DIR"/*.sh

# 复制文档
cp README.md MIGRATION_GUIDE.md "$PROJECT_DIR/"
cp *.md "$PROJECT_DIR/" 2>/dev/null || true

# 创建部署说明
cat > "$PROJECT_DIR/DEPLOY.txt" << 'EOF'
快速部署步骤：

1. 解压文件
   tar -xzf perception_streaming_*.tar.gz
   cd perception_streaming/

2. 安装 Node.js 依赖
   npm install

3. 修改 start.sh 配置
   - SSH_KEY: SSH 密钥路径
   - ROBOT_HOST: 机器人 IP
   - ROBOT_PORT: SSH 端口
   - NODE: node 可执行文件路径

4. 启动服务
   ./start.sh

5. 访问前端
   http://localhost:5173

详细说明请查看 MIGRATION_GUIDE.md
EOF

echo "[3/3] 打包压缩..."
cd "$TEMP_DIR"
tar -czf "$SCRIPT_DIR/$PACKAGE_NAME" perception_streaming/

# 清理临时目录
rm -rf "$TEMP_DIR"

# 显示结果
PACKAGE_SIZE=$(du -h "$SCRIPT_DIR/$PACKAGE_NAME" | cut -f1)
echo ""
echo "=========================================="
echo "  打包完成！"
echo "=========================================="
echo ""
echo "文件名: $PACKAGE_NAME"
echo "大小:   $PACKAGE_SIZE"
echo "路径:   $SCRIPT_DIR/$PACKAGE_NAME"
echo ""
echo "传输到目标机器："
echo "  scp $PACKAGE_NAME user@target-machine:/path/to/deploy/"
echo ""
echo "或使用 Docker 部署（需先创建 Dockerfile）："
echo "  docker build -t perception-streaming ."
echo ""
