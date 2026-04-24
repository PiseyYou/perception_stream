# stereo_perception_multi2 离线测试工具 v2.3.0

## 概述
基于 stereo_perception_multi2 v2.1.0 的离线测试工具，支持手动配置硬件模式（K100/bestmow）。该工具提供了一个独立的离线环境，用于测试和验证立体视觉感知算法，无需 ROS2 依赖。

## 主要特性
- ✅ 手动配置硬件模式（无需读取配置文件）
- ✅ 支持批量处理图像
- ✅ 输出分割结果、点云、检测框
- ✅ **支持 Model 6 (Sub/multi_sub) 和 Model 7 (DSG) 双模式**
- ✅ 完整的深度估计和点云生成
- ✅ **合并可视化输出**（原图+分割+点云三视图）
- ✅ **点云三视图可视化**（标签视图 + RGB视图）
- ✅ **CMake 构建模式选择**（支持 K100/bestmow 源码切换）
- ✅ 支持多种图像格式（JPG、PNG、BMP）

## 版本更新

### v2.3.0 (最新)

#### 新增功能
1. **Model 6 (Sub/multi_sub) 支持**
   - 添加 `multi_sub_perception.cpp` 源文件集成
   - 新增 `sub_20260303_640x384.bin` 模型文件
   - 支持红色砖头颜色后处理（`enable_red_brick_refine`）
   - 支持深度补全策略（`depth_inpainting_strategy`）
   - 支持高度过滤（`enable_height_filter`）
   - 支持检测框绘制控制（`enable_draw_detection_box`）

2. **智能输出目录命名**
   - 自动生成输出目录：`output_<模式名>_<硬件>_<腐蚀参数>/`
   - 示例：`output_Sub_K100/`, `output_DSG_bestmow_erode2/`
   - 更清晰的结果组织和对比

3. **模型自动选择**
   - Model 6: 自动使用 `sub_20260303_640x384.bin`
   - Model 7: 自动使用 `dsg_multi_20260407_640x384.bin`
   - 根据 `infer_mode` 自动加载对应模型

#### 改进优化
- ✅ 配置结构更清晰：Model 6 和 Model 7 配置分离
- ✅ 输出目录命名更直观（Sub/DSG 替代数字模式）
- ✅ 添加模型文件存在性检查
- ✅ 优化配置参数组织结构

### v2.2.0

#### 新增功能
1. **CMake 构建模式选择**
   - 支持通过 CMake 选项切换 K100/bestmow 源码
   - `cmake -DUSE_BESTMOW=ON` 使用 bestmow 源码
   - `cmake -DUSE_BESTMOW=OFF` 使用 K100 源码（默认）
   - 自动选择对应的头文件和库文件

2. **统一推理接口**
   - 使用完整的 `perception_process_bgr_no_argmax_erode` 接口
   - 动态设置 `ori_width/ori_height` 适配不同输入尺寸
   - 统一的检测框和分割结果处理流程

3. **HSV 暗色过滤增强**
   - 支持障碍物保护模式（`enable_dsg_hsv_obstacle_protection`）
   - 可配置的形态学核大小
   - 与在线代码逻辑对齐

4. **深度图处理优化**
   - K100 模式：深度图从 432 resize 到 384 用于融合
   - bestmow 模式：深度图直接裁剪到 384
   - 确保深度图与分割图尺寸一致

#### 改进优化
- ✅ 统一使用 `stereo_process_pci_depth_rgb_seg_det_fusion` 融合函数
- ✅ 添加模型文件存在性检查
- ✅ 优化可视化图像尺寸适配（K100: 432, bestmow: 384）
- ✅ 添加详细的调试日志输出
- ✅ bestmow 模式也使用 dsg_multi 模型

#### 修复问题
- ✅ 修复 K100/bestmow 模式图像裁剪逻辑
- ✅ 修复深度图与分割图尺寸不匹配问题
- ✅ 修复可视化时分割图尺寸适配问题
- ✅ 修复立体匹配参数初始化逻辑

### v2.1.0

#### 新增功能
1. **合并可视化保存**
   - 横向拼接：原图 | 纯色分割 | 叠加图
   - 纵向拼接：上方（三图横拼）+ 下方（点云三视图）
   - 一张图片展示所有结果

2. **点云三视图可视化**
   - 标签视图：X视图（侧视）、Y视图（俯视）、Z视图（正视）
   - RGB视图：X视图、Y视图、Z视图
   - 完整的 1920x960 点云可视化

