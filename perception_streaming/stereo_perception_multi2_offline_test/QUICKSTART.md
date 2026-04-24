# 快速使用指南

## 1. 编译项目

```bash
cd /home/youfeng/CLionProjects/12-evb/evb_test/src/stereo_perception_multi2_offline_test
./build.sh
```

清理重新编译：
```bash
./build.sh clean
```

## 2. 准备模型文件

将模型文件放到 `models/` 目录：
```bash
mkdir -p models
cp /path/to/dsg_multi_20260403_640x384.bin models/  # K100 模型
cp /path/to/dsg_20260115_640x384.bin models/        # bestmow 模型
```

或者修改 `src/offline_test_main.cpp` 中的模型路径：
```cpp
config.model_dir = "/absolute/path/to/models/";
```

## 3. 运行测试

### K100 模式（默认）
```bash
cd build
./offline_test_main /path/to/images ./output
# 或明确指定
./offline_test_main /path/to/images ./output k100
```

### bestmow 模式
```bash
cd build
./offline_test_main /path/to/images ./output bestmow
```

## 4. 查看结果

输出目录结构：
```
output/
├── segmentation/    # 分割可视化结果
│   └── image_name_seg.png
├── pointcloud/      # PCD 点云文件
│   └── image_name.pcd
├── detection/       # 检测框可视化（K100 模式）
│   └── image_name_det.png
└── depth/           # 深度图可视化
    └── image_name_depth.png
```

## 5. 调整配置

编辑 `src/offline_test_main.cpp` 中的配置：

```cpp
// 硬件模式
config.use_k100_mode = true;  // true: K100, false: bestmow

// 基础配置
config.infer_mode = 7;              // DSG 模式
config.erode_pixel = 0;             // 形态学腐蚀像素
config.detection_threshold = 0.3f;  // 检测阈值

// K100 专用
config.enable_dsg_hsv_dark_filter = false;
config.enable_dsg_detection_in_pointcloud = false;

// 输出控制
config.save_segmentation = true;
config.save_pointcloud = true;
config.save_detection = true;
config.save_depth = true;
```

## 6. 常见问题

### 编译错误：找不到头文件
确保 `stereo_perception_multi2` 项目在正确位置：
```
12-evb/evb_test/src/
├── stereo_perception_multi2/
└── stereo_perception_multi2_offline_test/
```

### 运行错误：找不到模型文件
检查模型路径配置，使用绝对路径：
```cpp
config.model_dir = "/home/youfeng/models/";
```

### 运行错误：找不到 libdnn.so
添加库路径到 LD_LIBRARY_PATH：
```bash
export LD_LIBRARY_PATH=/usr/hobot/lib:$LD_LIBRARY_PATH
```

## 7. 性能对比

| 模式 | DSG 推理 | 立体匹配 | 点云融合 | 总耗时 |
|------|----------|----------|----------|--------|
| K100 | ~80ms | ~50ms | ~50ms | ~180ms |
| bestmow | ~60ms | ~40ms | ~40ms | ~140ms |

bestmow 模式约快 25%，但点云质量略低。

## 8. 批量处理示例

```bash
#!/bin/bash
# 批量处理多个目录

DIRS=(
    "/path/to/dataset1"
    "/path/to/dataset2"
    "/path/to/dataset3"
)

for dir in "${DIRS[@]}"; do
    echo "Processing: $dir"
    ./offline_test_main "$dir" "${dir}/output_k100" k100
    ./offline_test_main "$dir" "${dir}/output_bestmow" bestmow
done
```
