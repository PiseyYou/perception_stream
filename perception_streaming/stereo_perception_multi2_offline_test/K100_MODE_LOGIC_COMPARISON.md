# K100 模式逻辑对比分析（更新版）

## 概述
对比离线测试代码 (`offline_test_main.cpp` + `offline_processor.cpp`) 与在线代码 (`stereo_perception_multi_queue.cpp`) 中 `use_k100_mode` / `is_k100` 的逻辑差异。

**分析日期**: 2026-04-17  
**在线代码版本**: v2.1.1c  
**离线代码版本**: v2.1.0

---

## 1. 图像裁剪和预处理

### 在线代码 (stereo_perception_multi_queue.cpp:3257-3285)
```cpp
bool is_k100 = HardwareDetector::getInstance().isK100Hardware();
cv::Mat dsg_input_img;

if (is_k100) {
    // K100 模式：裁剪到 640x432，然后 resize 到 640x384
    cv::Rect cropRegion432(0, 0, rectifyImageL.cols, 432);
    cv::Mat croppedImg432 = rectifyImageL(cropRegion432);
    cv::resize(croppedImg432, dsg_input_img, cv::Size(640, 384), 0, 0, cv::INTER_LINEAR);
} else {
    // bestmow 模式：直接裁剪到 640x384
    cv::Rect cropRegion384(0, 0, rectifyImageL.cols, 384);
    dsg_input_img = rectifyImageL(cropRegion384).clone();
}
```

### 离线代码 (offline_processor.cpp:99-106)
```cpp
// 裁剪到 640x384（无论 K100 还是 bestmow 模式）
cv::Rect crop_region(0, 0, 640, 384);
cropped_img = left_img(crop_region).clone();
resized_img = cropped_img.clone();
```

### ⚠️ **差异 1：图像裁剪策略不一致**
- **在线 K100 模式**：裁剪 640x432 → resize 到 640x384
- **离线代码**：统一裁剪 640x384（未区分 K100/bestmow）
- **影响**：K100 模式下输入图像的纵横比和内容可能不同

---

## 2. HSV 暗色过滤

### 在线代码 (stereo_perception_multi_queue.cpp:3313-3386)
```cpp
// 仅在 K100 模式下启用
if (is_k100 && m_enable_dsg_hsv_dark_filter) {
    cv::Mat hsvImg;
    cv::cvtColor(dsg_input_img, hsvImg, cv::COLOR_BGR2HSV);
    
    cv::Mat darkMask;
    cv::inRange(hsvImg, cv::Scalar(0, 0, 0), cv::Scalar(180, 50, 80), darkMask);
    
    // 优化：使用 3×3 核
    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(3, 3));
    cv::morphologyEx(darkMask, darkMask, cv::MORPH_CLOSE, kernel);
    
    // 支持障碍物保护
    if (m_enable_dsg_hsv_obstacle_protection) {
        // 构建障碍物掩码 (label==5 或 label>=100)
        // 从暗色掩码中排除障碍物区域
        cv::Mat safe_dark_mask = darkMask & ~obstacle_mask;
        lab_dst.setTo(3, safe_dark_mask);
    } else {
        lab_dst.setTo(3, darkMask);
    }
}
```

### 离线代码 (offline_processor.cpp:160-187)
```cpp
// 根据配置启用（未检查 K100 模式）
if (config_.enable_dsg_hsv_dark_filter) {
    cv::Mat hsvImg;
    cv::cvtColor(cropped_img, hsvImg, cv::COLOR_BGR2HSV);
    
    cv::Scalar lowerBlack(0, 0, 0);
    cv::Scalar upperBlack(180, 50, 80);
    
    cv::Mat darkMask;
    cv::inRange(hsvImg, lowerBlack, upperBlack, darkMask);
    
    // 使用 5×5 核
    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(5, 5));
    cv::morphologyEx(darkMask, darkMask, cv::MORPH_CLOSE, kernel);
    cv::morphologyEx(darkMask, darkMask, cv::MORPH_OPEN, kernel);
    
    // 无障碍物保护逻辑
    cv::Mat resizedMask;
    cv::resize(darkMask, resizedMask, lab_dst.size(), 0, 0, cv::INTER_NEAREST);
    lab_dst.setTo(3, resizedMask);
}
```

### ⚠️ **差异 2：HSV 过滤逻辑不一致**
- **在线代码**：
  - 条件：`is_k100 && m_enable_dsg_hsv_dark_filter`（强制 K100 模式）
  - 形态学核：3×3（优化版）
  - 支持障碍物保护（`m_enable_dsg_hsv_obstacle_protection`）
  
- **离线代码**：
  - 条件：仅检查 `config_.enable_dsg_hsv_dark_filter`（未检查 K100 模式）
  - 形态学核：5×5（两次操作：CLOSE + OPEN）
  - 无障碍物保护逻辑
  
- **影响**：bestmow 模式下可能错误启用 HSV 过滤

