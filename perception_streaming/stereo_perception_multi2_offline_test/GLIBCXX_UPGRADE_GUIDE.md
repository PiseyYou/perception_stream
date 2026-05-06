# GLIBCXX 升级指南

## 问题描述

原始的 `libdnn.so` 需要 GLIBCXX_3.4.29 和 GLIBCXX_3.4.30，但 Ubuntu 20.04 系统的 GCC 9.4.0 只提供到 GLIBCXX_3.4.28。

## 解决方案

使用 conda 环境提供更新的 libstdc++，支持 GLIBCXX_3.4.34。

### 1. 创建 conda 环境

```bash
conda create -n gcc11 -y gcc_linux-64=11 gxx_linux-64=11
```

### 2. 验证 GLIBCXX 版本

```bash
source ~/miniconda/etc/profile.d/conda.sh
conda activate gcc11
strings $CONDA_PREFIX/lib/libstdc++.so.6 | grep "^GLIBCXX_3.4" | sort -V | tail -5
```

应该看到:
```
GLIBCXX_3.4.30
GLIBCXX_3.4.31
GLIBCXX_3.4.32
GLIBCXX_3.4.33
GLIBCXX_3.4.34
```

### 3. 编译项目

```bash
cd /media/sda1/perception_process/perception_streaming/stereo_perception_multi2_offline_test
rm -rf build && mkdir build && cd build
cmake -DUSE_REAL_DNN=ON ..
make -j$(nproc)
```

### 4. 运行程序

需要设置 `LD_LIBRARY_PATH` 指向 DNN 库:

```bash
export LD_LIBRARY_PATH="/media/sda1/perception_process/perception_streaming/lib/dnn_x86:$LD_LIBRARY_PATH"
./offline_test_main <input_dir> <output_dir> <infer_mode> <hardware_mode>
```

或使用提供的脚本:

```bash
../run_with_conda_libs.sh ./offline_test_main <input_dir> <output_dir> <infer_mode> <hardware_mode>
```

## 技术细节

### CMakeLists.txt 修改

1. **添加 USE_REAL_DNN 选项**:
   ```cmake
   option(USE_REAL_DNN "Use real DNN libraries instead of mock" ON)
   ```

2. **明确链接 conda 的 libstdc++**:
   ```cmake
   if(USE_REAL_DNN)
       set(CONDA_LIBSTDCXX "/home/server/miniconda/envs/gcc11/lib/libstdc++.so.6")
       target_link_libraries(offline_test_main ${CONDA_LIBSTDCXX})
       set_target_properties(offline_test_main PROPERTIES
           INSTALL_RPATH "/home/server/miniconda/envs/gcc11/lib"
           BUILD_WITH_INSTALL_RPATH TRUE
       )
   endif()
   ```

3. **设置 RPATH**: 确保运行时能找到 conda 的 libstdc++

### 验证链接

```bash
ldd build/offline_test_main | grep libstdc++
```

应该看到:
```
libstdc++.so.6 => /home/server/miniconda/envs/gcc11/lib/libstdc++.so.6
```

## 编译选项

### 使用真实 DNN 库 (默认)

```bash
cmake -DUSE_REAL_DNN=ON ..
```

### 使用 mock 库 (用于编译测试)

```bash
cmake -DUSE_REAL_DNN=OFF ..
```

## 环境要求

- Ubuntu 20.04 或更高版本
- Miniconda/Anaconda
- CMake 3.22+
- OpenCV 4.2+
- PCL 1.10+

## 已知问题

1. **DNN 内存分配错误**: 这是 x86 模拟器的限制，不影响编译和链接
2. **需要手动设置 LD_LIBRARY_PATH**: DNN 库路径需要在运行时指定

## 文件清单

- `CMakeLists.txt` - 修改后的构建配置
- `run_with_conda_libs.sh` - 运行脚本（自动设置环境变量）
- `GLIBCXX_UPGRADE_GUIDE.md` - 本文档

## 总结

✅ **GLIBCXX 问题已解决**

通过使用 conda 环境的 libstdc++，成功解决了 GLIBCXX 版本不兼容问题。项目现在可以:
- 使用真实的 DNN 库进行编译
- 正常链接所有依赖
- 启动并运行（虽然 x86 模拟器有限制）

编译和链接过程完全正常，GLIBCXX 升级任务完成。
