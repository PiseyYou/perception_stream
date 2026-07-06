#include "offline_processor.hpp"
#include "semantic_depth_utils.hpp"
#include "offline_utils.hpp"
#include "stereo_point_cloud_rgbl.h"
#include "hardware_detector.hpp"
#include <pcl/io/pcd_io.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <iostream>
#include <map>
#include <limits>

// Helper function to filter labels and detections
static void filterLabelDect(cv::Mat &src_lab, std::vector<Detection> &dect_src,
                     cv::Mat &lab_dst, std::vector<Detection> &dect_dst,
                     bool enable_det)
{
    // 先克隆，避免污染原图
    src_lab.copyTo(lab_dst);

    cv::Mat mask_zero;
    cv::compare(lab_dst, 0, mask_zero, cv::CMP_EQ);

    // 将所有 label == 0 的像素设置为 label == 2
    lab_dst.setTo(2, mask_zero);

    for (size_t i = 0; i < dect_src.size(); i++)
    {
        Bbox obj_box = dect_src[i].bbox;
        int8_t target_id = dect_src[i].id;

        int xmin = std::max(static_cast<int>(std::lround(obj_box.xmin)), 0);
        int ymin = std::max(static_cast<int>(std::lround(obj_box.ymin)), 0);
        int xmax =
            std::min(static_cast<int>(std::lround(obj_box.xmax)), lab_dst.cols - 1);
        int ymax =
            std::min(static_cast<int>(std::lround(obj_box.ymax)), lab_dst.rows - 1);

        if (xmin >= xmax || ymin >= ymax)
            continue;

        cv::Rect rect_tmp(xmin, ymin, xmax - xmin, ymax - ymin);
        cv::Mat roi_dst = lab_dst(rect_tmp); // 操作目标图的 ROI

        auto process_roi = [&](int8_t set_value)
        {
            cv::Mat mask_one, mask_five;
            // ✅ 使用 uchar 类型匹配
            cv::inRange(roi_dst, cv::Scalar(1), cv::Scalar(1), mask_one);
            cv::inRange(roi_dst, cv::Scalar(5), cv::Scalar(5), mask_five);
            cv::Mat combined_mask = mask_one | mask_five;
            roi_dst.setTo(set_value, combined_mask);
        };

        if (target_id == 3)
        {
            if (enable_det) {
                process_roi(103);
            }
            Detection det_with_mapped_id = dect_src[i];
            det_with_mapped_id.id = 103;  // 将ID映射为103
            dect_dst.push_back(det_with_mapped_id);
        }
        else if (target_id == 6)
        {
            if (enable_det) {
                process_roi(106);
            }
            Detection det_with_mapped_id = dect_src[i];
            det_with_mapped_id.id = 106;  // 将ID映射为106
            dect_dst.push_back(det_with_mapped_id);
        }
        else if (target_id == 7)
        {
            // 人物检测：不修改 label，保持原始分割结果
            // if (enable_det) {
            //     process_roi(107);
            // }
            std::cout << "[person] have been dect....." << std::endl;
            Detection det_with_mapped_id = dect_src[i];
            det_with_mapped_id.id = 107;  // 将ID映射为107
            dect_dst.push_back(det_with_mapped_id);
        }
        else if (target_id == 4) // 障碍物检测框 (id=4 -> label=104)
        {
            // 统计检测框内的标签分布
            int count_background = 0; // label==1
            int count_walkable = 0;   // label==2 或 label==3 (草坪或道路)
            int total_pixels = 0;

            for (int y = 0; y < roi_dst.rows; y++)
            {
                for (int x = 0; x < roi_dst.cols; x++)
                {
                    uint8_t label = roi_dst.at<uchar>(y, x);
                    total_pixels++;
                    if (label == 1)
                        count_background++;
                    else if (label == 2 || label == 3)
                        count_walkable++;
                }
            }

            // 情况1: 检测框跨越背景(label==1)和可行走区域(label==2或3) - 过滤掉此检测框
            if (count_background > 0 && count_walkable > 0)
            {
                // 不添加到 dect_dst，直接跳过此检测框
                // 不对 label_map 做任何修改，保持原有分割结果
                continue;
            }
            // 情况2: 检测框完全在可行走区域(label==2或3)内
            else if (count_background == 0 && count_walkable > 0)
            {
                // 只有在 enable_det 为 true 时才修改 label
                if (enable_det) {
                    roi_dst.setTo(104);
                }
                Detection det_with_mapped_id = dect_src[i];
                det_with_mapped_id.id = 104;  // 将ID映射为104
                dect_dst.push_back(det_with_mapped_id);
            }
            // 情况3: 其他情况（主要是背景区域）
            else
            {
                // 只有在 enable_det 为 true 时才修改 label
                if (enable_det) {
                    // 只覆盖背景(1)和静态障碍物(5)
                    cv::Mat mask_one, mask_five;
                    cv::inRange(roi_dst, cv::Scalar(1), cv::Scalar(1), mask_one);
                    cv::inRange(roi_dst, cv::Scalar(5), cv::Scalar(5), mask_five);
                    cv::Mat combined_mask = mask_one | mask_five;
                    roi_dst.setTo(104, combined_mask);
                }
                Detection det_with_mapped_id = dect_src[i];
                det_with_mapped_id.id = 104;  // 将ID映射为104
                dect_dst.push_back(det_with_mapped_id);
            }
        }
        else
        {
            if (enable_det)
            {
                roi_dst.setTo(target_id + 100);
                Detection det_with_mapped_id = dect_src[i];
                det_with_mapped_id.id = target_id + 100;  // 将ID映射为id+100
                dect_dst.push_back(det_with_mapped_id);
            }
        }
    }
}

static std::vector<Detection> scaleDetectionsY(const std::vector<Detection>& detections,
                                               float y_scale,
                                               int max_height)
{
    std::vector<Detection> scaled = detections;
    for (auto& det : scaled) {
        det.bbox.ymin = std::max(0, static_cast<int>(std::lround(det.bbox.ymin * y_scale)));
        det.bbox.ymax = std::min(max_height, static_cast<int>(std::lround(det.bbox.ymax * y_scale)));
    }
    return scaled;
}

