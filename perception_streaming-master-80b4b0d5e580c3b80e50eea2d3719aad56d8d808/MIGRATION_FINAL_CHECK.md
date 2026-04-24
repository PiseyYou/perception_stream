# 项目外部依赖最终检查报告

**检查时间**: 2026-04-21  
**目标**: 准备项目打包迁移到其他机器

---

## ✅ 已完成的迁移工作

### 1. 核心程序和库（已迁移到项目内）

#### 1.1 离线感知调试程序 ✅
```
bin/
└── offline_perception_debug_432  (492KB, 已迁移)

robot_monitor/offline_server.py:39
OFFLINE_EXE = os.path.abspath(os.path.join(PROJECT_ROOT, "bin/offline_perception_debug_432"))
```
**状态**: ✅ 已使用相对路径

#### 1.2 夜间离线测试程序 ✅
```
night_offline_debug/
├── build/
│   ├── run_cdt_dsg_fusion_dir  (1.6MB, 可执行)
│   └── run_cdt_dsg_fusion      (1.0MB, 可执行)
└── model/
    ├── dsg_multi_20260401_640x384.bin  (8.2MB)
    └── night_0331_167.bin              (8.2MB)

robot_monitor/offline_server.py:40
NIGHT_EXE = os.path.abspath(os.path.join(PROJECT_ROOT, "night_offline_debug/build/run_cdt_dsg_fusion_dir"))
```
**状态**: ✅ 已使用相对路径

#### 1.3 DNN动态库 ✅
```
lib/dnn_x86/
├── libdnn.so           (7.6MB)
└── libhbdk_sim_x86.so  (4.9MB)

robot_monitor/offline_server.py:41
OFFLINE_LIB = os.path.abspath(os.path.join(PROJECT_ROOT, "lib/dnn_x86"))
```
**状态**: ✅ 已使用相对路径

#### 1.4 AI模型文件 ✅
```
models/
├── dsg_multi_20260407_640x384.bin      (8.3MB) - 主模型
├── dsg_20260211_640x384.bin            (2.2MB)
├── cdt_20251125_640x384.bin            (3.5MB)
├── sub_20260303_640x384.bin            (8.3MB)
├── mul_20250918_640x384.bin            (7.3MB)
├── seg_20250421_640x384.bin            (6.3MB)
├── det_20241106_640x480.bin            (3.7MB)
└── cqr_20250821_640x384_yolov8n.bin    (3.8MB)

robot_monitor/offline_server.py:43-44
DSG_MODEL = os.path.abspath(os.path.join(PROJECT_ROOT, "models/dsg_multi_20260407_640x384.bin"))
```
**状态**: ✅ 已使用相对路径，模型文件齐全

#### 1.5 数据目录 ✅
```
data/
├── conf/
│   ├── bestmow_rsa_202604      (SSH密钥)
│   ├── ssh_config.json         (SSH配置)
│   └── README.md
├── bag_debug/                   (Bag包分析数据)
├── log_debug/                   (日志分析数据)
├── stereo_debug/                (双目分析数据)
└── visualization/               (可视化数据)
```
**状态**: ✅ 完整迁移

#### 1.6 源代码备份 ✅
```
offline_perception_debug_src/
├── build/
├── cmake-build-debug/
│   ├── offline_perception_debug_432_sob
│   ├── offline_perception_debug_color
│   └── offline_perception_debug
├── include/
├── models/
├── src/
└── CMakeLists.txt
```
**状态**: ✅ 源代码已保留在项目内

---

## ⚠️ 仍需处理的外部依赖

### 2. 硬编码路径（需要修改）

#### 2.1 vite.config.ts - Python和SSH密钥路径 ⚠️
**文件**: `vite.config.ts:10-11`
```typescript
const PYTHON = '/home/youfeng/anaconda3/bin/python3'  // ❌ 硬编码
const SSH_KEY = '/home/youfeng/CLionProjects/12-evb/evb_test/ssh/bestmow_rsa_202604'  // ❌ 硬编码
```

**建议修改**:
```typescript
const PYTHON = process.env.PYTHON || 'python3'
const SSH_KEY = path.resolve(__dirname, 'data/conf/bestmow_rsa_202604')
```

#### 2.2 package.json - Node.js路径 ⚠️
**文件**: `package.json:7-9`
```json
"dev": "/home/youfeng/.nvm/versions/node/v24.13.0/bin/node node_modules/vite/bin/vite.js",
"build": "/home/youfeng/.nvm/versions/node/v24.13.0/bin/node node_modules/vite/bin/vite.js build",
"preview": "/home/youfeng/.nvm/versions/node/v24.13.0/bin/node node_modules/vite/bin/vite.js preview"
```

