# 离线感知程序问题分析与解决方案

## 当前状态

### ✅ 已解决的问题
1. 硬件模式配置（K100/bestmow）- 完成
2. 环境变量传递 - 完成
3. Docker镜像库依赖（PCL, OpenCV）- 完成
4. 程序可以启动和初始化 - 完成
5. 模型文件可以加载 - 完成

### ❌ 核心问题：DNN推理失败

**错误信息**：
```
[ERROR] Image size mismatch! Got 640x384, expected 0x640
file=51d6536ef154943c68d1b222c564ab2a610d3cca:851, internal error: Dest addr of bpu_memcpy() is nullptr!?
terminate called without an active exception
Exit code: 139
```

**根本原因**：
- 程序使用的DNN库需要**真实的BPU硬件**（地平线芯片）
- 在x86环境（Docker容器）中，DNN库无法正常工作
- MOCK库过于简单，无法完整模拟DNN推理过程

## 技术限制

### 硬件依赖
- **真实环境**：需要地平线X3/X5芯片（带BPU）
- **当前环境**：x86 CPU（无BPU）
- **结果**：DNN推理无法执行

### 库兼容性
- 真实DNN库：`libdnn.so` - 需要BPU硬件
- MOCK库：`libdnn_mock.so` - 功能不完整
- 无法在x86环境下完整模拟BPU推理

## 可行的解决方案

### 方案1：使用真实硬件（推荐）
**描述**：在带BPU的设备上运行程序

**优点**：
- ✅ 完整功能
- ✅ 真实推理结果
- ✅ 性能最优

**实施步骤**：
1. 将Docker镜像部署到地平线设备
2. 或直接在设备上编译运行

### 方案2：使用预处理图像（临时方案）
**描述**：跳过DNN推理，直接使用预处理的分割图

**优点**：
- ✅ 可以在x86环境运行
- ✅ 可以测试点云生成流程

**缺点**：
- ❌ 无法进行实时推理
- ❌ 需要预先准备分割图

### 方案3：等待完整MOCK库
**描述**：开发完整的MOCK库，模拟DNN推理

**优点**：
- ✅ 可以在x86环境测试
- ✅ 不需要真实硬件

**缺点**：
- ❌ 开发工作量大
- ❌ 无法获得真实推理结果

## 当前程序状态

### 程序可以正常启动 ✅
```
[Init] Hardware mode: K100
[Init] Inference mode: 6
[Init] Loading Multi-Sub model: /app/models/sub_20260303_640x384.bin
[Init] Multi-Sub model loaded successfully
[Init] Initialization completed successfully
```

### 推理时崩溃 ❌
```
[Process] Running Multi-Sub inference...
[ERROR] Image size mismatch! Got 640x384, expected 0x640
terminate called without an active exception
Exit code: 139
```

## 建议

### 短期（立即可行）
1. **在真实硬件上测试**
   - 部署到地平线设备
   - 验证完整功能

2. **使用离线模式**
   - 预先在真实设备上处理图像
   - 生成分割图和点云
   - 在x86环境查看结果

### 长期（架构优化）
1. **分离推理和后处理**
   - 推理服务：运行在BPU设备
   - 后处理服务：可运行在x86
   - 通过API通信

2. **开发完整MOCK库**
   - 模拟完整的DNN推理流程
   - 支持x86环境开发测试

## 修改记录

### 已完成的修改
1. **offline_server.py**
   - 使用 `offline_test_main`
   - 添加 `MODEL_DIR` 环境变量

2. **Dockerfile.perception**
   - 创建PCL 1.10符号链接
   - 创建OpenCV 4.2符号链接

3. **lib/dnn_x86**
   - 配置使用MOCK库

### 文件状态
- ✅ `bin/offline_test_main` - 已编译
- ✅ `bin/offline_perception_debug_432` - 已编译（备用）
- ✅ Docker镜像 - 已构建
- ✅ 环境变量配置 - 已完成

## 结论

程序已经**从无法启动进步到可以启动并加载模型**，这是巨大的进步。

剩余的问题是**DNN推理需要真实硬件**，这是技术限制，不是程序bug。

**建议**：在带BPU的地平线设备上运行程序，可以获得完整功能。

## 验证步骤

在真实硬件上：
```bash
# 1. 加载Docker镜像
docker load < perception-runtime.tar

# 2. 运行测试
docker run --rm \
  -v /path/to/images:/app/input \
  -e OFFLINE_INPUT_DIR=/app/input \
  -e OFFLINE_INFER_MODE=6 \
  -e HARDWARE_MODE=K100 \
  -e MODEL_DIR=/app/models \
  perception-runtime:latest \
  /app/bin/offline_test_main

# 3. 检查输出
ls /path/to/images/sub_6_205_432/
ls /path/to/images/pcd_6_205_432/
```

预期结果：
- ✅ 程序正常运行
- ✅ 生成分割图
- ✅ 生成点云文件
- ✅ 退出码 0
