# 项目部署迁移清单

## 一、外部依赖分析

### 1. 硬编码的绝对路径

#### 1.1 C++ 可执行文件和库
**位置**: `robot_monitor/offline_server.py:35-40`

```python
OFFLINE_EXE = "/home/youfeng/CLionProjects/07_openclaw_auto/claude_project/offline_perception_debug/build/offline_perception_debug_432"
NIGHT_EXE = "/home/youfeng/CLionProjects/07_openclaw_auto/claude_project/night_test/build/run_cdt_dsg_fusion_dir"
OFFLINE_LIB = "/home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/lib"
MONO_EXE = "/home/youfeng/CLionProjects/05-offline_debug_fusion/offline_perception_debug/cmake-build-debug/dsg_mono_perception"
MONO_MODEL = "/home/youfeng/CLionProjects/05-offline_debug_fusion/offline_perception_debug/models/dsg_multi_20260407_640x384.bin"
DSG_MODEL = "/home/youfeng/CLionProjects/05-offline_debug_fusion/offline_perception_debug/models/dsg_multi_20260407_640x384.bin"
```

**迁移方案**:
- 将可执行文件移到 `bin/` 目录
- 将动态库移到 `lib/` 目录
- 将模型文件移到 `models/` 目录

#### 1.2 Python 解释器路径
**位置**: `vite.config.ts:10`

```typescript
const PYTHON = '/home/youfeng/anaconda3/bin/python3'
```

**迁移方案**: 改为使用系统 Python 或虚拟环境

#### 1.3 SSH 密钥路径
**位置**: `vite.config.ts:11`

```typescript
const SSH_KEY = '/home/youfeng/CLionProjects/12-evb/evb_test/ssh/bestmow_rsa_202604'
```

**迁移方案**: 移到 `data/conf/` 目录，通过配置文件加载

#### 1.4 Node.js 路径
**位置**: `package.json:7-9`

```json
"dev": "/home/youfeng/.nvm/versions/node/v24.13.0/bin/node node_modules/vite/bin/vite.js"
```

**迁移方案**: 改为使用 `node` 命令（依赖 PATH）

#### 1.5 Bag 数据目录
**位置**: `vite.config.ts:176`

```typescript
const BAG_DATA_DIR = process.env.BAG_DATA_DIR ?? '/home/youfeng/CLionProjects/07_openclaw_auto/project/...'
```

**迁移方案**: 改为项目内相对路径 `data/bag_debug/`

#### 1.6 上传目标目录
**位置**: `robot_monitor/ssh_bridge.py:53`

```python
BULK_UPLOAD_DEST = "/home/youfeng/debug/03/claude_bag"
```

**迁移方案**: 改为配置文件或环境变量

### 2. 远程机器依赖

#### 2.1 SSH 连接配置
**位置**: `vite.config.ts:12-14`, `config/machine_config.json`

```typescript
const REMOTE_HOST = '120.25.121.3'
const REMOTE_PORT = '10015'
```

**迁移方案**: 已通过 `config_loader.py` 和 `data/conf/ssh_config.json` 实现配置化

#### 2.2 远程脚本路径
**位置**: `robot_monitor/ssh_bridge.py:45-46`

```python
SCRIPT_PATH = "/app/BestMow/debug_sh/rosbag_record_perception_navigation.sh"
REMOTE_BAG_DIR = "/userdata/rosbag_record"
```

**迁移方案**: 移到配置文件

### 3. 外部服务端口

- **8765**: SSH Bridge WebSocket
- **8766**: PCL Proxy WebSocket
- **8767**: 远程 PCL WebSocket Bridge
- **8768**: SSH Tunnel 本地端口
- **8769**: Offline Server HTTP

## 二、迁移步骤

### 步骤 1: 创建标准目录结构

```bash
project_root/
├── bin/                    # 可执行文件
│   ├── offline_perception_debug_432
│   ├── run_cdt_dsg_fusion_dir
│   └── dsg_mono_perception
├── lib/                    # 动态库
│   └── dnn_x86/
│       └── lib/
├── models/                 # AI 模型文件
│   └── dsg_multi_20260407_640x384.bin
├── data/
│   ├── conf/              # 配置文件
│   │   ├── ssh_config.json
│   │   └── bestmow_rsa_202604
│   └── bag_debug/         # Bag 数据
├── robot_monitor/         # Python 服务
├── src/                   # 前端代码
└── node_modules/          # Node 依赖
```

### 步骤 2: 修改配置文件

#### 2.1 创建 `data/conf/ssh_config.json`

```json
{
  "ssh_key_path": "bestmow_rsa_202604",
  "ssh_host": "120.25.121.3",
  "ssh_user": "root",
  "default_ports": {
    "realtime_monitor": 10015,
    "log_fetch": 10123,
    "stereo_analysis": 10123
  },
  "remote_paths": {
    "record_script": "/app/BestMow/debug_sh/rosbag_record_perception_navigation.sh",
    "bag_dir": "/userdata/rosbag_record",
    "log_base": "/userdata/log_dir/ros2_log",
    "image_base": "/userdata/bestmow_data/image_save_path"
  }
}
```

