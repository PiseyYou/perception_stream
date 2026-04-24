# x86 平台编译配置说明

## 问题
在 x86 平台编译时，找不到 Horizon DNN 库的头文件和库文件。

## 解决方案

### 1. 添加 x86 DNN 头文件路径
在 `CMakeLists.txt` 的 `include_directories` 中添加：
```cmake
/home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/include
```

### 2. 添加 x86 DNN 库文件路径
在 `CMakeLists.txt` 的 `link_directories` 中添加：
```cmake
/home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/lib
```

### 3. 修改链接库名称
将 `hbrt_bayes_aarch64`（ARM 平台）改为 `hbdk_sim_x86`（x86 平台）：
```cmake
target_link_libraries(offline_test_main
    ...
    dnn
    hbdk_sim_x86  # x86 平台使用模拟库
    ...
)
```

## x86 vs ARM 平台差异

| 项目 | ARM 平台 | x86 平台 |
|------|----------|----------|
| 头文件路径 | /usr/hobot/include | deps_gcc11.3/x86/dnn_x86/include |
| 库文件路径 | /usr/hobot/lib | deps_gcc11.3/x86/dnn_x86/lib |
| DNN 库 | libdnn.so | libdnn.so |
| 运行时库 | libhbrt_bayes_aarch64.so | libhbdk_sim_x86.so |

## 库文件说明

### x86 平台库文件
```
/home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/lib/
├── libdnn.so           # DNN 推理库
└── libhbdk_sim_x86.so  # x86 模拟运行时库
```

### ARM 平台库文件
```
/usr/hobot/lib/
├── libdnn.so                  # DNN 推理库
└── libhbrt_bayes_aarch64.so   # ARM 硬件加速运行时库
```

## 编译命令

### 清理重新编译
```bash
cd /home/youfeng/CLionProjects/12-evb/evb_test/src/stereo_perception_multi2_offline_test
rm -rf cmake-build-debug build
./build.sh
```

### 或使用 CMake 手动编译
```bash
mkdir -p build && cd build
cmake ..
make -j$(nproc)
```

## 运行时配置

### 设置库路径
```bash
export LD_LIBRARY_PATH=/home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/lib:$LD_LIBRARY_PATH
```

### 验证库依赖
```bash
ldd ./offline_test_main | grep -E "dnn|hbdk"
```

应该看到：
```
libdnn.so => /home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/lib/libdnn.so
libhbdk_sim_x86.so => /home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/lib/libhbdk_sim_x86.so
```

## 注意事项

1. **x86 平台限制**：x86 版本使用模拟库，性能比 ARM 硬件加速慢
2. **模型兼容性**：确保模型文件与 x86 模拟库兼容
3. **路径依赖**：如果 deps 目录位置变化，需要更新 CMakeLists.txt 中的路径

## 跨平台编译

如果需要同时支持 x86 和 ARM 平台，可以使用条件编译：

```cmake
# 检测平台
if(CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64")
    # x86 平台
    include_directories(/home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/include)
    link_directories(/home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/lib)
    set(DNN_RUNTIME_LIB hbdk_sim_x86)
elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64")
    # ARM 平台
    include_directories(/usr/hobot/include)
    link_directories(/usr/hobot/lib)
    set(DNN_RUNTIME_LIB hbrt_bayes_aarch64)
endif()

target_link_libraries(offline_test_main
    ...
    dnn
    ${DNN_RUNTIME_LIB}
    ...
)
```

## 故障排除

### 问题 1：找不到 dnn/hb_dnn.h
**解决**：检查头文件路径是否正确添加到 `include_directories`

### 问题 2：链接时找不到 libhbdk_sim_x86.so
**解决**：检查库文件路径是否正确添加到 `link_directories`

### 问题 3：运行时找不到共享库
**解决**：设置 `LD_LIBRARY_PATH` 环境变量

### 问题 4：模型加载失败
**解决**：确保使用 x86 兼容的模型文件
