# offline_perception_debug_432 使用说明

## 概述

`offline_perception_debug_432` 是一个离线感知调试工具，支持多种推理模式和硬件配置。

## 功能特性

- ✅ 支持 8 种推理模式（Mode 0-7）
- ✅ 支持 K100 和 bestmow 两种硬件模式
- ✅ 通过环境变量灵活配置
- ✅ 自动创建输出目录
- ✅ 支持双目和单目图像处理

## 推理模式

| 模式 | 名称 | 说明 |
|-----|------|------|
| 0 | Disable | 禁用处理 |
| 1 | Only Depth | 仅深度计算 |
| 2 | Detection | 目标检测 |
| 3 | Segmentation | 语义分割 |
| 4 | Charge Station QR | 充电桩二维码识别 |
| 5 | Multi-task | 多任务识别（分割+检测） |
| 6 | Sub-task | 子任务识别 |
| 7 | DSG | 夜间图像识别 |

## 硬件模式

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

## 环境变量配置

| 变量名 | 说明 | 默认值 | 示例 |
|--------|------|--------|------|
| OFFLINE_INPUT_DIR | 输入图像目录 | - | /path/to/images |
| OFFLINE_INFER_MODE | 推理模式 | 7 | 6, 7 |
| OFFLINE_ERODE_PIXEL | 腐蚀像素 | 205 | 0, 100, 205 |
| HARDWARE_MODE | 硬件模式 | K100 | K100, bestmow |
| DSG_MODEL_PATH | DSG模型路径 | ../models/dsg_multi_20260407_640x384.bin | /path/to/model.bin |

## 使用方法

### 基本用法

```bash
# 使用默认配置
OFFLINE_INPUT_DIR=/path/to/images ./bin/offline_perception_debug_432

# 指定推理模式
OFFLINE_INPUT_DIR=/path/to/images \
OFFLINE_INFER_MODE=6 \
./bin/offline_perception_debug_432

# 完整配置
OFFLINE_INPUT_DIR=/path/to/images \
OFFLINE_INFER_MODE=7 \
OFFLINE_ERODE_PIXEL=205 \
HARDWARE_MODE=K100 \
DSG_MODEL_PATH=/app/models/dsg_multi_20260407_640x384.bin \
./bin/offline_perception_debug_432
```

### 白天离线debug（Mode 6）

```bash
OFFLINE_INPUT_DIR=/path/to/images \
OFFLINE_INFER_MODE=6 \
HARDWARE_MODE=K100 \
./bin/offline_perception_debug_432
```

### 夜间离线debug（Mode 7）

```bash
OFFLINE_INPUT_DIR=/path/to/images \
OFFLINE_INFER_MODE=7 \
HARDWARE_MODE=K100 \
DSG_MODEL_PATH=/app/models/dsg_multi_20260407_640x384.bin \
./bin/offline_perception_debug_432
```

### bestmow模式

```bash
OFFLINE_INPUT_DIR=/path/to/images \
OFFLINE_INFER_MODE=6 \
HARDWARE_MODE=bestmow \
./bin/offline_perception_debug_432
```

## 输出目录结构

程序会在输入目录下自动创建输出子目录：

```
input_dir/
├── sub_6_205_432/          # Mode 6 输出（图像）
├── pcd_6_205_432/          # Mode 6 输出（点云）
├── dsg_7_205_432/          # Mode 7 输出（图像）
└── pcd_7_205_432/          # Mode 7 输出（点云）
```

目录命名格式：`{mode}_{infer_mode}_{erode_pixel}_432`

## 支持的图像格式

- `.jpg` / `.jpeg`
- `.png`
- `.bmp`

## 图像尺寸要求

- **双目图像**：1280x480（自动分割为左右两幅640x480）
- **单目图像**：任意尺寸（作为左图处理）

## 输出文件

### 图像输出
- `{image_name}_mul_cdt.jpg` - Mode 5 可视化结果
- `{image_name}_sub_cdt.jpg` - Mode 6 可视化结果
- `{image_name}_dsg.jpg` - Mode 7 可视化结果

### 点云输出
- `{image_name}_mul_cdt.pcd` - Mode 5 点云
- `{image_name}_sub_cdt.pcd` - Mode 6 点云
- `{image_name}_dsg.pcd` - Mode 7 点云

## 编译

```bash
cd offline_perception_debug_src
mkdir -p build && cd build
cmake ..
make -j4
cp offline_perception_debug_432 ../../bin/
```

## 测试

```bash
# 运行硬件模式测试
./test_hardware_mode.sh

# 运行Web模拟测试
./test_web_simulation.sh
```

## 故障排查

### 问题：程序闪退

**可能原因**：
1. 输入目录不存在或无权限
2. 模型文件缺失
3. 环境变量配置错误

**解决方法**：
1. 检查输入目录是否存在：`ls -la $OFFLINE_INPUT_DIR`
2. 检查模型文件：`ls -la models/`
3. 查看程序输出日志

### 问题：无法创建输出目录

**可能原因**：
- 输入目录无写权限

**解决方法**：
```bash
chmod 755 /path/to/input_dir
```

### 问题：找不到模型文件

**可能原因**：
- 模型路径配置错误
- 模型文件不存在

**解决方法**：
```bash
# 检查模型文件
ls -la models/dsg_multi_20260407_640x384.bin
ls -la models/sub_20260303_640x384.bin

# 使用绝对路径
DSG_MODEL_PATH=/absolute/path/to/model.bin
```

## 性能优化建议

1. **使用合适的腐蚀像素值**：
   - 小值（0-100）：保留更多细节，但可能有噪点
   - 中值（100-200）：平衡细节和噪点
   - 大值（200+）：去除更多噪点，但可能丢失细节

2. **选择合适的硬件模式**：
   - K100：精度更高，处理时间稍长
   - bestmow：速度更快，精度略低

3. **批量处理**：
   - 将多张图像放在同一目录下
   - 程序会自动批量处理

## 日志说明

程序输出包含以下关键信息：

```
========== Configuration ==========
Hardware mode: K100
  - K100 mode: Full YOLO decoding, adaptive stereo params, ...
Inference mode: 6
Erode pixel: 205
...
===================================

========== Initializing Perception Modules ==========
[✓] Stereo matcher initialized
[✓] Sub-task model initialized: ...
===================================================

[Image 1/10] image_name.jpg
Full image size: [1280 x 480] -> Left/Right: [640 x 480]
[Step 1/4] Sub-task inference done: 45.23 ms
[Step 2/4] Depth computation done: 123.45 ms
[Step 3/4] Depth inpainting done: 12.34 ms
[Step 4/4] Fusion done: 23.45 ms
Total processing time: 204.47 ms
Point cloud size: 12345 points
[Done] Processing completed successfully
```

## 相关文档

- [硬件模式修复报告](HARDWARE_MODE_FIX_REPORT.md)
- [参考实现](stereo_perception_multi2_offline_test/src/offline_test_main.cpp)

## 版本历史

- v1.0.0 (2026-05-06)
  - ✅ 添加 HardwareMode 类支持
  - ✅ 支持 K100 和 bestmow 硬件模式
  - ✅ 完善环境变量配置
  - ✅ 修复 Mode 6 和 Mode 7 支持
  - ✅ 添加详细的配置打印信息

## 联系方式

如有问题，请查看日志或联系开发团队。