static void logSemanticRegionDiagnostics(const std::string& tag,
                                         const cv::Mat& label,
                                         const cv::Mat& depth,
                                         int x0,
                                         int y0,
                                         int x1,
                                         int y1)
{
    if (label.empty()) {
        return;
    }

    x0 = std::max(0, std::min(x0, label.cols));
    y0 = std::max(0, std::min(y0, label.rows));
    x1 = std::max(x0, std::min(x1, label.cols));
    y1 = std::max(y0, std::min(y1, label.rows));
    const cv::Rect roi(x0, y0, x1 - x0, y1 - y0);

    std::map<int, int> label_counts;
    int valid_depth_count = 0;
    int invalid_depth_count = 0;
    double depth_sum = 0.0;
    float min_depth = std::numeric_limits<float>::max();
    float max_depth = 0.0f;

    for (int y = roi.y; y < roi.y + roi.height; ++y) {
        const uchar* label_row = label.ptr<uchar>(y);
        const float* depth_row = (!depth.empty() && depth.rows == label.rows && depth.cols == label.cols)
                                     ? depth.ptr<float>(y)
                                     : nullptr;
        for (int x = roi.x; x < roi.x + roi.width; ++x) {
            label_counts[label_row[x]]++;
            if (depth_row) {
                const float d = depth_row[x];
                if (std::isfinite(d) && d > 0.0f && d < 6.0f) {
                    valid_depth_count++;
                    depth_sum += d;
                    min_depth = std::min(min_depth, d);
                    max_depth = std::max(max_depth, d);
                } else {
                    invalid_depth_count++;
                }
            }
        }
    }

    std::cout << "[Diag][" << tag << "] region x=" << roi.x << ", y=" << roi.y
              << ", w=" << roi.width << ", h=" << roi.height << std::endl;
    std::cout << "[Diag][" << tag << "] labels:";
    for (const auto& [label_id, count] : label_counts) {
        std::cout << " " << label_id << "=" << count;
    }
    std::cout << std::endl;

    if (!depth.empty() && depth.size() == label.size()) {
        const double mean_depth = valid_depth_count > 0 ? depth_sum / valid_depth_count : 0.0;
        std::cout << "[Diag][" << tag << "] depth valid=" << valid_depth_count
                  << ", invalid=" << invalid_depth_count
                  << ", mean_valid=" << mean_depth
                  << ", range=[" << (valid_depth_count > 0 ? min_depth : 0.0f)
                  << ", " << (valid_depth_count > 0 ? max_depth : 0.0f) << "]"
                  << std::endl;
    } else {
        std::cout << "[Diag][" << tag << "] depth skipped: label/depth size mismatch" << std::endl;
    }
}

static void logBottomSemanticDiagnostics(const std::string& stage,
                                         const cv::Mat& label,
                                         const cv::Mat& depth)
{
    if (label.empty()) {
        return;
    }

    const int bottom_y = label.rows * 3 / 5;
    logSemanticRegionDiagnostics(stage + ":bottom_center",
                                 label,
                                 depth,
                                 label.cols / 5,
                                 bottom_y,
                                 label.cols * 4 / 5,
                                 label.rows);
    logSemanticRegionDiagnostics(stage + ":bottom_right",
                                 label,
                                 depth,
                                 label.cols * 3 / 4,
                                 bottom_y,
                                 label.cols,
                                 label.rows);
}

static bool shouldLogFrame0336Diagnostics(const std::string& image_name)
{
    return image_name.find("match_0336") != std::string::npos ||
           image_name.find("0336") != std::string::npos;
}

static int countValidDepthInLabelRoi(const cv::Mat& label,
                                     const cv::Mat& depth,
                                     const cv::Rect& roi,
                                     uchar target_label)
{
    if (label.empty() || depth.empty() || label.size() != depth.size()) {
        return 0;
    }

    const cv::Rect safe_roi = roi & cv::Rect(0, 0, label.cols, label.rows);
    int count = 0;
    for (int y = safe_roi.y; y < safe_roi.y + safe_roi.height; ++y) {
        const uchar* label_row = label.ptr<uchar>(y);
        const float* depth_row = depth.ptr<float>(y);
        for (int x = safe_roi.x; x < safe_roi.x + safe_roi.width; ++x) {
            const float d = depth_row[x];
            if (label_row[x] == target_label &&
                std::isfinite(d) && d > 0.0f && d < 6.0f) {
                ++count;
            }
        }
    }
    return count;
}

static int countLabelInRoi(const cv::Mat& label,
                           const cv::Rect& roi,
                           uchar target_label)
{
    if (label.empty()) {
        return 0;
    }

    const cv::Rect safe_roi = roi & cv::Rect(0, 0, label.cols, label.rows);
    int count = 0;
    for (int y = safe_roi.y; y < safe_roi.y + safe_roi.height; ++y) {
        const uchar* label_row = label.ptr<uchar>(y);
        for (int x = safe_roi.x; x < safe_roi.x + safe_roi.width; ++x) {
            if (label_row[x] == target_label) {
                ++count;
            }
        }
    }
    return count;
}

static void logFrame0336RoiDepthStage(const std::string& stage,
                                      const cv::Mat& label,
                                      const cv::Mat& depth)
{
    if (label.empty()) {
        return;
    }

    const int bottom_y = label.rows * 3 / 5;
    const std::array<std::pair<const char*, cv::Rect>, 3> rois = {{
        {"bottom_semantic", cv::Rect(label.cols / 5, bottom_y,
                                     label.cols - label.cols / 5,
                                     label.rows - bottom_y)},
        {"bottom_right", cv::Rect(label.cols * 3 / 4, bottom_y,
                                  label.cols - label.cols * 3 / 4,
                                  label.rows - bottom_y)},
        {"bottom_right_wide", cv::Rect(label.cols * 3 / 5, bottom_y,
                                       label.cols - label.cols * 3 / 5,
                                       label.rows - bottom_y)}
    }};

    for (const auto& [name, roi] : rois) {
        const int label6_pixels = countLabelInRoi(label, roi, 6);
        const int valid_label6_depth =
            countValidDepthInLabelRoi(label, depth, roi, 6);
        std::cout << "[Diag][0336][" << stage << ":" << name << "]"
                  << " label6_pixels=" << label6_pixels
                  << ", valid_label6_depth=" << valid_label6_depth
                  << std::endl;
    }
}

