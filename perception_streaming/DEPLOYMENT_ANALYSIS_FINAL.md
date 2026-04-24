# 项目外部依赖最终分析报告

## 检查日期
2026-04-21

## 一、已完成的迁移工作 ✅

### 1.1 数据目录结构（已迁移到项目内）
```
data/
├── conf/                          # 配置文件 ✅
│   ├── bestmow_rsa_202604        # SSH密钥（已迁移）
│   ├── ssh_config.json           # SSH配置（已配置化）
│   └── README.md
├── bag_debug/                     # Bag包分析数据 ✅
│   └── 0111/0327/...
├── log_debug/                     # 日志分析数据 ✅
│   └── 0123/20260413/...
├── stereo_debug/                  # 双目分析数据 ✅
│   └── 0286/20260415/...
└── visualization/                 # 可视化数据 ✅
    └── 0327/...
```

### 1.2 夜间离线测试程序（已迁移到项目内）
```
night_offline_debug/               # 夜间离线调试 ✅
├── build/
│   └── run_cdt_dsg_fusion_dir    # 可执行文件（已编译）
├── model/
│   ├── dsg_multi_20260401_640x384.bin  # 模型文件（已迁移）
│   └── night_0331_167.bin              # 模型文件（已迁移）
├── data/
│   ├── input/                     # 输入数据目录
│   └── output/                    # 输出结果目录
├── include/                       # 头文件
├── src/                          # 源代码
└── CMakeLists.txt
```

### 1.3 配置文件化（已实现）
- ✅ `data/conf/ssh_config.json` - SSH连接配置
- ✅ `robot_monitor/config_loader.py` - 配置加载器
- ✅ `config/machine_config.json` - 机器配置

## 二、仍需处理的外部依赖 ⚠️

### 2.1 关键外部依赖（必须处理）

#### A. 离线感知调试程序（未迁移）
**位置**: `robot_monitor/offline_server.py:37-42`

```python
# ❌ 仍然指向外部路径
OFFLINE_EXE = "/home/youfeng/CLionProjects/07_openclaw_auto/claude_project/offline_perception_debug/build/offline_perception_debug_432"
OFFLINE_LIB = "/home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/lib"
MONO_EXE = "/home/youfeng/CLionProjects/05-offline_debug_fusion/offline_perception_debug/cmake-build-debug/dsg_mono_perception"
MONO_MODEL = "/home/youfeng/CLionProjects/05-offline_debug_fusion/offline_perception_debug/models/dsg_multi_20260407_640x384.bin"
DSG_MODEL = "/home/youfeng/CLionProjects/05-offline_debug_fusion/offline_perception_debug/models/dsg_multi_20260407_640x384.bin"
```

**影响功能**:
- Mode 5: Multi-task 离线测试
- Mode 6: Sub-perception 离线测试
- Mode 1-4: 其他离线测试模式

**建议方案**: 创建 `offline_perception_debug/` 目录，类似 `night_offline_debug/`

#### B. DNN动态库（未迁移）
**当前路径**: `/home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/lib`

**依赖库**:
- `libdnn.so` - DNN推理核心库
- `libhbdk_sim_x86.so` - 地平线BPU模拟库（当前缺失）

**影响**: 所有离线感知测试功能都依赖此库

**建议方案**: 
```
项目根目录/
└── deps/
    └── dnn_x86/
        └── lib/
            ├── libdnn.so
            └── libhbdk_sim_x86.so
```

#### C. Python解释器路径（硬编码）
**位置**: `vite.config.ts:10`

```typescript
const PYTHON = '/home/youfeng/anaconda3/bin/python3'  // ❌ 硬编码
```

**建议方案**: 改为 `process.env.PYTHON || 'python3'`

#### D. Node.js路径（硬编码）
**位置**: `package.json:7-9`

```json
"dev": "/home/youfeng/.nvm/versions/node/v24.13.0/bin/node node_modules/vite/bin/vite.js"
```

**建议方案**: 改为 `"dev": "vite"`

### 2.2 次要外部依赖（可选处理）

#### E. 本地上传目标目录
**位置**: `robot_monitor/ssh_bridge.py:53, 994, 1420`