#### 2.2 创建 `data/conf/paths_config.json`

```json
{
  "executables": {
    "offline_perception": "bin/offline_perception_debug_432",
    "night_test": "bin/run_cdt_dsg_fusion_dir",
    "mono_perception": "bin/dsg_mono_perception"
  },
  "libraries": {
    "dnn_x86": "lib/dnn_x86/lib"
  },
  "models": {
    "dsg_multi": "models/dsg_multi_20260407_640x384.bin"
  },
  "data_dirs": {
    "bag_data": "data/bag_debug",
    "bag_files": "bags",
    "upload_dest": "data/uploads"
  }
}
```

### 步骤 3: 修改 Python 代码

#### 3.1 更新 `robot_monitor/offline_server.py`

在文件开头添加路径配置加载:

```python
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).parent.parent
CONF_DIR = PROJECT_ROOT / "data" / "conf"

def load_paths_config():
    config_file = CONF_DIR / "paths_config.json"
    if not config_file.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_file}")
    with open(config_file, 'r') as f:
        return json.load(f)

paths = load_paths_config()

OFFLINE_EXE = str(PROJECT_ROOT / paths["executables"]["offline_perception"])
NIGHT_EXE = str(PROJECT_ROOT / paths["executables"]["night_test"])
OFFLINE_LIB = str(PROJECT_ROOT / paths["libraries"]["dnn_x86"])
MONO_EXE = str(PROJECT_ROOT / paths["executables"]["mono_perception"])
DSG_MODEL = str(PROJECT_ROOT / paths["models"]["dsg_multi"])
MONO_MODEL = DSG_MODEL
BAG_DATA_DIR = os.environ.get("BAG_DATA_DIR", str(PROJECT_ROOT / paths["data_dirs"]["bag_data"]))
```

#### 3.2 更新 `robot_monitor/ssh_bridge.py`

```python
from config_loader import get_ssh_key_path, get_ssh_host, get_ssh_user, get_remote_path

SCRIPT_PATH = get_remote_path("record_script")
REMOTE_BAG_DIR = get_remote_path("bag_dir")
BULK_UPLOAD_DEST = str(PROJECT_ROOT / "data" / "uploads")
```

#### 3.3 更新 `robot_monitor/config_loader.py`

添加远程路径加载函数:

```python
def get_remote_path(key: str) -> str:
    """获取远程路径配置"""
    config = load_ssh_config()
    remote_paths = config.get("remote_paths", {})
    
    defaults = {
        "record_script": "/app/BestMow/debug_sh/rosbag_record_perception_navigation.sh",
        "bag_dir": "/userdata/rosbag_record",
        "log_base": "/userdata/log_dir/ros2_log",
        "image_base": "/userdata/bestmow_data/image_save_path"
    }
    
    return remote_paths.get(key, defaults.get(key, ""))
```

### 步骤 4: 修改前端配置

#### 4.1 更新 `vite.config.ts`

```typescript
import { fileURLToPath } from 'url'
import path from 'path'
import fs from 'fs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// 加载配置
const confDir = path.resolve(__dirname, 'data/conf')
const sshConfig = JSON.parse(fs.readFileSync(path.join(confDir, 'ssh_config.json'), 'utf-8'))
const pathsConfig = JSON.parse(fs.readFileSync(path.join(confDir, 'paths_config.json'), 'utf-8'))

const PYTHON = process.env.PYTHON || 'python3'
const SSH_KEY = path.resolve(confDir, sshConfig.ssh_key_path)
const REMOTE_HOST = sshConfig.ssh_host
const REMOTE_PORT = String(sshConfig.default_ports.realtime_monitor)
const BAG_DATA_DIR = process.env.BAG_DATA_DIR || path.resolve(__dirname, pathsConfig.data_dirs.bag_data)
```

#### 4.2 更新 `package.json`

```json
{
  "scripts": {
    "dev": "node node_modules/vite/bin/vite.js",
    "build": "node node_modules/vite/bin/vite.js build",
    "preview": "node node_modules/vite/bin/vite.js preview"
  }
}
```

### 步骤 5: 创建部署脚本

#### 5.1 创建 `deploy_prepare.sh`