**建议修改**:
```json
"dev": "vite",
"build": "vite build",
"preview": "vite preview"
```

#### 2.3 robot_monitor/ssh_bridge.py - 上传目录 ⚠️
**文件**: `robot_monitor/ssh_bridge.py:53, 994, 1420`
```python
BULK_UPLOAD_DEST = "/home/youfeng/debug/03/claude_bag"  # ❌ 硬编码
upload_dest = f"/home/youfeng/debug/boluo/{port_suffix}/rosbag"  # ❌ 硬编码
local_dest = f"/home/youfeng/debug/03/{date}"  # ❌ 硬编码
```

**建议修改**:
```python
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BULK_UPLOAD_DEST = os.path.join(PROJECT_ROOT, "data/uploads")
```

#### 2.4 robot_monitor/offline_server.py - 上传和Docker路径 ⚠️
**文件**: `robot_monitor/offline_server.py`
```python
# Line 1266
LOCAL_IMAGE_BASE = "/home/youfeng/debug/03"

# Line 1312
LOCAL_IMAGE_CUSTOM_BASE = "/home/youfeng/debug/boluo"

# Line 1461
LOCAL_LOG_PULL_BASE = "/home/youfeng/debug/boluo"

# Line 2380
cross_compile_dir = "/home/youfeng/CLionProjects/07_openclaw_auto/project/cross_compile/"

# Line 2409-2411
'-v', '/home/youfeng/CLionProjects/07_openclaw_auto/project/cross_compile/:/open_explorer',
'-v', '/home/youfeng/CLionProjects/10-rdkx5/docker_packages/data/:/data',
'-v', '/home/youfeng/CLionProjects/12-evb/project/:/offline_debug',
```

**建议修改**: 使用 `PROJECT_ROOT` 相对路径或配置文件

#### 2.5 config/machine_config.json - SSH密钥路径 ⚠️
**文件**: `config/machine_config.json:7`
```json
"ssh_key": "/home/youfeng/CLionProjects/12-evb/evb_test/ssh/bestmow_rsa_202604"
```

**建议修改**:
```json
"ssh_key": "../data/conf/bestmow_rsa_202604"
```

#### 2.6 测试脚本 - SSH密钥路径 ⚠️
**文件**: 
- `test_sftp_fix.sh:4`
- `test_rsync_fix.sh:4`
- `test_scp_upload.sh:4`
- `robot_monitor/test_connection.sh:6`
- `robot_monitor/deploy_to_robot.sh:6`

```bash
SSH_KEY="/home/youfeng/CLionProjects/12-evb/evb_test/ssh/bestmow_rsa_202604"
```

**建议修改**:
```bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SSH_KEY="$PROJECT_ROOT/data/conf/bestmow_rsa_202604"
```

#### 2.7 restart_services.sh - 项目路径 ⚠️
**文件**: `restart_services.sh:4`
```bash
PROJECT_DIR="/home/youfeng/CLionProjects/07_openclaw_auto/project/perception_streaming-master-80b4b0d5e580c3b80e50eea2d3719aad56d8d808"
```

**建议修改**:
```bash
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
```

---

## 📋 修复优先级

### 🔴 P0 - 必须修复（阻塞打包）
1. ✅ **offline_server.py 核心路径** - 已完成
2. ⚠️ **vite.config.ts** - Python和SSH密钥路径
3. ⚠️ **package.json** - Node.js路径

### 🟡 P1 - 建议修复（影响功能）
4. ⚠️ **ssh_bridge.py** - 上传目录路径
5. ⚠️ **offline_server.py** - 上传和Docker路径
6. ⚠️ **config/machine_config.json** - SSH密钥路径

### 🟢 P2 - 可选修复（测试脚本）
7. ⚠️ 所有测试脚本的SSH密钥路径
8. ⚠️ restart_services.sh 项目路径

---

## 🎯 打包前必须完成的任务

### 任务清单

- [x] 离线感知程序迁移到 `bin/`
- [x] 夜间测试程序迁移到 `night_offline_debug/`
- [x] DNN库迁移到 `lib/dnn_x86/`
- [x] 模型文件迁移到 `models/`
- [x] SSH密钥迁移到 `data/conf/`
- [x] 数据目录结构完整
- [x] `offline_server.py` 使用相对路径
- [ ] 修复 `vite.config.ts` 硬编码路径
- [ ] 修复 `package.json` Node路径
- [ ] 修复 `ssh_bridge.py` 上传路径
- [ ] 修复 `offline_server.py` 上传路径
- [ ] 修复 `config/machine_config.json` SSH密钥路径
- [ ] 创建 `data/uploads/` 目录
- [ ] 测试所有功能正常

