# Perception Streaming

割草机器人感知系统实时监控与离线调试平台，基于 Vue 3 + TypeScript + Vite 构建。

## 核心功能

### 实时监控
- **视频流**：Agora RTC 实时视频传输
- **点云可视化**：Three.js 3D 点云渲染，支持双目图联动
- **避障监控**：实时分析避障行为（正常/漏检/误检），MQTT + SSH 日志联动
- **日志控制台**：ROS2 日志实时查看，WebSocket 桥接，自动重连

### 离线调试
- **单目测试**：本地可执行文件推理，SSE 实时进度推送，支持断点续传
- **Bag包分析**：Camera bag 路径日志解析，多源日志关联
- **日志分析**：SSH 日志获取与分析，支持多设备日志管理；避障分析可按端口后 4 位和日期自动生成日志/图片路径
- **双目分析**：批量分析双目图像文件夹，支持端口映射上传路径、网页缓存图片转存到本地调试机，增强的进度跟踪和错误处理
- **硬件模式支持**：支持白天/夜晚模式切换，自动调整感知参数
- **智能路径管理**：自动路径前缀处理，简化文件夹输入（支持相对路径和绝对路径）
- **图像尺寸筛选**：自动筛选和移除非标准尺寸的双目图像（1280x480）
- **K100 夜间优化**：Model 7 夜间模式支持 6m 自适应双目参数、DSG 点云融合和背景点过滤

### 高级特性
- 点云过滤优化（label=1 背景噪声过滤，保留 label=5 真实障碍物）
- SFTP 断点续传（大文件下载中断恢复）
- 端口号路径映射（根据 SSH 端口自动确定上传目录）
- 批量上传完整性校验
- 避障监控守护服务（systemd 自动拉起）
- 异常触发自动录包
- 支持多设备 SN（LK-MR2P1US000015/16/17/113/115, LK-MR6P1US000123/124/286）
- 双目离线测试工具（stereo_perception_multi2_offline_test）
- 增强的离线服务器（支持多任务管理、进度跟踪、错误恢复）
- Docker 容器化部署支持
- 硬件模式切换（白天/夜晚模式，自动调整感知参数）
- 双目匹配算法优化（支持多种匹配策略和 6m 自适应参数）
- K100/bestmow 硬件自适应（自动调整图像裁剪、分割策略和 DSG 点云融合高度）
- 高性能 PCD 解析器（支持二进制格式，提升点云加载速度）
- 统一的离线调试流程（自动扫描、断点续传、智能路径处理）
- SN 自动路径生成（输入 SN 末尾 4 位自动生成当日路径）
- bestMow CDT 前方矩形框修正（非 K100 模式下可选启用）
- 统一输出目录命名（根据硬件模式自动选择 432 或 384 后缀）
- Vite HTTPS 开发服务器看门狗（自动监控和重启，支持较长冷启动等待，保证服务稳定性）
- HTTPS/WSS 代理访问（`/bridge-ws`、`/pcl-ws`、`/offline`），支持 Agora 安全上下文
- 离线服务与 SSH Bridge 子进程自动拉起（异常退出后按退避重启）
- 日志拉取 SSE 结束后主动断开连接，避免代理层卡住完成态
- MQTT Broker 预设与本地凭据持久化（账号密码通过环境变量注入，不写入代码）
- 双目图片转存（将网页已缓存图片按端口后4位转存到调试电脑目录）
- 避障离线分析路径自动生成（输入端口后4位和日期后自动定位 `data/log_debug/<端口>/<日期>/ros2_log` 与 `data/stereo_debug/<端口>/<日期>`）

## 快速开始

### 环境要求

- Node.js 16+
- Python 3.10+
- **重要**：需要 websockets 10.0+ 库（系统自带的 9.1 版本不兼容）

### 安装步骤

```bash
# 1. 安装前端依赖
npm install

# 2. 安装 Python 依赖（推荐使用项目虚拟环境）
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# 3. 配置默认 MQTT 凭据（可选，不要写入代码）
export VITE_DEFAULT_MQTT_USERNAME=<mqtt 用户名>
export VITE_DEFAULT_MQTT_PASSWORD=<mqtt 密码>

# 4. 一键启动（前端 + 所有后端服务）
./start.sh
```