```python
BULK_UPLOAD_DEST = "/home/youfeng/debug/03/claude_bag"
upload_dest = f"/home/youfeng/debug/boluo/{port_suffix}/rosbag"
local_dest = f"/home/youfeng/debug/03/{date}"
```

**建议方案**: 改为项目内 `data/uploads/` 或通过配置文件指定

#### F. 监控脚本路径
**位置**: `robot_monitor/ssh_bridge.py:1229-1230`

```python
local_script = "/home/youfeng/CLionProjects/07_openclaw_auto/project/perception_streaming-master-80b4b0d5e580c3b80e50eea2d3719aad56d8d808/script/monitor_mow_obstacle.sh"
local_service = "/home/youfeng/CLionProjects/07_openclaw_auto/project/perception_streaming-master-80b4b0d5e580c3b80e50eea2d3719aad56d8d808/script/monitor_mow_obstacle.service"
```

**建议方案**: 改为相对路径 `PROJECT_ROOT / "script/..."`

#### G. Docker交叉编译目录
**位置**: `robot_monitor/offline_server.py:2380, 2409-2411`

```python
cross_compile_dir = "/home/youfeng/CLionProjects/07_openclaw_auto/project/cross_compile/"
'-v', '/home/youfeng/CLionProjects/10-rdkx5/docker_packages/data/:/data',
'-v', '/home/youfeng/CLionProjects/12-evb/project/:/offline_debug',
```

**建议方案**: 通过环境变量或配置文件指定

#### H. 测试脚本中的SSH密钥
**位置**: 多个测试脚本

```bash
# test_rsync_fix.sh, test_sftp_fix.sh, test_scp_upload.sh
SSH_KEY="/home/youfeng/CLionProjects/12-evb/evb_test/ssh/bestmow_rsa_202604"
```

**建议方案**: 改为 `data/conf/bestmow_rsa_202604`

### 2.3 配置文件中的遗留路径

#### I. machine_config.json
**位置**: `config/machine_config.json:7`

```json
"ssh_key": "/home/youfeng/CLionProjects/12-evb/evb_test/ssh/bestmow_rsa_202604"
```

**建议方案**: 改为相对路径 `"../data/conf/bestmow_rsa_202604"`

## 三、优先级分级

### 🔴 P0 - 必须立即处理（阻塞部署）

1. **离线感知调试程序迁移**
   - 创建 `offline_perception_debug/` 目录
   - 复制可执行文件、模型文件
   - 更新 `offline_server.py` 中的路径

2. **DNN动态库迁移**
   - 创建 `deps/dnn_x86/lib/` 目录
   - 复制所有 `.so` 文件
   - 更新 `OFFLINE_LIB` 路径

3. **Python和Node.js路径去硬编码**
   - 修改 `vite.config.ts`
   - 修改 `package.json`

### 🟡 P1 - 建议处理（影响便利性）

4. **上传目录配置化**
   - 添加到 `ssh_config.json`
   - 更新 `ssh_bridge.py`

5. **监控脚本路径相对化**
   - 使用 `PROJECT_ROOT` 变量

6. **测试脚本更新**
   - 更新所有 `.sh` 文件中的路径

### 🟢 P2 - 可选处理（不影响核心功能）

7. **Docker交叉编译配置化**
8. **machine_config.json 路径更新**

## 四、推荐的目录结构

```
perception_streaming-master/
├── bin/                           # 【新增】可执行文件目录
│   └── offline_perception_debug_432
├── deps/                          # 【新增】依赖库目录
│   └── dnn_x86/
│       └── lib/
│           ├── libdnn.so
│           └── libhbdk_sim_x86.so
├── models/                        # 【新增】共享模型目录
│   └── dsg_multi_20260407_640x384.bin
├── data/                          # ✅ 已完成
│   ├── conf/                      # ✅ 配置文件
│   ├── bag_debug/                 # ✅ Bag分析数据
│   ├── log_debug/                 # ✅ 日志分析数据
│   ├── stereo_debug/              # ✅ 双目分析数据
│   ├── visualization/             # ✅ 可视化数据
│   └── uploads/                   # 【新增】上传目标目录
├── night_offline_debug/           # ✅ 已完成
│   ├── build/
│   ├── model/
│   └── data/
├── offline_perception_debug/      # 【待创建】离线感知调试
│   ├── build/
│   ├── models/
│   └── data/
├── robot_monitor/                 # Python服务
├── src/                          # 前端代码
├── script/                       # 脚本文件
├── config/                       # 配置文件
└── node_modules/                 # Node依赖
```