---

## 3. 点云融合函数选择

### 在线代码 (stereo_perception_multi_queue.cpp:3409-3417)
```cpp
// 根据硬件模式选择融合函数
if (is_k100) {
    stereo_multi_match.stereo_process_pci_depth_rgb_seg_det_fusion_dsg(
        depth_crop, lab_dst, dst_detections, dsg_input_img, xyz_rgbl_cloud,
        out_xyz_rgbl_cloud, m_enable_dsg_detection_in_pointcloud, m_enable_dsg_outlier_removal);
} else {
    stereo_multi_match.stereo_process_pci_depth_rgb_seg_det_fusion_bestmow(
        depth_crop, lab_dst, dst_detections, dsg_input_img, xyz_rgbl_cloud,
        out_xyz_rgbl_cloud);
}
```

### 离线代码 (offline_processor.cpp:233-236)
```cpp
// 统一使用通用融合函数（未区分 K100/bestmow）
stereo_matcher_.stereo_process_pci_depth_rgb_seg_det_fusion(
    result.depth, result.segmentation, result.detections,
    cropped_img, xyz_rgbl_cloud, out_xyz_rgbl_cloud);
```

### ⚠️ **差异 3：点云融合函数不一致**
- **在线代码**：
  - K100 模式：`stereo_process_pci_depth_rgb_seg_det_fusion_dsg`（标签感知 + 障碍物深度过滤）
  - bestmow 模式：`stereo_process_pci_depth_rgb_seg_det_fusion_bestmow`（通用融合）
  
- **离线代码**：
  - 统一使用：`stereo_process_pci_depth_rgb_seg_det_fusion`（通用融合）
  - 未根据 `use_k100_mode` 选择不同的融合函数
  
- **影响**：K100 模式下缺少标签感知过滤和障碍物深度一致性检查

---

## 4. 检测框保存逻辑

### 在线代码
```cpp
// 检测框 ID 修复为 100+id 模式
dst_detections.clear();
for (const auto& det : dect_src) {
    Detection fixed_det = det;
    fixed_det.id += 100;
    dst_detections.push_back(fixed_det);
}
```

### 离线代码 (offline_processor.cpp:327)
```cpp
// 保存检测结果（K100 模式）
if (config_.save_detection && hardware_mode_.isK100Hardware() && !result.detections.empty()) {
    cv::Mat det_img = result.cropped_img.clone();
    drawDetections(det_img, result.detections);
    std::string det_path = config_.output_dir + "/detection/" + image_name + "_det.png";
    cv::imwrite(det_path, det_img);
}
```

### ✅ **一致性：检测框保存逻辑正确**
- 离线代码正确检查了 `hardware_mode_.isK100Hardware()`
- 仅在 K100 模式下保存检测框

---

## 5. 立体匹配参数初始化

### 在线代码 (stereo_perception_multi_queue.cpp:1943-1960) - **已更新**
```cpp
// 初始化立体匹配参数：根据硬件模式和 fusion_model 选择
// mode 7 (DSG): K100 使用自适应参数，bestmow 使用固定参数
// 其他模式：统一使用原始参数
if (m_fusion_model == 7)
{
    if (is_k100) {
        stereo_multi_match.stereo_multi_param_init_6m_adaptive();
        RCLCPP_INFO(this->get_logger(),
                    "[✓] Stereo matcher initialized (K100 adaptive parameters for DSG night mode)");
    } else {
        stereo_multi_match.stereo_multi_param_init();
        RCLCPP_INFO(this->get_logger(),
                    "[✓] Stereo matcher initialized (bestmow fixed parameters for DSG)");
    }
}
else
{
    stereo_multi_match.stereo_multi_param_init();
    RCLCPP_INFO(this->get_logger(),
                "[✓] Stereo matcher initialized (original parameters)");
}
```

### 离线代码 (offline_processor.cpp:63-77)
```cpp
// Mode 7 (DSG) 使用自适应参数，其他模式使用原始参数
if (config_.infer_mode == 7) {
    stereo_matcher_.stereo_multi_param_init_6m_adaptive();
} else {
    stereo_matcher_.stereo_multi_param_init();
}
```

### ⚠️ **差异 4：立体匹配参数初始化不完整**
- **在线代码（最新版本）**：
  - DSG 模式 + K100：`param_init_6m_adaptive()`（自适应参数）
  - DSG 模式 + bestmow：`param_init()`（固定参数）
  - 非 DSG 模式：统一使用 `param_init()`
  
- **离线代码**：
  - DSG 模式：统一使用 `param_init_6m_adaptive()`（未区分 K100/bestmow）
  - 非 DSG 模式：统一使用 `param_init()`
  
- **影响**：DSG 模式下，bestmow 应该使用固定参数而非自适应参数

---

## 总结：关键差异