启动后访问 `https://<本机局域网 IP>:5173`。开发证书为自签名证书，浏览器首次访问需要手动信任；如需指定打开地址，可设置 `VITE_DEV_SERVER_HOST`。

`npm run dev` 会通过 Vite 插件启动并代理：
- `ssh_bridge.py`（端口 8765，默认监听 `0.0.0.0`，可用 `BRIDGE_WS_HOST` 覆盖）- ROS2 日志 WebSocket 桥
- SSH 隧道（本地 8768 → 远端 8767）- 点云数据转发
- `pcl_proxy.mjs`（端口 8766）- 点云代理
- `offline_server.py`（端口 8769）- 离线测试服务器
- Vite HTTPS 开发服务器（端口 5173）- 前端界面

浏览器侧默认通过当前页面域名访问后端代理：
- `/bridge-ws` → `ws://localhost:8765`
- `/pcl-ws` → `ws://localhost:8766`
- `/offline` → `http://localhost:8769`

如需绕过代理，可设置：

```bash
export VITE_BRIDGE_WS_URL=wss://your-host/bridge-ws
export VITE_PCL_WS_URL=wss://your-host/pcl-ws
```

## 项目结构

```
├── src/                              # 前端源码
│   ├── App.vue                       # 主界面（实时监控/Bag包分析/日志分析/单目测试/双目分析）
│   ├── components/                   # Vue 组件
│   │   ├── BagOfflinePanel.vue       # 单目测试面板
│   │   ├── LogAnalysis2Panel.vue     # Bag包分析面板
│   │   ├── StereoAnalysis2Panel.vue  # 双目分析面板（增强版，支持硬件模式）
│   │   ├── LogFetchPanel.vue         # 日志分析面板（多设备支持）
│   │   ├── PointCloudPanel.vue       # 3D 点云渲染
│   │   └── ObstacleMonitor.vue       # 避障监控
│   ├── composables/                  # 组合式函数
│   │   ├── useAgoraRTC.ts            # Agora RTC 封装
│   │   ├── usePcdRenderer.ts         # 点云渲染工具
│   │   └── useBagPcdViewers.ts       # Bag 点云查看器
│   └── utils/                        # 工具函数
│       └── pcdParser.ts              # 高性能 PCD 解析器（支持二进制格式）
├── robot_monitor/                    # 后端服务
│   ├── ssh_bridge.py                 # SSH + WebSocket 桥（8765）
│   ├── offline_server.py             # 离线测试服务器（8769，增强版）
│   ├── config_loader.py              # 配置加载器（支持硬件模式）
│   ├── obstacle_monitor.py           # ROS2 避障监控节点
│   ├── pcl_ws_bridge.py              # 点云 WebSocket 桥（8767）
│   └── pcl_proxy.mjs                 # 点云代理（8766）
├── offline_perception_debug_src/     # 离线调试工具源码
│   ├── bin/offline_perception_debug_432  # 单目离线测试可执行文件
│   ├── include/                      # 头文件（包含硬件模式支持）
│   └── src/                          # C++ 源码（双目匹配、点云生成）
├── stereo_perception_multi2_offline_test/  # 双目离线测试工具
│   ├── include/                      # 头文件（配置、处理器、工具、PCL封装）
│   └── src/                          # C++ 源码（离线处理主程序，支持 K100/bestmow 自适应）
├── tests/                            # 测试文件
│   ├── model6-hardware-size-contract.test.mjs  # Model 6 硬件尺寸契约测试
│   ├── pcd-parser.test.mjs           # PCD 解析器测试
│   ├── stereo-download-to-local.test.mjs # 双目图片转存到调试电脑测试
│   ├── stereo-stop-button.test.mjs   # 双目停止按钮测试
│   └── stereo-upload-timeout.test.mjs # 双目上传超时测试
├── Dockerfile.perception             # Docker 镜像构建文件
├── build_offline_test_main_in_docker.sh  # Docker 构建脚本
├── start.sh                          # 一键启动脚本
└── vite.config.ts                    # Vite 配置
```

