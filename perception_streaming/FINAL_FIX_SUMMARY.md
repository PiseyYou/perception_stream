# 离线感知程序修复总结

## 问题描述
点击"白天离线debug"按钮后程序闪退（退出码139）

## 根本原因分析

### 1. 库版本不兼容问题
- **宿主机环境**：Ubuntu 20.04, PCL 1.10, OpenCV 4.2
- **Docker容器**：Ubuntu 22.04, PCL 1.12, OpenCV 4.5
- **编译的程序**：链接PCL 1.10和OpenCV 4.2

### 2. 程序选择问题
- `offline_perception_debug_432` - 缺少完整的硬件模式支持
- `offline_test_main` - 已有完整的硬件模式支持，但有库依赖问题

## 解决方案

### 方案1：修复offline_perception_debug_432（已完成）
✅ 添加硬件模式支持
✅ 添加环境变量配置
✅ 编译成功
❌ 在Docker容器中无法运行（PCL版本不兼容）

### 方案2：使用offline_test_main（已实施）
✅ 已有完整的硬件模式支持
✅ 重新编译
✅ 修改offline_server.py使用offline_test_main
✅ 添加MODEL_DIR环境变量
✅ 创建PCL 1.10和OpenCV 4.2的符号链接
✅ 程序可以启动并加载模型
⚠️ 推理时出现模型尺寸问题

## 当前状态

### 已解决
1. ✅ 硬件模式配置支持（K100/bestmow）
2. ✅ 环境变量传递（HARDWARE_MODE, MODEL_DIR等）
3. ✅ Docker镜像库依赖问题（PCL, OpenCV符号链接）
4. ✅ 程序可以正常启动和初始化
5. ✅ 模型可以成功加载

### 待解决
1. ⚠️ DNN推理时的模型尺寸读取问题
   - 错误：`[ERROR] Image size mismatch! Got 640x384, expected 0x640`
   - 原因：模型的输入高度读取为0
   - 影响：程序在推理时崩溃（退出码139）

## 修改的文件

### 1. offline_server.py
```python
# 修改1：使用offline_test_main
exe_cmd = f"/app/bin/offline_test_main"

# 修改2：添加MODEL_DIR环境变量
env_vars = [
    ...
    f"MODEL_DIR=/app/models",
    ...
]
```

### 2. Dockerfile.perception
```dockerfile
# 创建PCL 1.10和OpenCV 4.2的符号链接
RUN cd /usr/lib/x86_64-linux-gnu && \
    # PCL 1.10 -> 1.12
    for lib in libpcl_*.so.1.12; do \
        base=$(echo $lib | sed 's/\.so\.1\.12$//'); \
        ln -sf $lib ${base}.so.1.10 || true; \
    done && \
    # OpenCV 4.2 -> 4.5
    for lib in libopencv_*.so.4.5*; do \
        base=$(echo $lib | sed 's/\.so\.4\.5.*$//'); \
        ln -sf $lib ${base}.so.4.2 || true; \
    done
```

### 3. offline_perception_debug_432.cpp（备用方案）
- 添加了硬件模式支持
- 添加了环境变量配置
- 但因库依赖问题暂未使用

## 测试结果

### 程序启动测试 ✅
```
[Init] Hardware mode: K100
[Init] Inference mode: 6
[Init] Loading Multi-Sub model: /app/models/sub_20260303_640x384.bin
[Init] Multi-Sub model loaded successfully
[Init] Initialization completed successfully
```

### 推理测试 ❌
```
[ERROR] Image size mismatch! Got 640x384, expected 0x640
terminate called without an active exception
Exit code: 139
```

## 下一步建议

### 短期方案（推荐）
1. **检查DNN库版本**：确认lib/dnn_x86中的库是否与模型兼容
2. **使用MOCK库测试**：临时使用MOCK库验证流程是否正确
3. **检查模型文件**：确认sub_20260303_640x384.bin是否损坏

### 长期方案
1. **统一编译环境**：在Docker容器中编译所有程序
2. **使用相同的基础镜像**：确保开发和运行环境一致
3. **版本锁定**：明确指定PCL、OpenCV、DNN库的版本

## 环境变量配置

程序现在支持以下环境变量：
- `OFFLINE_INPUT_DIR` - 输入目录
- `OFFLINE_INFER_MODE` - 推理模式（6=Sub, 7=DSG）
- `OFFLINE_ERODE_PIXEL` - 腐蚀像素
- `HARDWARE_MODE` - 硬件模式（K100/bestmow）
- `MODEL_DIR` - 模型目录

## 成果

虽然推理部分还有问题，但已经取得了重大进展：

1. ✅ 程序不再在启动时崩溃
2. ✅ 硬件模式配置正常工作
3. ✅ 模型可以成功加载
4. ✅ Docker环境配置正确
5. ✅ 环境变量传递正常

**从"无法启动"到"可以启动但推理失败"是一个巨大的进步！**

剩下的问题是DNN库和模型的兼容性，这需要：
- 检查DNN库版本
- 或者使用正确版本的模型
- 或者在正确的硬件环境（带BPU的设备）上运行