```bash
#!/bin/bash
# 部署准备脚本 - 收集所有外部依赖到项目内

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "项目根目录: $PROJECT_ROOT"

# 创建目录结构
mkdir -p "$PROJECT_ROOT/bin"
mkdir -p "$PROJECT_ROOT/lib/dnn_x86/lib"
mkdir -p "$PROJECT_ROOT/models"
mkdir -p "$PROJECT_ROOT/data/conf"
mkdir -p "$PROJECT_ROOT/data/bag_debug"
mkdir -p "$PROJECT_ROOT/data/uploads"

# 复制可执行文件
echo "复制可执行文件..."
cp /home/youfeng/CLionProjects/07_openclaw_auto/claude_project/offline_perception_debug/build/offline_perception_debug_432 "$PROJECT_ROOT/bin/" || echo "警告: offline_perception_debug_432 不存在"
cp /home/youfeng/CLionProjects/07_openclaw_auto/claude_project/night_test/build/run_cdt_dsg_fusion_dir "$PROJECT_ROOT/bin/" || echo "警告: run_cdt_dsg_fusion_dir 不存在"
cp /home/youfeng/CLionProjects/05-offline_debug_fusion/offline_perception_debug/cmake-build-debug/dsg_mono_perception "$PROJECT_ROOT/bin/" || echo "警告: dsg_mono_perception 不存在"

# 复制动态库
echo "复制动态库..."
cp -r /home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/lib/* "$PROJECT_ROOT/lib/dnn_x86/lib/" || echo "警告: 动态库不存在"

# 复制模型文件
echo "复制模型文件..."
cp /home/youfeng/CLionProjects/05-offline_debug_fusion/offline_perception_debug/models/dsg_multi_20260407_640x384.bin "$PROJECT_ROOT/models/" || echo "警告: 模型文件不存在"

# 复制 SSH 密钥
echo "复制 SSH 密钥..."
cp /home/youfeng/CLionProjects/12-evb/evb_test/ssh/bestmow_rsa_202604 "$PROJECT_ROOT/data/conf/" || echo "警告: SSH 密钥不存在"
chmod 600 "$PROJECT_ROOT/data/conf/bestmow_rsa_202604"

# 设置可执行权限
chmod +x "$PROJECT_ROOT/bin/"*

echo "部署准备完成！"
echo ""
echo "下一步:"
echo "1. 检查 data/conf/ssh_config.json 配置"
echo "2. 检查 data/conf/paths_config.json 配置"
echo "3. 运行 npm install"
echo "4. 运行 ./start.sh 启动服务"
```

#### 5.2 创建 `pack_for_deployment.sh`

```bash
#!/bin/bash
# 打包脚本 - 打包整个项目用于迁移

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PACKAGE_NAME="perception_streaming_${TIMESTAMP}.tar.gz"

echo "开始打包项目..."

# 排除不需要的文件
tar -czf "$PACKAGE_NAME" \
  --exclude='node_modules' \
  --exclude='.git' \
  --exclude='*.log' \
  --exclude='__pycache__' \
  --exclude='.claude' \
  --exclude='data/bag_debug/*' \
  -C "$(dirname "$PROJECT_ROOT")" \
  "$(basename "$PROJECT_ROOT")"

echo "打包完成: $PACKAGE_NAME"
echo "文件大小: $(du -h "$PACKAGE_NAME" | cut -f1)"
echo ""
echo "部署到新机器的步骤:"
echo "1. 上传 $PACKAGE_NAME 到目标机器"
echo "2. tar -xzf $PACKAGE_NAME"
echo "3. cd perception_streaming-master-*"
echo "4. 编辑 data/conf/ssh_config.json (更新 SSH 配置)"
echo "5. npm install"
echo "6. pip3 install -r requirements.txt"
echo "7. ./start.sh"
```

### 步骤 6: 创建依赖文档

#### 6.1 创建 `requirements.txt`

```
paramiko>=3.0.0
websockets>=12.0
Pillow>=10.0.0
```

#### 6.2 创建 `DEPLOYMENT.md`

详细的部署文档，包含:
- 系统要求
- 依赖安装
- 配置说明
- 启动步骤
- 故障排查

## 三、验证清单

### 本地验证
- [ ] 所有可执行文件已复制到 `bin/`
- [ ] 所有动态库已复制到 `lib/`
- [ ] 所有模型文件已复制到 `models/`
- [ ] SSH 密钥已复制到 `data/conf/`
- [ ] 配置文件已创建并正确填写
- [ ] Python 代码已更新为使用相对路径
- [ ] TypeScript 配置已更新
- [ ] `package.json` 已移除硬编码路径
- [ ] 启动脚本可以正常运行
- [ ] 所有功能正常工作

### 迁移验证
- [ ] 打包文件已生成
- [ ] 在新机器上解压成功
- [ ] 配置文件已根据新环境更新
- [ ] 依赖安装成功
- [ ] 服务启动成功
- [ ] 前端可以访问
- [ ] SSH 连接正常
- [ ] 离线测试功能正常
- [ ] 日志拉取功能正常
- [ ] Bag 回放功能正常

## 四、注意事项

1. **SSH 密钥安全**: 确保 SSH 密钥权限为 600
2. **动态库依赖**: 确保目标机器有相同的 glibc 版本
3. **Python 版本**: 建议使用 Python 3.8+
4. **Node.js 版本**: 建议使用 Node.js 18+
5. **网络配置**: 确保目标机器可以访问远程机器人
6. **端口占用**: 确保 8765-8769 端口未被占用
7. **文件权限**: 确保可执行文件有执行权限
8. **环境变量**: 可通过 `.env` 文件覆盖默认配置

## 五、环境变量支持

创建 `.env` 文件支持运行时配置覆盖:

```bash
# Python 解释器
PYTHON=python3

# Bag 数据目录
BAG_DATA_DIR=/path/to/bag/data

# 上传目标目录
UPLOAD_DEST=/path/to/uploads

# SSH 配置覆盖
SSH_HOST=192.168.1.100
SSH_PORT=22
SSH_USER=root
```