## 数据流架构

```
机器人 (ROS2)
    ├─ obstacle_monitor.py  →  MQTT Broker         →  Web UI（避障状态 + AVOIDING 日志）
    ├─ ssh_bridge.py        →  WebSocket 8765      →  Vite /bridge-ws → Web UI（实时日志 + SSH 日志关联）
    └─ pcl_ws_bridge.py     →  pcl_proxy.mjs 8766  →  Vite /pcl-ws    → Web UI（点云）

离线分析
    └─ offline_server.py    →  HTTP/SSE 8769       →  Vite /offline   → Web UI（离线感知测试进度 + 部署管理）

视频流：Agora RTC（需要 HTTPS 安全上下文）
```

## 技术栈

| 技术 | 用途 |
|------|------|
| Vue 3 + TypeScript | 前端框架 |
| Three.js | 3D 点云渲染 |
| Agora RTC SDK | 实时视频流 |
| MQTT.js | MQTT 客户端 |
| JSZip | Bag 文件解压 |
| Paramiko (Python) | SSH 隧道 |
| WebSocket | 实时日志/点云传输 |
| SSE (Server-Sent Events) | 离线推理进度推送 |

## 避障行为分类

- `normal` — 正常避障
- `miss_avoidance` — 漏检（有障碍未避）
- `false_avoidance` — 误检（无障碍触发避障）

## 常见问题

### 网页无法访问 (ERR_CONNECTION_REFUSED)

如果访问 `https://<本机局域网 IP>:5173` 时出现连接被拒绝错误，通常是文件监视器数量超限导致 Vite 服务器崩溃：

**原因**：项目目录包含大量文件（如 `lib/`、`include/` 目录），超过系统 inotify 监视器限制。

**解决方案**：
1. 已在 `vite.config.ts` 中配置忽略 `lib/` 和 `include/` 目录
2. 如果问题仍存在，可临时增加系统限制（需要 sudo 权限）：
   ```bash
   sudo sysctl fs.inotify.max_user_watches=524288
   ```
3. 永久修改（可选）：
   ```bash
   echo "fs.inotify.max_user_watches=524288" | sudo tee -a /etc/sysctl.conf
   sudo sysctl -p
   ```

### Bridge 显示"未连接"

如果 Bridge 一直显示"未连接"状态，通常是 Python 依赖未安装、服务未启动或 WebSocket 地址配置不一致：

```bash
# 检查依赖版本
. .venv/bin/activate
python -c "import websockets, paramiko; print(websockets.__version__, paramiko.__version__)"

# 安装/更新依赖
pip install -r requirements.txt

# 重启服务
pkill -f vite
npm run dev
```

默认情况下前端会根据当前页面协议连接 `/bridge-ws`，Vite 再代理到 `ws://localhost:8765`。如果需要直连其他地址，设置 `VITE_BRIDGE_WS_URL`。

### SSH 端口自动更新

选择不同设备 SN 时，SSH 端口会自动更新（规则：10 + SN后4位）：
- LK-MR2P1US000015 → 10015
- LK-MR2P1US000016 → 10016
- LK-MR2P1US000017 → 10017
- LK-MR2P1US000113 → 10113
- LK-MR2P1US000115 → 10115
- LK-MR6P1US000123 → 10123
- LK-MR6P1US000124 → 10124
- LK-MR6P1US000286 → 10286

### MQTT 连接配置

默认 Broker 为 `mqtt-us.yjserver.com`，连接面板会提供 Broker 预设并将用户输入的账号密码保存到浏览器本地缓存。默认账号密码通过环境变量注入：

```bash
export VITE_DEFAULT_MQTT_USERNAME=<mqtt 用户名>
export VITE_DEFAULT_MQTT_PASSWORD=<mqtt 密码>
```

不要把真实 MQTT 密码提交到代码或 README 中。

### SSH 密钥配置

系统使用 `data/conf/ssh_config.json` 配置SSH连接参数：

