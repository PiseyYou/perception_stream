# 夜间离线Debug程序迁移记录

## 迁移日期
2026-04-21

## 迁移内容

### 源位置
```
/home/youfeng/CLionProjects/07_openclaw_auto/claude_project/night_test/
```

### 目标位置
```
/home/youfeng/CLionProjects/07_openclaw_auto/project/perception_streaming-master-80b4b0d5e580c3b80e50eea2d3719aad56d8d808/night_offline_debug/
```

## 迁移的文件

### 可执行文件
- `build/run_cdt_dsg_fusion_dir` (1.6MB) - 主程序可执行文件
- `build/run_cdt_dsg_fusion` - 辅助可执行文件

### 源代码
- `src/run_cdt_dsg_fusion_dir.cpp` - 主程序入口
- `src/run_cdt_dsg_fusion.cpp`
- `src/dsg_perception.cpp` - DSG感知模块
- `src/cdt_perception.cpp` - CDT感知模块
- `src/stereo_multi_match.cpp` - 立体匹配
- `src/stereo_point_cloud_rgbl.cpp` - 点云生成
- `src/multiscale_filter.cpp` - 多尺度滤波

### 头文件
- `include/perception.h`
- `include/perception_common.h`
- `include/dsg_perception.h`
- `include/cdt_perception.h`
- `include/stereo_multi_match.h`
- `include/stereo_point_cloud_rgbl.h`
- `include/config_loader.h`
- `include/detection_type.hpp`
- `include/multiscale_filter.hpp`

### 模型文件
- `model/dsg_multi_20260401_640x384.bin` - DSG多任务模型
- `model/night_0331_167.bin` - 夜间模型

### 构建文件
- `CMakeLists.txt` - CMake配置
- `build/Makefile` - 编译配置
- `build/CMakeCache.txt` - CMake缓存

### 数据目录
- `data/input/` - 输入数据目录
- `data/output/` - 输出结果目录

## 代码修改

### robot_monitor/offline_server.py

**修改前:**
```python
NIGHT_EXE = "/home/youfeng/CLionProjects/07_openclaw_auto/claude_project/night_test/build/run_cdt_dsg_fusion_dir"
```

**修改后:**
```python
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NIGHT_EXE = os.path.join(PROJECT_ROOT, "night_offline_debug/build/run_cdt_dsg_fusion_dir")
```

## 功能说明

该程序用于"双目分析"面板中的"🌙 夜间离线debug"功能：

1. **触发方式**: 在Web界面点击"夜间离线debug"按钮
2. **处理模式**: infer_mode=7 (DSG Nighttime)
3. **输入**: 包含 images/ 和 pointclouds/ 的文件夹
4. **输出**: 
   - 图像: `<input_dir>/dsg_7_205_432/*.jpg`
   - 点云: `<input_dir>/pcd_7_205_432/*.pcd`

## 验证

```bash
# 检查可执行文件
ls -lh night_offline_debug/build/run_cdt_dsg_fusion_dir

# 验证路径解析
python3 -c "
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath('robot_monitor/offline_server.py')))
NIGHT_EXE = os.path.join(PROJECT_ROOT, 'night_offline_debug/build/run_cdt_dsg_fusion_dir')
print(f'Path: {NIGHT_EXE}')
print(f'Exists: {os.path.exists(NIGHT_EXE)}')
"
```

## 注意事项

1. 原始程序仍保留在 `/home/youfeng/CLionProjects/07_openclaw_auto/claude_project/night_test/`
2. 如需重新编译，进入 `night_offline_debug/build/` 目录执行 `make`
3. 依赖的DNN库路径: `/home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/lib`
4. 模型文件已包含在 `night_offline_debug/model/` 目录中

## 相关文档

- [night_offline_debug/README.md](night_offline_debug/README.md) - 程序详细说明
- [src/components/StereoAnalysis2Panel.vue](src/components/StereoAnalysis2Panel.vue) - Web界面组件