static int countLabelInPointCloudRoi(const pcl::PointCloud<pcl::PointXYZRGBL>& cloud,
                                     int image_cols,
                                     int image_rows,
                                     const cv::Rect& roi,
                                     uint32_t target_label,
                                     double fx,
                                     double fy,
                                     double cx,
                                     double cy)
{
    const cv::Rect safe_roi = roi & cv::Rect(0, 0, image_cols, image_rows);
    int count = 0;
    for (const auto& point : cloud.points) {
        if (point.label != target_label || point.z <= 0.0f) {
            continue;
        }
        const int x = static_cast<int>(std::lround(point.x * fx / point.z + cx));
        const int y = static_cast<int>(std::lround(point.y * fy / point.z + cy));
        if (safe_roi.contains(cv::Point(x, y))) {
            ++count;
        }
    }
    return count;
}

static void logFrame0336PointCloudStage(
    const pcl::PointCloud<pcl::PointXYZRGBL>& cloud,
    const cv::Mat& label,
    const StereoMultiMatch& stereo_matcher)
{
    if (label.empty()) {
        return;
    }

    int total_label6 = 0;
    for (const auto& point : cloud.points) {
        if (point.label == 6) {
            ++total_label6;
        }
    }

    const int bottom_y = label.rows * 3 / 5;
    const cv::Rect bottom_semantic(label.cols / 5, bottom_y,
                                   label.cols - label.cols / 5,
                                   label.rows - bottom_y);
    const cv::Rect bottom_right(label.cols * 3 / 4, bottom_y,
                                label.cols - label.cols * 3 / 4,
                                label.rows - bottom_y);

    std::cout << "[Diag][0336][pointcloud]"
              << " label6_points=" << total_label6
              << ", bottom_semantic_label6_points="
              << countLabelInPointCloudRoi(cloud, label.cols, label.rows,
                                           bottom_semantic, 6,
                                           stereo_matcher.fx, stereo_matcher.fy,
                                           stereo_matcher.cx, stereo_matcher.cy)
              << ", bottom_right_label6_points="
              << countLabelInPointCloudRoi(cloud, label.cols, label.rows,
                                           bottom_right, 6,
                                           stereo_matcher.fx, stereo_matcher.fy,
                                           stereo_matcher.cx, stereo_matcher.cy)
              << std::endl;
}

OfflineProcessor::OfflineProcessor(const OfflineConfig& config)
    : config_(config),
      hardware_mode_(config.use_k100_mode) {
}

OfflineProcessor::~OfflineProcessor() {
    if (initialized_) {
        if (config_.infer_mode == 6) {
            mul_sub_perception_.perception_release();
        } else if (config_.infer_mode == 7) {
            dsg_perception_.perception_release();
        }
    }
}

bool OfflineProcessor::init() {
    std::cout << "\n[Init] Initializing offline processor..." << std::endl;
    std::cout << "[Init] Hardware mode: " << hardware_mode_.getHardwareModel() << std::endl;
    std::cout << "[Init] Inference mode: " << config_.infer_mode << std::endl;

    // 根据推理模式初始化对应的感知模块
    if (config_.infer_mode == 6) {
        // 初始化 Multi-Sub 感知模块
        if (!initMulSubPerception()) {
            std::cerr << "[Error] Failed to initialize Multi-Sub perception" << std::endl;
            return false;
        }
    } else if (config_.infer_mode == 7) {
        // 初始化 DSG 感知模块
        if (!initDSGPerception()) {
            std::cerr << "[Error] Failed to initialize DSG perception" << std::endl;
            return false;
        }
    } else {
        std::cerr << "[Error] Unsupported inference mode: " << config_.infer_mode << std::endl;
        return false;
    }

    // 初始化 CDT 模块（如果启用）
    if (config_.enable_cdt) {
        if (!initCDTPerception()) {
            std::cerr << "[Error] Failed to initialize CDT perception" << std::endl;
            return false;
        }
    }

    // 初始化立体匹配模块
    if (!initStereoMatcher()) {
        std::cerr << "[Error] Failed to initialize stereo matcher" << std::endl;
        return false;
    }

    initialized_ = true;
    std::cout << "[Init] Initialization completed successfully" << std::endl;
    return true;
}

bool OfflineProcessor::initMulSubPerception() {
    std::string model_path = config_.model_dir + config_.mul_sub_model_name;
    std::cout << "[Init] Loading Multi-Sub model: " << model_path << std::endl;

    // 检查模型文件是否存在
    if (!std::filesystem::exists(model_path)) {
        std::cerr << "[Error] Model file does not exist: " << model_path << std::endl;
        return false;
    }

    try {
        mul_sub_perception_.perception_init(model_path.c_str());
        std::cout << "[Init] Multi-Sub model loaded successfully" << std::endl;
        return true;
    } catch (const std::exception& e) {
        std::cerr << "[Error] Multi-Sub model loading failed: " << e.what() << std::endl;
        return false;
    }
}

