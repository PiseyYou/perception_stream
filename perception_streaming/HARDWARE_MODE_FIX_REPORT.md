# offline_perception_debug_432 硬件模式修复报告

## 问题描述

点击"白天离线debug"按钮后程序闪退（退出码139，段错误），原因是：
1. `offline_perception_debug_432` 缺少 model==6 的逻辑和硬件模式配置支持
2. 在 Config 结构体中包含 HardwareMode 对象导致内存访问错误

## 问题分析

1. **缺少硬件模式管理**：程序没有硬件模式配置机制
2. **环境变量处理不完整**：虽然读取了 `HARDWARE_MODE` 环境变量，但没有正确设置和传递给其他模块
3. **内存访问错误**：在 Config 结构体中直接包含 HardwareMode 对象，在复制时导致段错误（退出码139）

## 修复方案

### 1. 添加 HardwareMode 类（仅作为参考）

创建文件：`offline_perception_debug_src/include/hardware_mode.hpp`

这个类主要用于文档和参考，实际使用中直接使用布尔值 `use_k100_mode` 来避免对象复制问题。

### 2. 修改 offline_perception_debug_432.cpp

#### 2.1 添加头文件引用
```cpp
#include "hardware_mode.hpp"
```

#### 2.2 在 Config 结构中保留硬件模式标志
```cpp
struct Config {
    // ... 其他配置 ...
    bool use_k100_mode = true;  // 硬件模式标志
    // 注意：不在Config中包含HardwareMode对象，避免复制时的内存问题
};
```

#### 2.3 在 main 函数中添加硬件模式配置逻辑
```cpp
// 读取硬件模式
bool use_k100_mode = true;
if (env_hardware) {
    string hw_str = string(env_hardware);
    std::transform(hw_str.begin(), hw_str.end(), hw_str.begin(), ::tolower);
    use_k100_mode = (hw_str == "k100");
}
config.use_k100_mode = use_k100_mode;

// 设置环境变量供其他模块使用
if (use_k100_mode) {
    setenv("HARDWARE_MODE", "K100", 1);
} else {
    setenv("HARDWARE_MODE", "bestmow", 1);
}
```

#### 2.4 更新配置打印信息
```cpp
cout << "Hardware mode: " << (config.use_k100_mode ? "K100" : "bestmow") << endl;
if (config.use_k100_mode) {
    cout << "  - K100 mode: Full YOLO decoding, adaptive stereo params, ..." << endl;
} else {
    cout << "  - bestmow mode: Simplified label mapping, fixed stereo params, ..." << endl;
}
```

## 关键修复点

### 问题1：段错误（退出码139）
**原因**：在 Config 结构体中包含 HardwareMode 对象，在复制构造时导致内存访问错误。

**解决方案**：
- 移除 Config 结构体中的 `HardwareMode hardware_mode` 对象
- 只保留 `bool use_k100_mode` 标志
- 在需要显示模式描述时，直接使用条件判断输出字符串

### 问题2：环境变量传递
**原因**：其他感知模块需要读取 HARDWARE_MODE 环境变量。

**解决方案**：
- 使用 `setenv()` 显式设置环境变量
- 确保在初始化感知模块前设置好环境变量

```bash
cd offline_perception_debug_src
mkdir -p build && cd build
cmake ..
make -j4
cp offline_perception_debug_432 ../../bin/
```

## 测试结果

### 测试用例

1. **K100 模式 + Mode 6 (Sub)** ✅
2. **K100 模式 + Mode 7 (DSG)** ✅
3. **bestmow 模式 + Mode 6 (Sub)** ✅
4. **bestmow 模式 + Mode 7 (DSG)** ✅
5. **默认模式（无环境变量）** ✅

### 测试命令示例

```bash
# K100 模式
OFFLINE_INPUT_DIR=/path/to/input \
OFFLINE_INFER_MODE=6 \
HARDWARE_MODE=K100 \
./bin/offline_perception_debug_432

# bestmow 模式
OFFLINE_INPUT_DIR=/path/to/input \
OFFLINE_INFER_MODE=7 \
HARDWARE_MODE=bestmow \
./bin/offline_perception_debug_432
```

### 输出示例

```
========== Configuration ==========
Hardware mode: K100
  - K100 mode: Full YOLO decoding, adaptive stereo params, label-aware filtering, morphology post-processing
Inference mode: 6
Erode pixel: 205
Area threshold: 0.5
Detection threshold: 0.2
===================================
```

## 硬件模式说明

### K100 模式
- Full YOLO decoding（完整YOLO解码）
- Adaptive stereo params（自适应立体参数）
- Label-aware filtering（标签感知过滤）
- Morphology post-processing（形态学后处理）

### bestmow 模式
- Simplified label mapping（简化标签映射）
- Fixed stereo params（固定立体参数）
- Generic filtering（通用过滤）
- No morphology（无形态学处理）

## 支持的推理模式

- Mode 0: Disable（禁用）
- Mode 1: Only Depth（仅深度）
- Mode 2: Detection（检测）
- Mode 3: Segmentation（分割）
- Mode 4: Charge Station QR（充电桩二维码）
- Mode 5: Multi-task（多任务）
- Mode 6: Sub-task（子任务）✅ 新增支持
- Mode 7: DSG nighttime（夜间DSG）✅ 新增支持

## 环境变量配置

| 环境变量 | 说明 | 默认值 | 可选值 |
|---------|------|--------|--------|
| OFFLINE_INPUT_DIR | 输入图像目录 | - | 任意有效路径 |
| OFFLINE_INFER_MODE | 推理模式 | 7 | 0-7 |
| OFFLINE_ERODE_PIXEL | 腐蚀像素 | 205 | 任意整数 |
| HARDWARE_MODE | 硬件模式 | K100 | K100, bestmow |
| DSG_MODEL_PATH | DSG模型路径 | - | 任意有效路径 |

## 修复文件清单

1. ✅ `offline_perception_debug_src/include/hardware_mode.hpp` - 新增
2. ✅ `offline_perception_debug_src/src/offline_perception_debug_432.cpp` - 修改
3. ✅ `bin/offline_perception_debug_432` - 重新编译

## 验证步骤

1. 编译程序：`cd offline_perception_debug_src/build && make -j4`
2. 复制可执行文件：`cp offline_perception_debug_432 ../../bin/`
3. 运行测试脚本：`./test_hardware_mode.sh`
4. 在Web界面点击"白天离线debug"按钮测试

## 注意事项

1. 程序需要有效的输入目录，否则会因为无法创建输出目录而失败
2. 硬件模式会影响立体匹配、点云融合等多个模块的行为
3. 环境变量 `HARDWARE_MODE` 会被程序设置，供其他感知模块使用
4. 默认使用 K100 模式和 Mode 7 (DSG)

## 后续建议

1. 在 Web 界面添加硬件模式选择选项
2. 添加更详细的错误日志，便于调试
3. 考虑将配置参数持久化到配置文件
4. 添加输入目录有效性检查，提供更友好的错误提示
