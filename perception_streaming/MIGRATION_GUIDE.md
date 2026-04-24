# 项目迁移指南（精简版）

## 一、打包准备

### 1.1 需要打包的核心文件

```bash
# 在当前机器执行
tar -czf perception_streaming_minimal.tar.gz \
  --exclude='node_modules' \
  --exclude='.git' \
  --exclude='dist' \
  --exclude='logs' \
  --exclude='bags' \
  --exclude='reports' \
  --exclude='*.log' \
  --exclude='.vscode' \
  --exclude='.claude' \
  src/ \
  robot_monitor/ \
  script/ \
  scripts/ \
  public/ \
  conf/ \
  config/ \
  *.sh \
  *.md \
  *.json \
  *.ts \
  *.html \
  requirements.txt \
  vite.config.ts
```

### 1.2 环境依赖清单

**Node.js 环境：**
- Node.js v24.13.0（或 v18+ 兼容版本）
- npm（随 Node.js 安装）

**Python 环境：**
- Python 3.8+
- 标准库即可（无额外依赖）

**系统工具：**
- SSH 客户端
- lsof（端口管理）
- systemd（可选，用于守护服务）

---

## 二、目标机器部署步骤

### 2.1 环境准备

```bash
# 1. 安装 Node.js（推荐使用 nvm）
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
source ~/.bashrc
nvm install 24.13.0
nvm use 24.13.0

# 2. 验证 Python（通常系统自带）
python3 --version  # 需要 3.8+

# 3. 安装系统工具（Ubuntu/Debian）
sudo apt-get update
sudo apt-get install -y openssh-client lsof
```

### 2.2 项目部署

```bash
# 1. 传输打包文件到目标机器
scp perception_streaming_minimal.tar.gz user@target-machine:/path/to/deploy/

# 2. 在目标机器解压
cd /path/to/deploy/
tar -xzf perception_streaming_minimal.tar.gz
cd perception_streaming-master-*

# 3. 安装 Node.js 依赖
npm install

# 4. 配置 SSH 密钥（重要！）
# 将你的 SSH 私钥复制到目标机器
mkdir -p ~/.ssh
chmod 700 ~/.ssh
# 复制密钥文件到 ~/.ssh/ 并设置权限
chmod 600 ~/.ssh/your_key_file

# 5. 修改 start.sh 中的路径
nano start.sh
# 修改以下变量：
# - SSH_KEY: 指向你的 SSH 密钥路径
# - NODE: 指向 node 可执行文件路径（可用 which node 查看）
# - ROBOT_HOST/ROBOT_PORT: 机器人连接信息
```

### 2.3 配置文件调整

**编辑 [start.sh](start.sh)：**

```bash
#!/bin/bash
# 根据目标机器环境修改以下变量

SSH_KEY="/home/YOUR_USERNAME/.ssh/your_key_file"  # ← 修改
ROBOT_HOST="120.25.121.3"                          # ← 根据实际修改
ROBOT_PORT="10015"                                 # ← 根据实际修改
NODE="$(which node)"                               # ← 自动检测或手动指定

# 其余保持不变
```

### 2.4 启动服务

```bash
# 赋予执行权限
chmod +x start.sh

# 启动所有服务
./start.sh
```

访问：http://localhost:5173

---

## 三、Docker 部署方案（可选）

如果需要容器化部署，创建以下文件：

### 3.1 创建 Dockerfile

```dockerfile
FROM node:24-alpine

# 安装必要工具
RUN apk add --no-cache \
    python3 \
    openssh-client \
    lsof \
    bash

WORKDIR /app

# 复制项目文件
COPY package*.json ./
RUN npm install

COPY . .

# 暴露端口
EXPOSE 5173 8765 8766 8768 8769

# 启动脚本
CMD ["./start.sh"]
```

### 3.2 创建 docker-compose.yml

