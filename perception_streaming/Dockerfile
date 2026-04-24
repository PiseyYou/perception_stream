FROM node:24-alpine

LABEL maintainer="perception_streaming"
LABEL description="割草机器人感知系统实时监控平台"

# 安装必要的系统工具
RUN apk add --no-cache \
    python3 \
    openssh-client \
    lsof \
    bash \
    curl \
    && rm -rf /var/cache/apk/*

# 创建工作目录
WORKDIR /app

# 复制 package.json 并安装依赖（利用 Docker 缓存）
COPY package*.json ./
RUN npm install --production=false

# 复制项目文件
COPY src/ ./src/
COPY robot_monitor/ ./robot_monitor/
COPY script/ ./script/
COPY scripts/ ./scripts/
COPY public/ ./public/
COPY conf/ ./conf/ 2>/dev/null || true
COPY config/ ./config/ 2>/dev/null || true

# 复制配置文件
COPY vite.config.ts tsconfig*.json index.html ./
COPY requirements.txt ./ 2>/dev/null || true
COPY *.sh ./
COPY *.md ./ 2>/dev/null || true

# 赋予脚本执行权限
RUN chmod +x *.sh robot_monitor/*.py robot_monitor/*.mjs script/*.sh 2>/dev/null || true

# 创建必要的目录
RUN mkdir -p logs bags reports

# 暴露端口
EXPOSE 5173 8765 8766 8768 8769

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5173/ || exit 1

# 启动脚本
CMD ["./start.sh"]