3. **K100/bestmow 模式差异化处理**
   - K100: 640x432 → 640x384 → 推理 → 640x432
   - bestmow: 640x384 → 推理
   - 深度图裁剪尺寸自动适配

#### 修复问题
- ✅ 修复编译链接错误（移除未使用的 gflags/glog）
- ✅ 修复模型加载路径
- ✅ 修复 ori_width/ori_height 未初始化问题
- ✅ 修复立体匹配图像格式错误
- ✅ 修复分割图像初始化问题

## 配置说明

### 手动硬件模式配置
在 `offline_test_main.cpp` 中直接修改：

```cpp
// 硬件模式配置（手动调整）
bool use_k100_mode = true;  // true: K100 模式, false: bestmow 模式

// 推理模式选择
config.infer_mode = 6;  // 6: Model 6 (Sub/multi_sub), 7: Model 7 (DSG)

// 输出控制
config.enable_debug_show = true;  // 启用合并可视化保存
```

### 推理模式对比

| 特性 | Model 6 (Sub) | Model 7 (DSG) |
|------|---------------|---------------|
| 模型文件 | sub_20260303_640x384.bin | dsg_multi_20260407_640x384.bin |
| 红砖后处理 | ✅ 支持 | ❌ 不支持 |
| 深度补全 | ✅ 支持（3种策略） | ❌ 不支持 |
| 高度过滤 | ✅ 支持 | ❌ 不支持 |
| HSV暗色过滤 | ❌ 不支持 | ✅ 支持 |
| 障碍物保护 | ❌ 不支持 | ✅ 支持 |
| 离群点移除 | ❌ 不支持 | ✅ 支持 |

### K100 模式 vs bestmow 模式

| 特性 | K100 模式 | bestmow 模式 |
|------|-----------|--------------|
| 源码选择 | stereo_perception_multi2 | stereo_perception_multi2_bestmow |
| 图像处理 | 裁剪640x432→resize到640x384 | 直接裁剪640x384 |
| 推理接口 | 统一使用完整接口 | 统一使用完整接口 |
| 立体匹配 | 自适应参数 | 自适应参数 |
| 深度图处理 | 432→resize到384用于融合 | 直接384用于融合 |
| 点云融合 | 统一融合函数 | 统一融合函数 |
| 可视化尺寸 | 432 resize到384显示 | 直接384显示 |

## 编译

### 默认编译（K100 模式）
```bash
cd /home/youfeng/CLionProjects/12-evb/evb_test/src/stereo_perception_multi2_offline_test
mkdir -p cmake-build-debug && cd cmake-build-debug
cmake ..
make -j$(nproc)
```

### 编译 bestmow 模式
```bash
cd /home/youfeng/CLionProjects/12-evb/evb_test/src/stereo_perception_multi2_offline_test
mkdir -p cmake-build-debug && cd cmake-build-debug
cmake -DUSE_BESTMOW=ON ..
make -j$(nproc)
```

或使用构建脚本：
```bash
./build.sh          # K100 模式
./build.sh bestmow  # bestmow 模式
```

## 使用方法

```bash
# 设置库路径
export LD_LIBRARY_PATH=/path/to/dnn_x86/lib:$LD_LIBRARY_PATH

# 运行程序
./offline_test_main <input_dir> <output_dir> [hardware_mode]

# 示例
./offline_test_main /path/to/images /path/to/output k100
./offline_test_main /path/to/images /path/to/output bestmow

# 输出目录会自动生成为：
# - Model 6: output_Sub_K100/ 或 output_Sub_bestmow/
# - Model 7: output_DSG_K100/ 或 output_DSG_bestmow/
```

## 输入格式
- 支持双目拼接图像（1280x480）：自动分割为左右图
- 支持单目图像：仅使用左图
- 支持格式：.jpg, .jpeg, .png, .bmp

## 输出内容
- `<output_dir>/combined/`: **合并可视化图像**（原图+分割+点云三视图）
- `<output_dir>/segmentation/`: 分割可视化结果
- `<output_dir>/pointcloud/`: PCD 点云文件
- `<output_dir>/detection/`: 检测框可视化（K100 模式）
- `<output_dir>/depth/`: 深度图可视化

### 合并可视化布局
```
┌─────────────────────────────────────────────────────────┐
│  原图(640x432)  │  纯色分割  │  叠加图(原图+分割)  │
├─────────────────────────────────────────────────────────┤
│              点云三视图 (1920x960)                        │
│  标签视图: X | Y | Z                                     │
│  RGB视图:  X | Y | Z                                     │
└─────────────────────────────────────────────────────────┘
```

