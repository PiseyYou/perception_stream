#ifndef OFFLINE_UTILS_HPP
#define OFFLINE_UTILS_HPP

#include <opencv2/opencv.hpp>
#include <filesystem>
#include <vector>
#include <string>
#include <algorithm>

namespace fs = std::filesystem;

/**
 * @brief 扫描目录中的图像文件
 */
inline std::vector<std::string> scanImageFiles(const std::string& dir_path) {
    std::vector<std::string> image_files;

    if (!fs::exists(dir_path) || !fs::is_directory(dir_path)) {
        std::cerr << "[Error] Directory does not exist: " << dir_path << std::endl;
        return image_files;
    }

    for (const auto& entry : fs::directory_iterator(dir_path)) {
        if (!entry.is_regular_file()) continue;

        std::string ext = entry.path().extension().string();
        std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);

        if (ext == ".jpg" || ext == ".jpeg" || ext == ".png" || ext == ".bmp") {
            image_files.push_back(entry.path().string());
        }
    }

    // 按文件名排序
    std::sort(image_files.begin(), image_files.end());

    return image_files;
}

/**
 * @brief 从双目拼接图像中分割左右图
 * @param full_img 完整图像（1280x480 或其他）
 * @param left_img 输出左图
 * @param right_img 输出右图
 * @return true: 成功分割, false: 单目图像
 */
inline bool splitStereoImage(const cv::Mat& full_img, cv::Mat& left_img, cv::Mat& right_img) {
    int width = full_img.cols;
    int height = full_img.rows;

    // 典型双目格式：1280x480
    if (width == 1280 && height == 480) {
        int half_width = width / 2;
        left_img = full_img(cv::Rect(0, 0, half_width, height)).clone();
        right_img = full_img(cv::Rect(half_width, 0, half_width, height)).clone();
        return true;
    }

    // 单目图像
    left_img = full_img.clone();
    right_img = cv::Mat();
    return false;
}

/**
 * @brief 颜色查找表（用于分割可视化）
 */
inline std::array<cv::Vec3b, 256> getColorLookupTable() {
    std::array<cv::Vec3b, 256> lut;
    lut.fill(cv::Vec3b(0, 0, 0)); // 默认黑色

    // 初始化特定 ID 的颜色 (BGR 顺序)
    lut[0] = cv::Vec3b(0, 0, 0);        // black
    lut[1] = cv::Vec3b(200, 0, 0);      // background
    lut[2] = cv::Vec3b(102, 255, 100);  // grass
    lut[3] = cv::Vec3b(0, 89, 118);     // road
    lut[4] = cv::Vec3b(0, 255, 255);    // dynamic
    lut[5] = cv::Vec3b(0, 0, 255);      // static_obstacle
    lut[6] = cv::Vec3b(0, 165, 255);    // wall
    lut[7] = cv::Vec3b(147, 20, 255);   // vehicle
    lut[8] = cv::Vec3b(255, 255, 0);    // pole
    lut[9] = cv::Vec3b(48, 130, 245);   // impassable
    lut[10] = cv::Vec3b(128, 64, 0);    // depression
    lut[11] = cv::Vec3b(34, 139, 34);   // bush
    lut[12] = cv::Vec3b(203, 192, 255); // limb_bush
    lut[13] = cv::Vec3b(226, 43, 138);  // CES_arod

    // 100+ ID 映射（检测框）
    lut[100] = cv::Vec3b(0, 0, 255);   // pole
    lut[101] = cv::Vec3b(0, 0, 255);   // obst
    lut[102] = cv::Vec3b(0, 0, 255);   // fixo
    lut[103] = cv::Vec3b(255, 0, 255); // car
    lut[104] = cv::Vec3b(0, 0, 255);   // stat
    lut[105] = cv::Vec3b(0, 255, 255); // dyna
    lut[106] = cv::Vec3b(255, 255, 0); // charge_station
    lut[107] = cv::Vec3b(255, 0, 255); // person

    return lut;
}

/**
 * @brief 将单通道标签图转换为彩色可视化图
 */
inline cv::Mat labelToColor(const cv::Mat& label_img) {
    static const auto lut = getColorLookupTable();

    cv::Mat color_img(label_img.size(), CV_8UC3);

    for (int y = 0; y < label_img.rows; ++y) {
        const uint8_t* label_row = label_img.ptr<uint8_t>(y);
        cv::Vec3b* color_row = color_img.ptr<cv::Vec3b>(y);

        for (int x = 0; x < label_img.cols; ++x) {
            color_row[x] = lut[label_row[x]];
        }
    }

    return color_img;
}