bool OfflineProcessor::initDSGPerception() {
    std::string model_path = config_.model_dir + config_.dsg_model_name;
    std::cout << "[Init] Loading DSG model: " << model_path << std::endl;

    // 检查 HardwareDetector 状态
    std::string hw_model = HardwareDetector::getInstance().getHardwareModel();
    std::string hw_status = HardwareDetector::getInstance().getDetectionStatus();
    bool hw_is_k100 = HardwareDetector::getInstance().isK100Hardware();

    std::cout << "[Init] HardwareDetector status:" << std::endl;
    std::cout << "  - Model: " << hw_model << std::endl;
    std::cout << "  - Status: " << hw_status << std::endl;
    std::cout << "  - Is K100: " << (hw_is_k100 ? "yes" : "no") << std::endl;

    // 检查配置不匹配
    if (hardware_mode_.isK100Hardware() != hw_is_k100) {
        std::cerr << "[Warning] Hardware mode mismatch!" << std::endl;
        std::cerr << "  - OfflineConfig: " << (hardware_mode_.isK100Hardware() ? "K100" : "bestmow") << std::endl;
        std::cerr << "  - HardwareDetector: " << (hw_is_k100 ? "K100" : "bestmow") << std::endl;
        std::cerr << "  - DSG will use HardwareDetector mode!" << std::endl;
    }

    // 检查模型文件是否存在
    if (!std::filesystem::exists(model_path)) {
        std::cerr << "[Error] Model file does not exist: " << model_path << std::endl;
        return false;
    }

    try {
        dsg_perception_.perception_init(model_path.c_str());

        // K100 模式才需要设置 ori_width/ori_height
        // bestmow 模式不需要这些成员变量

        std::cout << "[Init] DSG model loaded successfully" << std::endl;
        return true;
    } catch (const std::exception& e) {
        std::cerr << "[Error] DSG model loading failed: " << e.what() << std::endl;
        return false;
    }
}

bool OfflineProcessor::initStereoMatcher() {
    std::cout << "[Init] Initializing stereo matcher..." << std::endl;

    // 根据推理模式选择参数初始化方法
    // Mode 7 (DSG 夜间模式) 使用自适应参数，其他模式使用原始参数
    if (config_.infer_mode == 7) {
        stereo_matcher_.stereo_multi_param_init_6m_adaptive();
        std::cout << "[Init] Stereo matcher initialized (adaptive parameters for night mode)" << std::endl;
    } else {
        stereo_matcher_.stereo_multi_param_init();
        std::cout << "[Init] Stereo matcher initialized (original parameters)" << std::endl;
    }

    return true;
}

bool OfflineProcessor::initCDTPerception() {
    std::string model_path = config_.model_dir + config_.cdt_model_name;
    std::cout << "[Init] Loading CDT model: " << model_path << std::endl;

    // 检查模型文件是否存在
    if (!std::filesystem::exists(model_path)) {
        std::cerr << "[Error] CDT model file does not exist: " << model_path << std::endl;
        return false;
    }

    try {
        cdt_perception_.perception_init(model_path.c_str());
        std::cout << "[Init] CDT model loaded successfully" << std::endl;
        return true;
    } catch (const std::exception& e) {
        std::cerr << "[Error] CDT model loading failed: " << e.what() << std::endl;
        return false;
    }
}

OfflineProcessor::ProcessResult OfflineProcessor::process(
    const cv::Mat& left_img,
    const cv::Mat& right_img,
    const std::string& image_name) {

    ProcessResult result;

    if (!initialized_) {
        std::cerr << "[Error] Processor not initialized" << std::endl;
        return result;
    }

    if (left_img.empty()) {
        std::cerr << "[Error] Left image is empty" << std::endl;
        return result;
    }

    std::cout << "\n[Process] Processing image: " << image_name << std::endl;

    // 根据推理模式调用不同的处理流程
    if (config_.infer_mode == 6) {
        return processModel6(left_img, right_img, image_name);
    } else if (config_.infer_mode == 7) {
        return processModel7(left_img, right_img, image_name);
    } else {
        std::cerr << "[Error] Unsupported inference mode: " << config_.infer_mode << std::endl;
        return result;
    }
}