## 参数调整

### 在代码中修改配置
```cpp
// 主配置
config.infer_mode = 6;              // 推理模式：6=Sub, 7=DSG
config.erode_pixel = 0;             // 形态学腐蚀像素
config.detection_threshold = 0.3;   // 检测阈值
config.area_threshold = 0.5;        // 区域阈值

// Model 6 (Sub) 专用配置
config.enable_red_brick_refine = false;              // 红色砖头颜色后处理
config.red_brick_min_area = 100;                     // 红色砖头最小面积
config.depth_inpainting_strategy = 0;                // 深度补全策略：0=关闭, 1=检测框, 2=语义, 3=两者
config.enable_height_filter = false;                 // 启用高度过滤
config.enable_draw_detection_box = false;            // 是否在可视化结果中绘制检测框

// Model 7 (DSG) 专用配置
config.enable_dsg_hsv_dark_filter = false;           // HSV 暗色过滤
config.enable_dsg_hsv_obstacle_protection = false;   // HSV 暗色过滤时保护障碍物
config.enable_dsg_detection_in_pointcloud = false;   // 点云中显示检测框
config.enable_dsg_outlier_removal = false;           // 点云融合时启用离群点移除

// 输出控制
config.save_segmentation = true;    // 保存分割结果
config.save_pointcloud = true;      // 保存点云
config.save_detection = true;       // 保存检测结果
config.save_depth = true;           // 保存深度图
config.enable_debug_show = true;    // 保存合并可视化
```

## 与 ROS2 版本的差异
1. **硬件检测**：不读取配置文件，手动指定硬件模式
2. **模型路径**：使用相对路径或绝对路径
3. **输出格式**：直接保存文件，无 ROS2 topic 发布
4. **日志系统**：使用 cout/cerr，无 ROS2 日志
5. **可视化**：生成合并图像，无需 RViz

## 项目结构
```
stereo_perception_multi2_offline_test/
├── CMakeLists.txt                    # CMake 构建配置（支持 K100/bestmow 切换）
├── README.md                         # 本文档
├── QUICKSTART.md                     # 快速开始指南
├── PROJECT_SUMMARY.md                # 项目总结
├── FINAL_FIX_SUMMARY.md             # 修复总结
├── K100_MODE_LOGIC_COMPARISON.md    # K100 模式逻辑对比分析
├── build.sh                          # 构建脚本
├── include/                          # 头文件
│   ├── offline_config.hpp            # 配置结构定义
│   ├── hardware_mode.hpp             # 硬件模式定义
│   ├── offline_processor.hpp         # 处理器接口
│   ├── offline_utils.hpp             # 工具函数
│   └── stereo_point_cloud_rgbl.h    # 点云可视化
├── src/                              # 源文件
│   ├── offline_test_main.cpp         # 主程序入口
│   ├── offline_processor.cpp         # 核心处理逻辑
│   └── stereo_point_cloud_rgbl.cpp  # 点云可视化实现
├── models/                           # 模型文件
    ├── sub_20260303_640x384.bin      # Model 6 (Sub) 模型
    └── dsg_multi_20260407_640x384.bin # Model 7 (DSG) 模型
```

## 依赖项
- OpenCV 4.x
- PCL (Point Cloud Library)
- Eigen3
- stereo_perception_multi2 库
- DNN 库（x86 模拟器）
- C++17 或更高版本

## 技术要点

### 图像处理流程
**K100 模式**:
```
640x480 → 裁剪640x432 → resize到640x384 → DSG推理 
→ resize回640x432 → 深度图裁剪640x432 → 点云融合
```

**bestmow 模式**:
```
640x480 → 裁剪640x384 → DSG推理 
→ 深度图裁剪640x384 → 点云融合
```

### 点云三视图
- **X视图（侧视）**：从侧面看，显示 Y-Z 平面
- **Y视图（俯视）**：从上往下看，显示 X-Z 平面
- **Z视图（正视）**：从正面看，显示 X-Y 平面

每个视图包含标签版本和RGB版本，共6个视图。

## 开发说明
- 基于 stereo_perception_multi2 v2.1.0
- 参考 offline_perception_debug_432_sob.cpp
- 保留核心感知逻辑，简化 ROS2 依赖
- 支持 x86 和 ARM 平台编译
- 完整的点云可视化功能

## 许可证
本项目遵循与 stereo_perception_multi2 相同的许可证。

## 贡献
欢迎提交 Issue 和 Pull Request。

## 联系方式
如有问题，请通过 GitHub Issues 联系。