| 模块 | 在线代码 | 离线代码 | 是否一致 |
|------|---------|---------|---------|
| **图像裁剪** | K100: 640x432→384<br>bestmow: 640x384 | 统一 640x384 | ❌ 不一致 |
| **HSV 过滤条件** | `is_k100 && enable_filter` | 仅 `enable_filter` | ❌ 不一致 |
| **HSV 形态学核** | 3×3 (CLOSE) | 5×5 (CLOSE+OPEN) | ❌ 不一致 |
| **HSV 障碍物保护** | 支持 | 不支持 | ❌ 不一致 |
| **点云融合函数** | K100/bestmow 分别调用 | 统一调用通用函数 | ❌ 不一致 |
| **检测框保存** | K100 模式检查 | K100 模式检查 | ✅ 一致 |
| **立体匹配参数** | 根据模式和硬件选择 | DSG 模式正确，其他模式未区分 | ⚠️ 部分一致 |

---

## 修复建议

### 1. 修复图像裁剪逻辑
```cpp
// offline_processor.cpp:99-106
cv::Mat cropped_img, resized_img;

if (hardware_mode_.isK100Hardware()) {
    // K100 模式：裁剪到 640x432，然后 resize 到 640x384
    cv::Rect crop_region(0, 0, 640, 432);
    cv::Mat cropped_432 = left_img(crop_region).clone();
    cv::resize(cropped_432, resized_img, cv::Size(640, 384), 0, 0, cv::INTER_LINEAR);
    cropped_img = resized_img.clone();
} else {
    // bestmow 模式：直接裁剪到 640x384
    cv::Rect crop_region(0, 0, 640, 384);
    cropped_img = left_img(crop_region).clone();
    resized_img = cropped_img.clone();
}
```

### 2. 修复 HSV 过滤条件
```cpp
// offline_processor.cpp:160
if (hardware_mode_.isK100Hardware() && config_.enable_dsg_hsv_dark_filter) {
    // HSV 过滤逻辑
}
```

### 3. 修复 HSV 形态学操作
```cpp
// 使用 3×3 核，单次 CLOSE 操作（对齐在线优化版本）
cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(3, 3));
cv::morphologyEx(darkMask, darkMask, cv::MORPH_CLOSE, kernel);
```

### 4. 添加障碍物保护逻辑
```cpp
if (config_.enable_dsg_hsv_obstacle_protection) {
    // 构建障碍物掩码 (label==5 或 label>=100)
    cv::Mat obstacle_mask = cv::Mat::zeros(lab_dst.size(), CV_8UC1);
    for (int y = 0; y < lab_dst.rows; ++y) {
        const uint8_t* lab_ptr = lab_dst.ptr<uint8_t>(y);
        uint8_t* mask_ptr = obstacle_mask.ptr<uint8_t>(y);
        for (int x = 0; x < lab_dst.cols; ++x) {
            uint8_t label = lab_ptr[x];
            if (label == 5 || (label >= 100 && label <= 106)) {
                mask_ptr[x] = 255;
            }
        }
    }
    cv::Mat safe_dark_mask = darkMask & ~obstacle_mask;
    lab_dst.setTo(3, safe_dark_mask);
} else {
    lab_dst.setTo(3, darkMask);
}
```

### 5. 修复点云融合函数选择
```cpp
// offline_processor.cpp:233-236
if (hardware_mode_.isK100Hardware()) {
    stereo_matcher_.stereo_process_pci_depth_rgb_seg_det_fusion_dsg(
        result.depth, result.segmentation, result.detections,
        cropped_img, xyz_rgbl_cloud, out_xyz_rgbl_cloud,
        config_.enable_dsg_detection_in_pointcloud,
        config_.enable_dsg_outlier_removal);
} else {
    stereo_matcher_.stereo_process_pci_depth_rgb_seg_det_fusion_bestmow(
        result.depth, result.segmentation, result.detections,
        cropped_img, xyz_rgbl_cloud, out_xyz_rgbl_cloud);
}
```

### 6. 修复立体匹配参数初始化
```cpp
// offline_processor.cpp:63-77
if (config_.infer_mode == 7) {
    // DSG 模式：使用自适应参数
    stereo_matcher_.stereo_multi_param_init_6m_adaptive();
} else {
    // 其他模式：根据硬件选择参数
    if (hardware_mode_.isK100Hardware()) {
        stereo_matcher_.stereo_multi_param_init();
    } else {
        stereo_matcher_.stereo_multi_param_init_bestmow();
    }
}
```

---

## 验证方法

1. **切换 `use_k100_mode = true`**：
   - 检查是否使用 640x432→384 裁剪
   - 检查是否调用 `fusion_dsg` 函数
   - 检查 HSV 过滤是否正确启用

2. **切换 `use_k100_mode = false`**：
   - 检查是否使用 640x384 裁剪
   - 检查是否调用 `fusion_bestmow` 函数
   - 检查 HSV 过滤是否被禁用

3. **对比输出结果**：
   - 点云数量和分布
   - 分割标签分布
   - 检测框数量（K100 模式）