OfflineProcessor::ProcessResult OfflineProcessor::processModel6(
    const cv::Mat& left_img,
    const cv::Mat& right_img,
    const std::string& image_name) {

    ProcessResult result;
    std::cout << "[Process] Using Model 6 (Sub/multi_sub)" << std::endl;

    // ========== 图像裁剪和预处理 ==========
    cv::Mat cropped_img, resized_img;
    cv::Mat lab_dst;

    if (hardware_mode_.isK100Hardware()) {
        // K100 模式：裁剪到 640x432，然后 resize 到 640x384
        std::cout << "[Process] Model 6 K100 mode: Crop to 640x432, then resize to 640x384" << std::endl;
        cv::Rect crop_region(0, 0, 640, 432);
        cropped_img = left_img(crop_region).clone();
        cv::resize(cropped_img, resized_img, cv::Size(640, 384), 0, 0, cv::INTER_LINEAR);
    } else {
        // bestmow 模式：直接裁剪到 640x384
        std::cout << "[Process] Model 6 bestmow mode: Crop to 640x384" << std::endl;
        cv::Rect crop_region(0, 0, 640, 384);
        cropped_img = left_img(crop_region).clone();
        resized_img = cropped_img.clone();
    }
    result.cropped_img = cropped_img;

    // ========== 1. Multi-Sub 推理 ==========
    std::cout << "[Process] Running Multi-Sub inference..." << std::endl;

    std::vector<Detection> detections, dst_detections;
    cv::Mat img_label384 = cv::Mat::zeros(384, 640, CV_8UC1) + 2;
    cv::Mat lab_out;

    mul_sub_perception_.perception_process_bgr_no_argmax_erode(
        resized_img, detections, img_label384, lab_out, config_.erode_pixel);

    // ========== 1.5 CDT 检测（如果启用） ==========
    cv::Rect cdt_rect;
    if (config_.enable_cdt) {
        std::cout << "[Process] Running CDT detection..." << std::endl;
        std::vector<Detection> cdt_detections;
        cdt_perception_.perception_process_bgr(resized_img, cdt_detections);
        cdt_rect = get_cdt_rect(cdt_detections);

        if (cdt_rect.area() > 0) {
            std::cout << "[Process] CDT detected at: " << cdt_rect << std::endl;
        } else {
            std::cout << "[Process] No valid CDT detection" << std::endl;
        }
    }

    cv::Mat dst_label384(384, 640, CV_8UC1);
    filterLabelDect(lab_out, detections, dst_label384, dst_detections,
                    config_.enable_draw_detection_box);

    // 应用 CDT 掩码（在 640x384 尺度）
    if (config_.enable_cdt && cdt_rect.area() > 0) {
        dst_label384(cdt_rect).setTo(-1);  // 标记为无效区域
        std::cout << "[Process] CDT mask applied to segmentation" << std::endl;
    }

    // ========== 1.8 红色砖头后处理（在 640x384 尺度） ==========
    if (config_.enable_red_brick_refine) {
        std::cout << "[Process] Applying red brick refinement..." << std::endl;
        refineObstacleByColorAndEdge(dst_label384, resized_img, config_.red_brick_min_area);
    }

    result.detections = dst_detections;
    result.segmentation = dst_label384;
    cv::Mat fusion_label = dst_label384;
    cv::Mat fusion_img = resized_img;
    std::vector<Detection> fusion_detections = dst_detections;

    if (dst_label384.empty()) {
        std::cerr << "[Error] lab_dst is empty after Multi-Sub inference!" << std::endl;
        return result;
    }

    // ========== 2. 立体匹配 ==========
    if (!right_img.empty()) {
        std::cout << "[Process] Computing stereo depth..." << std::endl;

        cv::Mat left_gray, right_gray;
        if (left_img.channels() == 3) {
            cv::cvtColor(left_img, left_gray, cv::COLOR_BGR2GRAY);
        } else {
            left_gray = left_img;
        }

        if (right_img.channels() == 3) {
            cv::cvtColor(right_img, right_gray, cv::COLOR_BGR2GRAY);
        } else {
            right_gray = right_img;
        }

        cv::Mat depth_480;
        cv::Mat depth_before_morph_480;
        const bool log_0336 = shouldLogFrame0336Diagnostics(image_name);

        if (hardware_mode_.isK100Hardware()) {
            cv::Mat fusion_label_480;
            cv::resize(dst_label384, fusion_label_480, cv::Size(640, 432),
                       0, 0, cv::INTER_NEAREST);
            cv::copyMakeBorder(fusion_label_480, fusion_label_480, 0,
                               480 - fusion_label_480.rows, 0, 0,
                               cv::BORDER_CONSTANT, cv::Scalar(2));

            cv::Mat disparity = stereo_matcher_.stereo_multi_process_depth(left_gray, right_gray);
            if (log_0336) {
                cv::Mat sgbm_depth;
                double bf = std::abs(stereo_matcher_.Pr.at<double>(0, 3));
                cv::Mat disparity_480;
                cv::resize(disparity, disparity_480, left_gray.size(), 0, 0,
                           cv::INTER_NEAREST);
                disparity_480 *= 2.0f;
                cv::divide(bf, disparity_480, sgbm_depth, 1, CV_32F);
                sgbm_depth.setTo(100.0f, disparity_480 <= 0.01f);
                logFrame0336RoiDepthStage("sgbm", fusion_label_480, sgbm_depth);
            }

            depth_480 = stereo_matcher_.stereo_multi_process_filter(
                disparity, fusion_label_480, false);

            // K100 模式：深度保持 640x432；融合前将 384 标签还原到 432
            result.depth = depth_480(cv::Rect(0, 0, 640, 432)).clone();
            cv::resize(dst_label384, fusion_label, cv::Size(640, 432), 0, 0, cv::INTER_NEAREST);
            fusion_img = cropped_img;
            fusion_detections = scaleDetectionsY(dst_detections, 432.0f / 384.0f, 432);
            std::cout << "[Process] Model 6 K100 mode: Depth cropped to 432 for fusion" << std::endl;
            if (log_0336) {
                logFrame0336RoiDepthStage(
                    "multiscale_before_morph",
                    fusion_label,
                    result.depth);
                logFrame0336RoiDepthStage("after_morph", fusion_label, result.depth);
            }
        } else {
            // bestmow 模式保持原参考路径：直接在原始 640x480 灰度图上计算深度
            depth_480 = stereo_matcher_.stereo_multi_process(left_gray, right_gray, false);
            // bestmow 模式：深度直接裁剪到 384 用于融合
            result.depth = depth_480(cv::Rect(0, 0, 640, 384)).clone();
            fusion_label = dst_label384;
            fusion_img = resized_img;
            fusion_detections = dst_detections;
            std::cout << "[Process] Model 6 bestmow mode: Depth cropped to 384" << std::endl;
        }

        std::cout << "[Process] Depth map computed: " << result.depth.size() << std::endl;
        if (hardware_mode_.isK100Hardware()) {
            logBottomSemanticDiagnostics("before_inpaint", fusion_label, result.depth);
            if (log_0336) {
                logFrame0336RoiDepthStage("before_inpaint", fusion_label, result.depth);
            }
        }

        // ========== 2.5 深度补全（可选） ==========
        if (config_.depth_inpainting_strategy > 0 && !result.depth.empty()) {
            std::cout << "[Process] Applying depth inpainting (strategy: "
                      << config_.depth_inpainting_strategy << ")..." << std::endl;

            // 策略1或3: 基于检测框的补全
            if (config_.depth_inpainting_strategy == 1 || config_.depth_inpainting_strategy == 3) {
                result.depth = depthInpaintingByDetections(result.depth, fusion_label, fusion_detections);
            }

            // 策略2或3: 基于语义分割的补全
            if (config_.depth_inpainting_strategy == 2 || config_.depth_inpainting_strategy == 3) {
                result.depth = depthInpaintingForObstacles(result.depth, fusion_label);
            }

            std::cout << "[Process] Depth inpainting completed" << std::endl;
            if (hardware_mode_.isK100Hardware()) {
                logBottomSemanticDiagnostics("after_inpaint", fusion_label, result.depth);
                if (log_0336) {
                    logFrame0336RoiDepthStage("after_inpaint", fusion_label, result.depth);
                }
            }
        }

        if (hardware_mode_.isK100Hardware()) {
            logBottomSemanticDiagnostics("final", fusion_label, result.depth);
            if (log_0336) {
                logFrame0336RoiDepthStage("final_depth", fusion_label, result.depth);
            }
        }
    } else {
        std::cout << "[Process] No right image, skipping stereo matching" << std::endl;
    }

    // ========== 3. 点云融合 ==========
    if (!result.depth.empty()) {
        std::cout << "[Process] Generating point cloud..." << std::endl;

        pcl::PointCloud<pcl::PointXYZRGBL> xyz_rgbl_cloud;
        pcl::PointCloud<pcl::PointXYZRGBL> out_xyz_rgbl_cloud;

        if (hardware_mode_.isK100Hardware()) {
            stereo_matcher_.stereo_process_pci_depth_rgb_seg_det_fusion(
                result.depth, fusion_label, fusion_detections,
                fusion_img,  // K100: 640x432
                xyz_rgbl_cloud, out_xyz_rgbl_cloud);
        } else {
            stereo_matcher_.stereo_process_pci_depth_rgb_seg_det_fusion_bestmow(
                result.depth, fusion_label, fusion_detections,
                fusion_img,  // bestmow: 640x384
                xyz_rgbl_cloud, out_xyz_rgbl_cloud);
        }

        result.pointcloud = out_xyz_rgbl_cloud;
        std::cout << "[Process] Point cloud generated: " << out_xyz_rgbl_cloud.size() << " points" << std::endl;
        if (hardware_mode_.isK100Hardware() && shouldLogFrame0336Diagnostics(image_name)) {
            logFrame0336PointCloudStage(out_xyz_rgbl_cloud, fusion_label, stereo_matcher_);
        }
    }

    result.success = true;
    return result;
}