```yaml
version: '3.8'

services:
  perception-streaming:
    build: .
    container_name: perception_streaming
    ports:
      - "5173:5173"   # Vite 前端
      - "8765:8765"   # SSH Bridge
      - "8766:8766"   # PCL Proxy
      - "8768:8768"   # PCL Tunnel
      - "8769:8769"   # Offline Server
    volumes:
      - ./logs:/app/logs
      - ./bags:/app/bags
      - ./reports:/app/reports
      - ~/.ssh:/root/.ssh:ro  # SSH 密钥（只读）
    environment:
      - NODE_ENV=production
      - ROBOT_HOST=120.25.121.3
      - ROBOT_PORT=10015
    restart: unless-stopped
    network_mode: host  # 使用主机网络模式（简化端口映射）
```

### 3.3 Docker 部署命令

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

---

## 四、验证清单

部署完成后，逐项检查：

- [ ] Node.js 版本正确（`node --version`）
- [ ] Python 版本正确（`python3 --version`）
- [ ] SSH 密钥权限正确（`ls -l ~/.ssh/`）
- [ ] 能够 SSH 连接到机器人（`ssh -i <key> root@<host> -p <port>`）
- [ ] 前端页面可访问（http://localhost:5173）
- [ ] WebSocket 连接正常（查看浏览器控制台）
- [ ] 点云数据能正常显示
- [ ] 日志实时更新

---

## 五、常见问题

### 5.1 端口被占用

```bash
# 查看占用端口的进程
lsof -ti:5173
lsof -ti:8765

# 杀死进程
kill $(lsof -ti:5173)
```

### 5.2 SSH 连接失败

```bash
# 测试 SSH 连接
ssh -i ~/.ssh/your_key root@120.25.121.3 -p 10015 -v

# 检查密钥权限
chmod 600 ~/.ssh/your_key
```

### 5.3 Node.js 路径问题

```bash
# 查找 node 路径
which node

# 更新 start.sh 中的 NODE 变量
NODE="$(which node)"
```

---

## 六、最小化部署（仅核心功能）

如果只需要基础监控功能，可以进一步精简：

### 6.1 精简打包

```bash
tar -czf perception_minimal_core.tar.gz \
  src/App.vue \
  src/components/ConnectionPanel.vue \
  src/components/VideoPlayer.vue \
  src/components/PointCloudPanel.vue \
  src/composables/ \
  src/utils/ \
  robot_monitor/ssh_bridge.py \
  robot_monitor/pcl_proxy.mjs \
  public/index.html \
  package.json \
  vite.config.ts \
  start.sh
```

### 6.2 简化启动脚本

创建 `start_minimal.sh`：

```bash
#!/bin/bash
NODE="$(which node)"
PYTHON="$(which python3)"

# 启动 SSH Bridge
$PYTHON robot_monitor/ssh_bridge.py &

# 启动 PCL Proxy
$NODE robot_monitor/pcl_proxy.mjs &

# 启动 Vite
$NODE node_modules/vite/bin/vite.js

# 等待并清理
wait
```

---

## 七、备份与回滚

### 7.1 备份当前配置

```bash
# 在目标机器备份
tar -czf backup_$(date +%Y%m%d_%H%M%S).tar.gz \
  ~/.ssh/ \
  /path/to/perception_streaming/
```

### 7.2 快速回滚

```bash
# 恢复备份
tar -xzf backup_YYYYMMDD_HHMMSS.tar.gz -C /
```

---

## 附录：文件清单

**必需文件（~50MB 含依赖）：**
- `src/` - 前端源码
- `robot_monitor/` - 后端服务
- `package.json` - Node.js 依赖
- `vite.config.ts` - 构建配置
- `start.sh` - 启动脚本

**可选文件：**
- `script/` - 守护服务脚本
- `public/` - 静态资源
- `docs/` - 文档

**无需迁移：**
- `node_modules/` - 目标机器重新安装
- `.git/` - 版本控制历史
- `logs/`, `bags/`, `reports/` - 运行时数据