## 五、迁移检查清单

### 已完成 ✅
- [x] SSH密钥迁移到 `data/conf/`
- [x] SSH配置文件化 (`ssh_config.json`)
- [x] 配置加载器实现 (`config_loader.py`)
- [x] Bag分析数据迁移到 `data/bag_debug/`
- [x] 日志分析数据迁移到 `data/log_debug/`
- [x] 双目分析数据迁移到 `data/stereo_debug/`
- [x] 夜间离线测试迁移到 `night_offline_debug/`
- [x] 夜间测试模型文件迁移

### 待完成 ⚠️
- [ ] 创建 `offline_perception_debug/` 目录
- [ ] 复制离线感知可执行文件到项目内
- [ ] 创建 `deps/dnn_x86/lib/` 目录
- [ ] 复制DNN动态库到项目内
- [ ] 复制共享模型文件到 `models/`
- [ ] 更新 `offline_server.py` 中的路径变量
- [ ] 更新 `vite.config.ts` 中的Python路径
- [ ] 更新 `package.json` 中的Node路径
- [ ] 更新 `ssh_bridge.py` 中的上传目录
- [ ] 更新所有测试脚本中的SSH密钥路径
- [ ] 更新 `machine_config.json` 中的SSH密钥路径
- [ ] 创建 `data/uploads/` 目录
- [ ] 创建路径配置文件 `data/conf/paths_config.json`

## 六、部署验证步骤

### 本地验证
1. 检查所有外部路径是否已迁移
2. 运行 `grep -r "/home/youfeng" --include="*.py" --include="*.ts" --include="*.json"`
3. 测试所有离线测试模式（Mode 1-7）
4. 测试SSH连接和日志拉取
5. 测试Bag包分析功能

### 打包验证
1. 创建打包脚本排除 `node_modules/`, `.git/`
2. 在新目录解压测试
3. 检查所有相对路径是否正确
4. 验证配置文件加载

### 远程部署验证
1. 上传到新机器
2. 安装依赖 (`npm install`, `pip install -r requirements.txt`)
3. 更新 `data/conf/ssh_config.json` 中的远程机器信息
4. 启动服务并测试所有功能

## 七、风险评估

### 高风险项
1. **DNN库依赖**: `libhbdk_sim_x86.so` 当前缺失，可能影响推理功能
2. **动态库版本**: 目标机器的glibc版本必须兼容
3. **OpenCV版本**: 需要OpenCV 4.5+

### 中风险项
1. **Python版本**: 建议Python 3.8+
2. **Node.js版本**: 建议Node.js 18+
3. **网络配置**: 需要访问远程机器人

### 低风险项
1. **端口占用**: 8765-8769端口
2. **文件权限**: SSH密钥需要600权限
3. **磁盘空间**: 数据目录可能较大

## 八、下一步行动建议

### 立即执行（P0）
1. 创建 `offline_perception_debug/` 和 `deps/` 目录结构
2. 复制所有外部可执行文件和库到项目内
3. 创建 `data/conf/paths_config.json` 配置文件
4. 更新 `offline_server.py` 使用配置文件加载路径
5. 更新 `vite.config.ts` 和 `package.json` 去除硬编码路径

### 后续执行（P1-P2）
6. 更新所有测试脚本
7. 创建部署脚本和打包脚本
8. 编写完整的部署文档
9. 在测试环境验证完整部署流程

## 九、总结

### 当前状态
- **已完成**: 约60%的迁移工作
  - 数据目录结构完整
  - SSH配置已配置化
  - 夜间离线测试已迁移
  
- **待完成**: 约40%的关键依赖
  - 离线感知调试程序（核心功能）
  - DNN动态库（核心依赖）
  - 路径硬编码清理

### 预计工作量
- **P0任务**: 2-3小时
- **P1任务**: 1-2小时
- **P2任务**: 1小时
- **总计**: 4-6小时

### 部署可行性
完成P0任务后，项目即可打包部署到其他机器。P1和P2任务主要影响便利性和维护性，不阻塞核心功能。
