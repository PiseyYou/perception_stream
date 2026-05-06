# 快速开始指南

## 一键编译

```bash
cd /media/sda1/perception_process/perception_streaming/stereo_perception_multi2_offline_test
rm -rf build && mkdir build && cd build
cmake -DUSE_REAL_DNN=ON ..
make -j$(nproc)
```

## 一键运行

```bash
export LD_LIBRARY_PATH="/media/sda1/perception_process/perception_streaming/lib/dnn_x86:$LD_LIBRARY_PATH"
./offline_test_main <input_dir> <output_dir> <infer_mode> <hardware_mode>
```

## 参数说明

- `input_dir`: 输入图像目录
- `output_dir`: 输出结果目录
- `infer_mode`: 推理模式 (6=Sub, 7=DSG)
- `hardware_mode`: 硬件模式 (k100 或 bestmow)

## 示例

```bash
./offline_test_main /path/to/images test_output 7 k100
```

## 环境要求

✅ Ubuntu 20.04+  
✅ OpenCV 4.2+ (当前 4.2.0)  
✅ PCL 1.10+  
✅ Conda 环境 (gcc11)  

## 验证状态

✅ **编译**: 正常  
✅ **链接**: 正常  
✅ **运行**: 正常  

详细信息见 [COMPILATION_VERIFICATION_REPORT.md](COMPILATION_VERIFICATION_REPORT.md)
