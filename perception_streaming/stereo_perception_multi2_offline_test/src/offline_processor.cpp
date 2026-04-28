#include "offline_processor.hpp"
#include "offline_utils.hpp"
#include "stereo_point_cloud_rgbl.h"
#include "hardware_detector.hpp"
#include <pcl/io/pcd_io.h>
#include <iostream>

// Helper function to filter labels and detections
static void filterLabelDect(cv::Mat &src_lab, std::vector<Detection> &dect_src,
                     cv::Mat &lab_dst, std::vector<Detection> &dect_dst,
                     bool enable_det, bool force_bottom_region = true)
{
    // 先克隆，避免污染原图
    src_lab.copyTo(lab_dst);

    cv::Mat mask_zero;
    cv::compare(lab_dst, 0, mask_zero, cv::CMP_EQ);

    // 将所有 label == 0 的像素设置为 label == 2
    lab_dst.setTo(2, mask_zero);

    // 只有在 force_bottom_region 为 true 时才强制设置底部区域
    if (force_bottom_region) {
        int shift_high = 370;
        // 强制将指定区域 (x=0, y=370, x=640, y=384) 的 label 设置为 2
        cv::Rect force_region(0, shift_high, 640,
                              384 - shift_high); // 宽度为 640，高度为 14 (384 - 370)
        lab_dst(force_region)
            .setTo(cv::Scalar(2)); // 将该区域的所有像素设置为 label == 2
    }

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
            process_roi(103);
        }
        else if (target_id == 6)
        {
            process_roi(106);
        }
        else if (target_id == 7)
        {
            // process_roi(107);
            std::cout << "[person] have been dect....." << std::endl;
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
                // 保留检测框标签，覆盖整个区域
                roi_dst.setTo(104);
                dect_dst.push_back(dect_src[i]);
            }
            // 情况3: 其他情况（主要是背景区域）
            else
            {
                // 只覆盖背景(1)和静态障碍物(5)
                cv::Mat mask_one, mask_five;
                cv::inRange(roi_dst, cv::Scalar(1), cv::Scalar(1), mask_one);
                cv::inRange(roi_dst, cv::Scalar(5), cv::Scalar(5), mask_five);
                cv::Mat combined_mask = mask_one | mask_five;
                roi_dst.setTo(104, combined_mask);
                dect_dst.push_back(dect_src[i]);
            }
        }
        if (enable_det)
        {
            roi_dst.setTo(target_id + 100);
            dect_dst.push_back(dect_src[i]);
        }
    }
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

    // 禁用 OpenCL 以避免在 Docker 容器中的段错误
    cv::ocl::setUseOpenCL(false);
    std::cout << "[Init] OpenCL disabled for stereo matcher" << std::endl;

    // 初始化立体匹配器参数
    stereo_matcher_.stereo_multi_param_init();
    std::cout << "[Init] Stereo matcher initialized" << std::endl;

    return true;
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

    // Model 6 固定使用 640x432 裁剪，然后 resize 到 640x384
    std::cout << "[Process] Crop to 640x432, then resize to 640x384" << std::endl;
    cv::Rect crop_region(0, 0, 640, 432);
    cropped_img = left_img(crop_region).clone();
    cv::resize(cropped_img, resized_img, cv::Size(640, 384), 0, 0, cv::INTER_LINEAR);

    // ========== 1. Multi-Sub 推理 ==========
    std::cout << "[Process] Running Multi-Sub inference..." << std::endl;

    std::vector<Detection> detections, dst_detections;
    cv::Mat img_label384 = cv::Mat::zeros(384, 640, CV_8UC1) + 2;
    cv::Mat lab_out;

    mul_sub_perception_.perception_process_bgr_no_argmax_erode(
        resized_img, detections, img_label384, lab_out, config_.erode_pixel);

    // 过滤标签和检测框
    // K100 模式：不强制设置底部区域，真实展示分割结果
    // bestmow 模式：强制设置底部区域为 label==2
    cv::Mat dst_label384(384, 640, CV_8UC1);
    bool force_bottom = !hardware_mode_.isK100Hardware();
    filterLabelDect(lab_out, detections, dst_label384, dst_detections,
                    config_.enable_draw_detection_box, force_bottom);

    // 将分割结果从 640x384 resize 回 640x432
    cv::resize(dst_label384, lab_dst, cv::Size(640, 432), 0, 0, cv::INTER_NEAREST);

    // 将检测框 y 坐标按 432/384 比例缩放
    const float y_scale = 432.0f / 384.0f;
    for (auto& det : dst_detections) {
        det.bbox.ymin = static_cast<int>(det.bbox.ymin * y_scale);
        det.bbox.ymax = static_cast<int>(det.bbox.ymax * y_scale);
    }

    result.detections = dst_detections;
    result.segmentation = lab_dst;

    if (lab_dst.empty()) {
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

        // 立体匹配
        cv::Mat disparity = stereo_matcher_.stereo_multi_process_depth(left_gray, right_gray);
        result.depth = stereo_matcher_.stereo_multi_process_filter(
            disparity, lab_dst, config_.enable_height_filter);

        std::cout << "[Process] Depth map computed: " << result.depth.size() << std::endl;
    } else {
        std::cout << "[Process] No right image, skipping stereo matching" << std::endl;
    }

    // ========== 3. 点云融合 ==========
    if (!result.depth.empty()) {
        std::cout << "[Process] Generating point cloud..." << std::endl;

        pcl::PointCloud<pcl::PointXYZRGBL> xyz_rgbl_cloud;
        pcl::PointCloud<pcl::PointXYZRGBL> out_xyz_rgbl_cloud;

        stereo_matcher_.stereo_process_pci_depth_rgb_seg_det_fusion(
            result.depth, result.segmentation, result.detections,
            cropped_img,  // 使用 640x432 的原始裁剪图像
            xyz_rgbl_cloud, out_xyz_rgbl_cloud);

        result.pointcloud = out_xyz_rgbl_cloud;
        result.cropped_img = cropped_img;
        std::cout << "[Process] Point cloud generated: " << out_xyz_rgbl_cloud.size() << " points" << std::endl;
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
    cv::Mat lab_dst;

    // 根据硬件模式选择裁剪尺寸
    if (hardware_mode_.isK100Hardware()) {
        // K100 模式：裁剪到 640x432，然后 resize 到 640x384
        std::cout << "[Process] K100 mode: Crop to 640x432, then resize to 640x384" << std::endl;
        cv::Rect crop_region(0, 0, 640, 432);
        cropped_img = left_img(crop_region).clone();
        cv::resize(cropped_img, resized_img, cv::Size(640, 384));
    } else {
        // bestmow 模式：直接裁剪到 640x384
        std::cout << "[Process] bestmow mode: Crop to 640x384" << std::endl;
        cv::Rect crop_region(0, 0, 640, 384);
        cropped_img = left_img(crop_region).clone();
        resized_img = cropped_img.clone();
    }

    // ========== 1. DSG 推理 ==========
    std::cout << "[Process] Running DSG inference..." << std::endl;

    // 使用简化的推理接口
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

    // DSG 模式不返回检测框，只有分割结果
    result.detections.clear();

    // 更新分割结果（lab_dst 已经是 640x384）
    result.segmentation = lab_dst;

    // ========== HSV 暗区域滤波（可选） ==========
    if (config_.enable_dsg_hsv_dark_filter) {
        std::cout << "[Process] Applying HSV dark filter..." << std::endl;

        cv::Mat hsvImg;
        cv::cvtColor(cropped_img, hsvImg, cv::COLOR_BGR2HSV);

        // 检测偏黑区域：低饱和度、低亮度
        cv::Scalar lowerBlack(0, 0, 0);      // H, S, V
        cv::Scalar upperBlack(180, 50, 80);  // 低饱和度、低亮度

        cv::Mat darkMask;
        cv::inRange(hsvImg, lowerBlack, upperBlack, darkMask);

        // 形态学处理去噪
        cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(5, 5));
        cv::morphologyEx(darkMask, darkMask, cv::MORPH_CLOSE, kernel);
        cv::morphologyEx(darkMask, darkMask, cv::MORPH_OPEN, kernel);

        // Resize 到标签图尺寸并应用
        cv::Mat resizedMask;
        cv::resize(darkMask, resizedMask, lab_dst.size(), 0, 0, cv::INTER_NEAREST);
        lab_dst.setTo(3, resizedMask);  // 标记为 road (类别3)

        // 更新分割结果
        result.segmentation = lab_dst;

        std::cout << "[Process] HSV dark filter applied" << std::endl;
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

        // 根据硬件模式裁剪深度图
        if (hardware_mode_.isK100Hardware()) {
            // K100 模式：裁剪到 640x432，然后 resize 到 640x384 用于融合
            cv::Mat depth_432 = depth_480(cv::Rect(0, 0, 640, 432)).clone();
            cv::resize(depth_432, result.depth, cv::Size(640, 384), 0, 0, cv::INTER_LINEAR);
            std::cout << "[Process] K100 mode: Depth cropped to 432, resized to 384" << std::endl;
        } else {
            // bestmow 模式：直接裁剪到 640x384
            result.depth = depth_480(cv::Rect(0, 0, 640, 384)).clone();
            std::cout << "[Process] bestmow mode: Depth cropped to 384" << std::endl;
        }
    } else {
        std::cout << "[Process] No right image, skipping stereo matching" << std::endl;
    }

    // ========== 3. 点云融合 ==========
    if (!result.depth.empty()) {
        std::cout << "[Process] Generating point cloud..." << std::endl;
        std::cout << "[Debug] depth size: " << result.depth.size()
                  << ", segmentation size: " << result.segmentation.size()
                  << ", resized_img size: " << resized_img.size() << std::endl;

        pcl::PointCloud<pcl::PointXYZRGBL> xyz_rgbl_cloud;
        pcl::PointCloud<pcl::PointXYZRGBL> out_xyz_rgbl_cloud;

        // 使用 640x384 的 resized_img 进行融合（无论哪种模式，融合都在 384 尺度）
        stereo_matcher_.stereo_process_pci_depth_rgb_seg_det_fusion(
            result.depth, result.segmentation, result.detections,
            resized_img,  // 使用 640x384 的 resized 图像
            xyz_rgbl_cloud, out_xyz_rgbl_cloud);

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

        // 根据推理模式和硬件模式调整可视化图像尺寸
        if (config_.infer_mode == 6) {
            // Model 6: 分割结果是 640x432，直接使用
            vis_cropped_img = result.cropped_img;
            vis_segmentation = result.segmentation;
        } else if (config_.infer_mode == 7) {
            // Model 7: 根据硬件模式调整
            if (hardware_mode_.isK100Hardware()) {
                // K100 模式：将 384 的分割结果 resize 回 432 用于可视化
                std::cout << "[Debug] K100 mode: Resizing segmentation from 384 to 432 for visualization" << std::endl;
                cv::resize(result.segmentation, vis_segmentation, cv::Size(640, 432), 0, 0, cv::INTER_NEAREST);
                vis_cropped_img = result.cropped_img;  // cropped_img 已经是 432
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
                                          result.detections, img_seg_show, enable_draw_box);

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
        const std::string& pointcloud_base = config_.pointcloud_dir.empty()
            ? config_.output_dir + "/pointcloud"
            : config_.pointcloud_dir;
        std::string pcd_path = pointcloud_base + "/" + image_name + ".pcd";
        pcl::io::savePCDFileBinary(pcd_path, result.pointcloud);
        std::cout << "[Save] Point cloud saved: " << pcd_path << std::endl;
    }

    // 保存检测结果（Model 6 或 K100 模式）
    if (config_.save_detection && !result.detections.empty() &&
        (config_.infer_mode == 6 || hardware_mode_.isK100Hardware())) {
        cv::Mat det_img = result.cropped_img.clone();
        drawDetections(det_img, result.detections);
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