/**
 * @brief 获取检测类别名称映射表
 */
inline std::map<int, std::string> getClassNameMap() {
    std::map<int, std::string> class_map;

    // 基础检测类别 (原始 ID)
    class_map[3] = "car";
    class_map[4] = "obstacle";
    class_map[6] = "charge_station";
    class_map[7] = "person";

    // 映射后的检测类别 (100+ ID)
    class_map[100] = "pole";
    class_map[101] = "obst";
    class_map[102] = "fixo";
    class_map[103] = "car";
    class_map[104] = "stat";
    class_map[105] = "dyna";
    class_map[106] = "charge_station";
    class_map[107] = "person";

    return class_map;
}

/**
 * @brief 在图像上绘制检测框
 */
inline void drawDetections(cv::Mat& img, const std::vector<Detection>& detections) {
    static const auto class_map = getClassNameMap();

    for (const auto& det : detections) {
        cv::Rect rect(det.bbox.xmin, det.bbox.ymin,
                      det.bbox.xmax - det.bbox.xmin,
                      det.bbox.ymax - det.bbox.ymin);

        // 绘制矩形框
        cv::rectangle(img, rect, cv::Scalar(0, 255, 0), 2);

        // 获取类别名称
        std::string class_name;
        auto it = class_map.find(det.id);
        if (it != class_map.end()) {
            class_name = it->second;
        } else {
            class_name = "id_" + std::to_string(det.id);
        }

        // 绘制标签和置信度
        std::string label = class_name + ":" + cv::format("%.2f", det.score);
        cv::putText(img, label,
                    cv::Point(det.bbox.xmin, std::max((int)det.bbox.ymin + 15, 15)),
                    cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(0, 255, 0), 1, cv::LINE_AA);
    }
}

/**
 * @brief 深度图可视化（伪彩色）
 */
inline cv::Mat visualizeDepth(const cv::Mat& depth, float max_depth = 10.0f) {
    cv::Mat depth_normalized;
    depth.convertTo(depth_normalized, CV_8UC1, 255.0 / max_depth);

    cv::Mat depth_color;
    cv::applyColorMap(depth_normalized, depth_color, cv::COLORMAP_JET);

    // 将无效深度（100.0f）设为黑色
    for (int y = 0; y < depth.rows; ++y) {
        const float* depth_row = depth.ptr<float>(y);
        cv::Vec3b* color_row = depth_color.ptr<cv::Vec3b>(y);

        for (int x = 0; x < depth.cols; ++x) {
            if (depth_row[x] >= 99.0f) {
                color_row[x] = cv::Vec3b(0, 0, 0);
            }
        }
    }

    return depth_color;
}

/**
 * @brief 创建输出目录
 */
inline void createOutputDirectories(const std::string& base_dir) {
    fs::create_directories(base_dir);
    fs::create_directories(base_dir + "/segmentation");
    fs::create_directories(base_dir + "/pointcloud");
    fs::create_directories(base_dir + "/detection");
    fs::create_directories(base_dir + "/depth");
    fs::create_directories(base_dir + "/combined");  // 添加合并图像目录
}

/**
 * @brief 绘制分割结果（纯色分割图 + 叠加图）
 * @param img_src 原始图像
 * @param img_lab 标签图
 * @param dect_src 检测框
 * @param img_seg_show 输出：叠加图（原图+分割+检测框）
 * @param enable_draw_box 是否绘制检测框
 * @return 纯色分割图（带检测框）
 */
inline cv::Mat drawResultOptimized(const cv::Mat& img_src, const cv::Mat& img_lab,
                                   const std::vector<Detection>& dect_src,
                                   cv::Mat& img_seg_show, bool enable_draw_box = false) {
    // 1. 生成纯色分割图
    cv::Mat pure_seg = labelToColor(img_lab);

    // 2. 生成叠加图（原图 + 半透明分割）
    img_seg_show = img_src.clone();
    cv::addWeighted(img_seg_show, 0.6, pure_seg, 0.4, 0, img_seg_show);

    // 3. 绘制检测框（如果启用）
    // 注意：在纯色分割图和叠加图上都绘制检测框
    if (enable_draw_box && !dect_src.empty()) {
        drawDetections(pure_seg, dect_src);      // 在纯色分割图上绘制
        drawDetections(img_seg_show, dect_src);  // 在叠加图上绘制
    }

    return pure_seg;
}

#endif // OFFLINE_UTILS_HPP
