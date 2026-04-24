# Night Offline Debug - 夜间离线调试程序

## 概述

这是用于"双目分析"面板中"夜间离线debug"功能的完整程序。该程序专门用于处理夜间场景的双目视觉数据，使用自适应立体匹配参数和DSG多任务模型进行检测和分割。

## 功能特性

- **Mode 7: DSG Night Recognition**
  - 使用针对夜间场景优化的自适应立体匹配参数
  - 使用DSG多任务模型进行检测和分割
  - 裁剪到432高度，调整到384进行推理
  - 将检测ID映射到100+格式
  - 支持可选的CDT（充电站检测）
  - 在432分辨率下执行深度计算和融合

## 目录结构

```
night_offline_debug/
├── build/                      # 编译输出目录
│   └── run_cdt_dsg_fusion_dir  # 主可执行文件
├── cmake-build-debug/          # CMake调试构建目录
├── data/                       # 数据目录
│   ├── input/                  # 输入数据
│   └── output/                 # 输出结果
├── include/                    # 头文件
│   ├── cdt_perception.h
│   ├── config_loader.h
│   ├── dsg_perception.h
│   ├── perception.h
│   ├── perception_common.h
│   ├── stereo_multi_match.h
│   └── stereo_point_cloud_rgbl.h
├── model/                      # 模型文件目录
├── src/                        # 源代码
│   ├── cdt_perception.cpp
│   ├── dsg_perception.cpp
│   ├── multiscale_filter.cpp
│   ├── run_cdt_dsg_fusion.cpp
│   ├── run_cdt_dsg_fusion_dir.cpp
│   ├── stereo_multi_match.cpp
│   └── stereo_point_cloud_rgbl.cpp
└── CMakeLists.txt              # CMake配置文件
```

## 使用方法

### 通过Web界面使用

1. 打开"双目分析"标签页
2. 输入包含 `images/` 和 `pointclouds/` 子目录的文件夹路径
3. 点击"🌙 夜间离线debug"按钮
4. 程序将自动处理所有帧并显示进度

### 环境变量

程序通过以下环境变量配置：

- `NIGHT_INPUT_DIR`: 输入目录路径
- `DSG_MODEL_PATH`: DSG模型文件路径
- `RESUME_NIGHT`: 设置为"1"以继续之前中断的处理
- `LD_LIBRARY_PATH`: 包含所需的DNN库路径

### 输出

- **图像输出**: `<input_dir>/dsg_7_205_432/`
  - 包含处理后的检测和分割结果图像
  - 文件格式: `*_dsg_cdt.jpg` 或 `*_dsg_cdt.png`

- **点云输出**: `<input_dir>/pcd_7_205_432/`
  - 包含融合后的点云数据
  - 文件格式: `*.pcd`

## 编译

```bash
cd night_offline_debug
mkdir -p build
cd build
cmake ..
make -j$(nproc)
```

## 依赖

- OpenCV
- PCL (Point Cloud Library)
- DNN推理库 (位于 `/home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/lib`)
- DSG模型文件

## 集成

该程序已集成到 `robot_monitor/offline_server.py` 中：

```python
NIGHT_EXE = os.path.join(PROJECT_ROOT, "night_offline_debug/build/run_cdt_dsg_fusion_dir")
```

当用户在Web界面点击"夜间离线debug"按钮时，会调用 `infer_mode=7` 来执行此程序。

## 原始位置

原始程序位于: `/home/youfeng/CLionProjects/07_openclaw_auto/claude_project/night_test/`

已迁移到项目根目录以便于管理和部署。