---

## 📦 打包建议

### 1. 需要打包的内容
```
perception_streaming-master/
├── bin/                    ✅ 可执行文件
├── lib/                    ✅ 动态库
├── models/                 ✅ AI模型
├── night_offline_debug/    ✅ 夜间测试
├── offline_perception_debug_src/  ✅ 源代码备份
├── data/
│   ├── conf/              ✅ 配置和密钥
│   ├── bag_debug/         ⚠️ 可选（数据量大）
│   ├── log_debug/         ⚠️ 可选（数据量大）
│   ├── stereo_debug/      ⚠️ 可选（数据量大）
│   └── uploads/           ✅ 空目录
├── robot_monitor/         ✅ Python服务
├── src/                   ✅ 前端代码
├── config/                ✅ 配置文件
├── script/                ✅ 脚本
├── public/                ✅ 静态资源
├── package.json           ✅ 依赖配置
├── vite.config.ts         ✅ Vite配置
├── tsconfig.json          ✅ TS配置
├── start.sh               ✅ 启动脚本
└── README.md              ✅ 文档
```

### 2. 排除的内容
```
- node_modules/            # 目标机器重新 npm install
- .git/                    # Git历史（可选保留）
- .claude/                 # Claude配置
- dist/                    # 构建产物
- data/bag_debug/          # 数据文件（可选）
- data/log_debug/          # 数据文件（可选）
- data/stereo_debug/       # 数据文件（可选）
- **/__pycache__/          # Python缓存
- **/*.pyc                 # Python字节码
- **/*.log                 # 日志文件
- **/cmake-build-debug/    # CMake构建缓存
```

### 3. 打包命令建议
```bash
tar -czf perception_streaming_$(date +%Y%m%d).tar.gz \
  --exclude='node_modules' \
  --exclude='.git' \
  --exclude='dist' \
  --exclude='data/bag_debug' \
  --exclude='data/log_debug' \
  --exclude='data/stereo_debug' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.log' \
  --exclude='cmake-build-debug' \
  --exclude='.claude' \
  perception_streaming-master-*/
```

---

## 🚀 部署到新机器的步骤

### 1. 系统要求
- **操作系统**: Ubuntu 20.04+ / Linux
- **Python**: 3.8+
- **Node.js**: 18+
- **依赖库**: OpenCV 4.5+, PCL 1.12+

### 2. 部署步骤
```bash
# 1. 解压项目
tar -xzf perception_streaming_20260421.tar.gz
cd perception_streaming-master-*/

# 2. 安装Python依赖
pip3 install paramiko websockets Pillow

# 3. 安装Node依赖
npm install

# 4. 修改配置文件
# 编辑 data/conf/ssh_config.json 更新远程机器信息

# 5. 创建上传目录
mkdir -p data/uploads

# 6. 设置SSH密钥权限
chmod 600 data/conf/bestmow_rsa_202604

# 7. 设置可执行文件权限
chmod +x bin/*
chmod +x night_offline_debug/build/*

# 8. 启动服务
./start.sh
```

### 3. 验证清单
- [ ] 前端可以访问 (http://localhost:5173)
- [ ] SSH连接正常
- [ ] 离线测试功能正常 (Mode 0-6)
- [ ] 夜间测试功能正常 (Mode 7)
- [ ] 日志拉取功能正常
- [ ] Bag包分析功能正常
- [ ] 双目分析功能正常

---

## 📊 项目统计

### 文件大小统计
- **可执行文件**: ~3.1MB (bin/ + night_offline_debug/)
- **动态库**: ~12.5MB (lib/dnn_x86/)
- **AI模型**: ~43MB (models/)
- **源代码**: ~2MB
- **前端代码**: ~5MB (src/ + public/)
- **Node依赖**: ~200MB (node_modules/, 需重新安装)
- **数据文件**: 可变（data/目录，可选打包）

### 预计打包大小
- **不含数据**: ~70MB
- **含数据**: 根据数据量，可能 500MB - 5GB

---

## ⚡ 快速修复脚本

我可以帮你创建一个自动修复脚本，一键修复所有P0和P1的硬编码路径问题。需要我创建吗？