```json
{
  "ssh_key_path": "bestmow_rsa_202605",
  "ssh_host": "120.25.121.3",
  "ssh_user": "root",
  "default_ports": {
    "realtime_monitor": 10015,
    "log_fetch": 10016,
    "stereo_analysis": 10115
  }
}
```

- `ssh_key_path`: SSH私钥文件名（相对于 `data/conf/` 目录）
- `ssh_host`: 远程主机地址
- `ssh_user`: SSH用户名
- `default_ports`: 各服务的默认端口配置

### 双目图片转存到调试电脑

双目分析面板的“转存本地”按钮会把网页端已缓存的图片，从 `data/stereo_debug/<端口后4位>/` 复制到调试电脑，默认目标为：

```text
youfeng@192.168.55.239:/home/youfeng/debug/boluo/<端口后4位>/<日期文件夹>/
```

可通过环境变量覆盖目标配置：

```bash
export BOLUO_TRANSFER_HOST=192.168.55.239
export BOLUO_TRANSFER_USER=youfeng
export BOLUO_TRANSFER_PASSWORD=<调试电脑密码>
export BOLUO_TRANSFER_BASE=/home/youfeng/debug/boluo
```

该功能依赖 `sshpass` 和 `rsync`，会按起止日期筛选本地缓存文件夹，并只转存常见图片格式（jpg/jpeg/png/bmp/webp）。

## 守护服务部署

### 避障监控守护服务
```bash
# 安装避障监控守护服务（systemd）
cp script/monitor_avoiding.service /etc/systemd/system/
systemctl enable monitor_avoiding
systemctl start monitor_avoiding
```

### Vite 开发服务器看门狗
自动监控 Vite HTTPS 开发服务器状态，一旦检测到服务掉线，自动重启服务。

```bash
# 启动看门狗
./start-watchdog.sh

# 停止看门狗
./stop-watchdog.sh

# 查看日志
tail -f /tmp/vite-watchdog.log
```

看门狗默认检查 `https://127.0.0.1:5173/`，开发证书为自签名证书，脚本会使用 `curl -k` 检查。由于当前项目冷启动通常需要 50 秒以上，看门狗改为轮询等待 Vite 就绪，而不是固定等待 8 秒。可通过 `VITE_WATCHDOG_URL`、`VITE_WATCHDOG_STARTUP_TIMEOUT` 和 `VITE_WATCHDOG_STARTUP_CHECK_INTERVAL` 覆盖检测地址与启动等待策略。

详细说明请参考 [WATCHDOG.md](WATCHDOG.md)

## 开发说明

- 前端开发：`npm run dev`
- 构建生产版本：`npm run build`
- 预览生产版本：`npm run preview`
- Node 回归测试：`node tests/watchdog-http-url.test.mjs && node tests/vite-http-server.test.mjs && node tests/vite-offline-sse-proxy.test.mjs && node tests/offline-server-plugin-restart.test.mjs && node tests/log-pull-sse-contract.test.mjs`
- Python 回归测试：`python3 -m unittest robot_monitor.tests.test_offline_server`
- 后端服务独立重启：`./restart_services.sh`（优先使用 `.venv/bin/python`，也可通过 `PYTHON=/path/to/python` 覆盖）
- 后端服务独立启动：参考 `start.sh` 中的命令

## 相关文档

- [部署分析](DEPLOYMENT_ANALYSIS_FINAL.md)
- [部署检查清单](DEPLOYMENT_CHECKLIST.md)
- [配置迁移指南](CONFIG_MIGRATION.md)
- [离线测试设置](OFFLINE_TEST_SETUP.md)
- [启动指南](START_GUIDE.md)
- [硬件模式修复报告](HARDWARE_MODE_FIX_REPORT.md)
- [Segfault 修复说明](SEGFAULT_FIX.md)
- [任务完成报告](TASK_COMPLETION_REPORT.md)
- [双目离线测试快速开始](stereo_perception_multi2_offline_test/QUICK_START.md)
- [编译验证报告](stereo_perception_multi2_offline_test/COMPILATION_VERIFICATION_REPORT.md)
- [Vite 看门狗说明](WATCHDOG.md)