OfflineProcessor::ProcessResult OfflineProcessor::processModel7(
    const cv::Mat& left_img,
    const cv::Mat& right_img,
    const std::string& image_name) {

    ProcessResult result;
    std::cout << "[Process] Using Model 7 (DSG)" << std::endl;

    // ========== 图像裁剪和预处理 ==========
    cv::Mat cropped_img, resized_img;
    cv::Mat dsg_fusion_img;
    cv::Mat lab_dst;

    // 根据硬件模式选择裁剪尺寸
    if (hardware_mode_.isK100Hardware()) {
        // K100 模式：裁剪到 640x432，然后 resize 到 640x384
        std::cout << "[Process] K100 mode: Crop to 640x432, then resize to 640x384" << std::endl;
        cv::Rect crop_region(0, 0, 640, 432);
        cropped_img = left_img(crop_region).clone();
        dsg_fusion_img = cropped_img.clone();
        cv::resize(cropped_img, resized_img, cv::Size(640, 384));
    } else {
        // bestmow 模式：直接裁剪到 640x384
        std::cout << "[Process] bestmow mode: Crop to 640x384" << std::endl;
        cv::Rect crop_region(0, 0, 640, 384);
        cropped_img = left_img(crop_region).clone();
        resized_img = cropped_img.clone();
        dsg_fusion_img = resized_img;
    }

    // ========== 1. DSG 推理 ==========
    std::cout << "[Process] Running DSG inference..." << std::endl;

    // 使用本地 DSG 接口进行推理，输入尺寸保持与参考流程一致（640x384）。
    std::vector<Detection> dect_src;

    dsg_perception_.process_infer_match(resized_img, lab_dst);

    std::cout << "[Debug] After inference - lab_dst stats:" << std::endl;
    if (!lab_dst.empty()) {
        cv::Scalar lab_dst_mean = cv::mean(lab_dst);
        double lab_dst_min, lab_dst_max;
        cv::minMaxLoc(lab_dst, &lab_dst_min, &lab_dst_max);
        std::cout << "  size: " << lab_dst.size()
                  << ", mean: " << lab_dst_mean[0]
                  << ", min: " << lab_dst_min
                  << ", max: " << lab_dst_max << std::endl;
    } else {
        std::cout << "  lab_dst is EMPTY!" << std::endl;
    }

    if (lab_dst.empty()) {
        std::cerr << "[Error] lab_dst is empty after DSG inference!" << std::endl;
        return result;
    }

    // ========== 1.5 CDT 检测（如果启用） ==========
    cv::Rect cdt_rect;
    if (config_.enable_cdt) {
        std::cout << "[Process] Running CDT detection..." << std::endl;
        std::vector<Detection> cdt_detections;
        cdt_perception_.perception_process_bgr(cropped_img, cdt_detections);
        cdt_rect = get_cdt_rect(cdt_detections);

        if (cdt_rect.area() > 0) {
            std::cout << "[Process] CDT detected at: " << cdt_rect << std::endl;
            // 应用 CDT 掩码到分割结果
            lab_dst(cdt_rect).setTo(-1);  // 标记为无效区域
            std::cout << "[Process] CDT mask applied to segmentation" << std::endl;
        } else {
            std::cout << "[Process] No valid CDT detection" << std::endl;
        }
    }

    // ========== 检测框处理（对齐参考代码） ==========
    std::vector<Detection> dst_detections;
    dst_detections.clear();

    // 根据配置决定是否处理检测框
    bool enable_draw_box = config_.enable_draw_detection_box;
    if (enable_draw_box) {
        for (const auto& det : dect_src) {
            Detection fixed_det = det;
            fixed_det.id += 100;  // 映射到 100+ 格式
            dst_detections.push_back(fixed_det);
        }
    }
    result.detections = dst_detections;

    // 更新分割结果（lab_dst 已经是 640x384）
    result.segmentation = lab_dst;
    cv::Mat fusion_label = lab_dst;
    std::vector<Detection> fusion_detections = dst_detections;

    // ========== HSV 暗区域滤波（可选） ==========
    if (config_.enable_dsg_hsv_dark_filter) {
        std::cout << "[Process] Applying HSV dark filter..." << std::endl;

        if (resized_img.channels() != 3) {
            std::cout << "[Warning] DSG HSV input image is not 3-channel, skip dark filter" << std::endl;
        } else if (lab_dst.empty() || lab_dst.size() != resized_img.size()) {
            std::cout << "[Warning] DSG HSV lab/image size mismatch, skip dark filter. lab="
                      << lab_dst.size() << ", image=" << resized_img.size() << std::endl;
        } else {
            cv::Mat hsvImg;
            cv::cvtColor(resized_img, hsvImg, cv::COLOR_BGR2HSV);

            cv::Mat darkMask;
            cv::inRange(hsvImg, cv::Scalar(0, 0, 0), cv::Scalar(180, 50, 80), darkMask);

            cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(3, 3));
            cv::morphologyEx(darkMask, darkMask, cv::MORPH_CLOSE, kernel);

            if (darkMask.size() != lab_dst.size()) {
                cv::resize(darkMask, darkMask, lab_dst.size(), 0, 0, cv::INTER_NEAREST);
            }

            if (config_.enable_dsg_hsv_obstacle_protection) {
                cv::Mat obstacle_mask = cv::Mat::zeros(lab_dst.size(), CV_8UC1);

                const int rows = lab_dst.rows;
                const int cols = lab_dst.cols;
                for (int y = 0; y < rows; ++y) {
                    const uint8_t* lab_ptr = lab_dst.ptr<uint8_t>(y);
                    uint8_t* mask_ptr = obstacle_mask.ptr<uint8_t>(y);
                    for (int x = 0; x < cols; ++x) {
                        uint8_t label = lab_ptr[x];
                        if (label == 5 || (label >= 100 && label <= 106)) {
                            mask_ptr[x] = 255;
                        }
                    }
                }

                cv::Mat safe_dark_mask = darkMask & ~obstacle_mask;
                lab_dst.setTo(3, safe_dark_mask);
                std::cout << "[Process] HSV dark filter applied with obstacle protection" << std::endl;
            } else {
                lab_dst.setTo(3, darkMask);
                std::cout << "[Process] HSV dark filter applied without obstacle protection" << std::endl;
            }

            result.segmentation = lab_dst;
        }
    }

    // ========== 2. 立体匹配 ==========
    if (!right_img.empty()) {
        std::cout << "[Process] Computing stereo depth..." << std::endl;

        // 转换为灰度图（立体匹配需要 CV_8UC1 格式）
        cv::Mat left_gray, right_gray;
        if (left_img.channels() == 3) {
            cv::cvtColor(left_img, left_gray, cv::COLOR_BGR2GRAY);
        } else {
            left_gray = left_img;
        }

        if (right_img.channels() == 3) {
            cv::cvtColor(right_img, right_gray, cv::COLOR_BGR2GRAY);
        } else {
            right_gray = right_img;
        }

        // 立体匹配（输出 640x480）
        cv::Mat depth_480 = stereo_matcher_.stereo_multi_process(
            left_gray,
            right_gray,
            false);  // DSG 模式固定不启用 height filter

        std::cout << "[Process] Depth map computed: " << depth_480.size() << std::endl;

        const int fusion_height = hardware_mode_.isK100Hardware() ? 432 : 384;
        fusion_label = lab_dst;
        fusion_detections = dst_detections;

        if (hardware_mode_.isK100Hardware()) {
            cv::resize(lab_dst, fusion_label, cv::Size(640, fusion_height), 0, 0, cv::INTER_NEAREST);
            fusion_detections = scaleDetectionsY(dst_detections, 432.0f / 384.0f, fusion_height);
        }

        // 根据硬件模式裁剪深度图；K100 保持 640x432 与融合图对齐
        if (hardware_mode_.isK100Hardware()) {
            result.depth = depth_480(cv::Rect(0, 0, 640, fusion_height)).clone();
            std::cout << "[Process] K100 mode: Depth cropped to 432 for fusion" << std::endl;
        } else {
            // bestmow 模式：直接裁剪到 640x384
            result.depth = depth_480(cv::Rect(0, 0, 640, fusion_height)).clone();
            std::cout << "[Process] bestmow mode: Depth cropped to 384" << std::endl;
        }
    } else {
        std::cout << "[Process] No right image, skipping stereo matching" << std::endl;
    }

    // ========== 3. 点云融合 ==========
    if (!result.depth.empty()) {
        std::cout << "[Process] Generating point cloud..." << std::endl;
        std::cout << "[Debug] depth size: " << result.depth.size()
                  << ", fusion label size: " << fusion_label.size()
                  << ", fusion image size: " << dsg_fusion_img.size() << std::endl;

        pcl::PointCloud<pcl::PointXYZRGBL> xyz_rgbl_cloud;
        pcl::PointCloud<pcl::PointXYZRGBL> out_xyz_rgbl_cloud;

        // DSG 模式使用专用融合函数，与在线逻辑保持一致
        stereo_matcher_.stereo_process_pci_depth_rgb_seg_det_fusion_dsg(
            result.depth, fusion_label, fusion_detections,
            dsg_fusion_img,
            xyz_rgbl_cloud, out_xyz_rgbl_cloud,
            config_.enable_dsg_detection_in_pointcloud,
            config_.enable_dsg_outlier_removal);

        result.pointcloud = out_xyz_rgbl_cloud;
        result.cropped_img = cropped_img;  // 保存原始裁剪图像（K100: 432, bestmow: 384）
        std::cout << "[Process] Point cloud generated: " << out_xyz_rgbl_cloud.size() << " points" << std::endl;
    }

    result.success = true;
    return result;
}

