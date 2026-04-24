# 离线测试环境配置说明

## 目录结构

项目已配置为使用相对路径，需要将以下文件放置到对应目录：

```
perception_streaming-master/
├── bin/                                    # 可执行文件目录
│   ├── offline_perception_debug_432       # 离线感知调试主程序
│   └── dsg_mono_perception                # 单目感知程序
├── lib/                                    # 依赖库目录
│   └── dnn_x86/                           # DNN库文件
│       ├── libhorizon_runtime.so
│       └── ... (其他.so文件)
├── models/                                 # 模型文件目录
│   └── dsg_multi_20260407_640x384.bin     # DSG多任务模型
└── night_offline_debug/                    # 夜间调试程序
    └── build/
        └── run_cdt_dsg_fusion_dir
```

## 文件来源映射

### 1. 可执行文件 (bin/)

从以下路径复制到 `bin/` 目录：

```bash
# 离线感知调试主程序
cp /home/youfeng/CLionProjects/07_openclaw_auto/claude_project/offline_perception_debug/build/offline_perception_debug_432 \
   bin/offline_perception_debug_432

# 单目感知程序
cp /home/youfeng/CLionProjects/05-offline_debug_fusion/offline_perception_debug/cmake-build-debug/dsg_mono_perception \
   bin/dsg_mono_perception
```

### 2. 依赖库 (lib/)

从以下路径复制到 `lib/dnn_x86/` 目录：

```bash
# 创建库目录
mkdir -p lib/dnn_x86

# 复制所有依赖库
cp -r /home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/lib/* \
   lib/dnn_x86/
```

### 3. 模型文件 (models/)

从以下路径复制到 `models/` 目录：

```bash
# 复制DSG多任务模型
cp /home/youfeng/CLionProjects/05-offline_debug_fusion/offline_perception_debug/models/dsg_multi_20260407_640x384.bin \
   models/dsg_multi_20260407_640x384.bin

# 复制CDT模型
cp /home/youfeng/CLionProjects/06_claude_debug/02_debug/offline_perception_debug/models/cdt_20251125_640x384.bin \
   models/cdt_20251125_640x384.bin

# 复制DSG夜间模型
cp /home/youfeng/CLionProjects/06_claude_debug/02_debug/offline_perception_debug/models/dsg_20260211_640x384.bin \
   models/dsg_20260211_640x384.bin
```

### 4. 夜间调试程序 (已存在)

`night_offline_debug/` 目录已经在项目中，无需额外操作。

## 快速部署脚本

创建并运行以下脚本来自动部署所有文件：

```bash
#!/bin/bash
# deploy_offline_test.sh

PROJECT_ROOT="/home/youfeng/CLionProjects/07_openclaw_auto/project/perception_streaming-master-80b4b0d5e580c3b80e50eea2d3719aad56d8d808"

cd "$PROJECT_ROOT"

# 创建目录
mkdir -p bin lib/dnn_x86 models

# 复制可执行文件
echo "复制可执行文件..."
cp /home/youfeng/CLionProjects/07_openclaw_auto/claude_project/offline_perception_debug/build/offline_perception_debug_432 \
   bin/offline_perception_debug_432

cp /home/youfeng/CLionProjects/05-offline_debug_fusion/offline_perception_debug/cmake-build-debug/dsg_mono_perception \
   bin/dsg_mono_perception

# 设置执行权限
chmod +x bin/offline_perception_debug_432
chmod +x bin/dsg_mono_perception

# 复制依赖库
echo "复制依赖库..."
cp -r /home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/lib/* \
   lib/dnn_x86/

# 复制模型文件
echo "复制模型文件..."
cp /home/youfeng/CLionProjects/05-offline_debug_fusion/offline_perception_debug/models/dsg_multi_20260407_640x384.bin \
   models/dsg_multi_20260407_640x384.bin

echo "部署完成！"
echo "文件列表："
ls -lh bin/
ls -lh lib/dnn_x86/ | head -10
ls -lh models/
```

## 验证部署

运行以下命令验证文件是否正确部署：

```bash
# 检查可执行文件
ls -lh bin/offline_perception_debug_432
ls -lh bin/dsg_mono_perception

# 检查库文件
ls lib/dnn_x86/ | wc -l  # 应该有多个.so文件

# 检查模型文件
ls -lh models/dsg_multi_20260407_640x384.bin

# 测试可执行文件
ldd bin/offline_perception_debug_432  # 检查依赖库
```

## 配置说明

所有路径配置已在 `robot_monitor/offline_server.py` 中更新为相对路径：

- `OFFLINE_EXE`: `bin/offline_perception_debug_432`
- `MONO_EXE`: `bin/dsg_mono_perception`
- `OFFLINE_LIB`: `lib/dnn_x86`
- `DSG_MODEL`: `models/dsg_multi_20260407_640x384.bin`
- `MONO_MODEL`: `models/dsg_multi_20260407_640x384.bin`

## 注意事项

1. 确保所有可执行文件有执行权限 (`chmod +x`)
2. 库文件路径会通过 `LD_LIBRARY_PATH` 环境变量设置
3. 模型文件路径会通过 `DSG_MODEL_PATH` 环境变量传递给程序
4. 如果程序运行失败，检查日志中的路径是否正确

## 故障排查

如果离线测试无法运行：

1. 检查文件是否存在：
   ```bash
   ls -la bin/ lib/dnn_x86/ models/
   ```

2. 检查执行权限：
   ```bash
   chmod +x bin/*
   ```

3. 检查库依赖：
   ```bash
   ldd bin/offline_perception_debug_432
   ```

4. 查看服务器日志中的错误信息