void OfflineProcessor::saveResults(const ProcessResult& result,
                                    const std::string& image_name,
                                    const cv::Mat& original_img) {
    if (!result.success) {
        std::cerr << "[Save] Cannot save results: processing failed" << std::endl;
        return;
    }

    std::cout << "[Save] Saving results for: " << image_name << std::endl;

    // ========== 合并可视化保存 ==========
    if (config_.enable_debug_show && !result.cropped_img.empty() && !result.segmentation.empty()) {
        std::cout << "[Debug] Creating visualization..." << std::endl;
        std::cout << "[Debug] cropped_img: " << result.cropped_img.size()
                  << ", segmentation: " << result.segmentation.size() << std::endl;

        cv::Mat img_seg_show, pure_seg_mat;
        cv::Mat vis_cropped_img, vis_segmentation;
        std::vector<Detection> vis_detections = result.detections;

        // 根据推理模式和硬件模式调整可视化图像尺寸
        if (config_.infer_mode == 6) {
            if (hardware_mode_.isK100Hardware()) {
                // Model 6 K100: 融合结果保持 384，可视化时还原到 432
                std::cout << "[Debug] Model 6 K100 mode: Resizing segmentation from 384 to 432 for visualization" << std::endl;
                cv::resize(result.segmentation, vis_segmentation, cv::Size(640, 432), 0, 0, cv::INTER_NEAREST);
                vis_cropped_img = result.cropped_img;
                vis_detections = scaleDetectionsY(result.detections, 432.0f / 384.0f, 432);
            } else {
                // Model 6 bestmow: 直接使用 384 尺度
                vis_cropped_img = result.cropped_img;
                vis_segmentation = result.segmentation;
            }
        } else if (config_.infer_mode == 7) {
            // Model 7: 根据硬件模式调整
            if (hardware_mode_.isK100Hardware()) {
                // K100 模式：将 384 的分割结果 resize 回 432 用于可视化
                std::cout << "[Debug] K100 mode: Resizing segmentation from 384 to 432 for visualization" << std::endl;
                cv::resize(result.segmentation, vis_segmentation, cv::Size(640, 432), 0, 0, cv::INTER_NEAREST);
                vis_cropped_img = result.cropped_img;  // cropped_img 已经是 432
                vis_detections = scaleDetectionsY(result.detections, 432.0f / 384.0f, 432);
            } else {
                // bestmow 模式：直接使用 384 尺寸
                vis_cropped_img = result.cropped_img;
                vis_segmentation = result.segmentation;
            }
        }

        // 1. 绘制分割结果（纯色分割图 + 叠加图）
        // Model 6: 根据配置决定是否绘制检测框
        bool enable_draw_box = (config_.infer_mode == 6) && config_.enable_draw_detection_box;
        pure_seg_mat = drawResultOptimized(vis_cropped_img, vis_segmentation,
                                          vis_detections, img_seg_show, enable_draw_box);

        std::cout << "[Debug] pure_seg_mat: " << pure_seg_mat.size()
                  << ", img_seg_show: " << img_seg_show.size() << std::endl;

        // 2. 横向拼接：原图 | 纯色分割 | 叠加图
        cv::Mat origin_seg;
        cv::hconcat(vis_cropped_img, pure_seg_mat, origin_seg);
        cv::hconcat(origin_seg, img_seg_show, origin_seg);

        // 3. 生成点云三视图可视化（标签视图 + RGB视图）
        cv::Mat xyz_rgbl;
        if (!result.pointcloud.empty()) {
            std::cout << "[Debug] Generating point cloud visualization, points: "
                      << result.pointcloud.size() << std::endl;
            stereo_point_cloud stereoPointCloud;
            stereoPointCloud.show_xyz_rgbl_plane_point_cloud_final(result.pointcloud, xyz_rgbl);

            std::cout << "[Debug] xyz_rgbl size before resize: " << xyz_rgbl.size() << std::endl;

            // 将点云视图 resize 到与 origin_seg 相同的宽度
            int target_width = origin_seg.cols;
            int target_height = xyz_rgbl.rows * target_width / xyz_rgbl.cols;
            cv::resize(xyz_rgbl, xyz_rgbl, cv::Size(target_width, target_height));

            std::cout << "[Debug] xyz_rgbl size after resize: " << xyz_rgbl.size() << std::endl;
        } else {
            std::cout << "[Debug] Point cloud is empty, creating black placeholder" << std::endl;
            // 如果没有点云，创建一个黑色占位图
            xyz_rgbl = cv::Mat::zeros(origin_seg.rows, origin_seg.cols, CV_8UC3);
        }

        // 4. 纵向拼接：上方（原图+分割） + 下方（点云三视图）
        cv::Mat final_compared;
        cv::vconcat(origin_seg, xyz_rgbl, final_compared);

        // 5. 保存合并图像
        std::string combined_path = config_.output_dir + "/combined/" + image_name + "_combined.jpg";
        cv::imwrite(combined_path, final_compared);
        std::cout << "[Save] Combined visualization saved: " << combined_path << std::endl;
    }

    // ========== 单独保存各项结果（可选） ==========
    // 保存分割结果
    if (config_.save_segmentation && !result.segmentation.empty()) {
        cv::Mat seg_color = labelToColor(result.segmentation);
        std::string seg_path = config_.output_dir + "/segmentation/" + image_name + "_seg.png";
        cv::imwrite(seg_path, seg_color);
        std::cout << "[Save] Segmentation saved: " << seg_path << std::endl;
    }

    // 保存点云
    if (config_.save_pointcloud && !result.pointcloud.empty()) {
        std::string pcd_path = config_.output_dir + "/pointcloud/" + image_name + ".pcd";
        pcl::io::savePCDFileBinary(pcd_path, result.pointcloud);
        std::cout << "[Save] Point cloud saved: " << pcd_path << std::endl;
    }

    // 保存检测结果（Model 6 或 K100 模式）
    if (config_.save_detection && !result.detections.empty() &&
        (config_.infer_mode == 6 || hardware_mode_.isK100Hardware())) {
        cv::Mat det_img = result.cropped_img.clone();
        std::vector<Detection> det_detections = result.detections;
        if (hardware_mode_.isK100Hardware() && result.cropped_img.rows == 432) {
            det_detections = scaleDetectionsY(result.detections, 432.0f / 384.0f, 432);
        }
        drawDetections(det_img, det_detections);
        std::string det_path = config_.output_dir + "/detection/" + image_name + "_det.png";
        cv::imwrite(det_path, det_img);
        std::cout << "[Save] Detection saved: " << det_path << std::endl;
    }

    // 保存深度图
    if (config_.save_depth && !result.depth.empty()) {
        cv::Mat depth_color = visualizeDepth(result.depth);
        std::string depth_path = config_.output_dir + "/depth/" + image_name + "_depth.png";
        cv::imwrite(depth_path, depth_color);
        std::cout << "[Save] Depth saved: " << depth_path << std::endl;
    }
}
