#ifndef OFFLINE_CONFIG_HPP
#define OFFLINE_CONFIG_HPP

#include <string>

/**
 * @brief 离线测试配置结构
 */
struct OfflineConfig {
    // ========== 硬件模式配置（手动调整） ==========
    bool use_k100_mode = true;  // true: K100 模式, false: bestmow 模式

    // ========== 基础配置 ==========
    int infer_mode = 7;              // 推理模式：6=Sub(multi_sub), 7=DSG
    int erode_pixel = 0;             // 形态学腐蚀像素
    float detection_threshold = 0.3f; // 检测阈值
    float area_threshold = 0.5f;      // 区域阈值

    // ========== Model 6 (Sub) 专用配置 ==========
    bool enable_red_brick_refine = false;              // 红色砖头颜色后处理
    int red_brick_min_area = 100;                      // 红色砖头最小面积
    int depth_inpainting_strategy = 0;                 // 深度补全策略：0=关闭, 1=检测框, 2=语义, 3=两者
    bool enable_height_filter = false;                 // 启用高度过滤
    bool enable_draw_detection_box = false;             // 是否在可视化结果中绘制检测框

    // ========== Model 7 (DSG) 专用配置 ==========
    bool enable_dsg_hsv_dark_filter = false;           // HSV 暗色过滤
    bool enable_dsg_hsv_obstacle_protection = false;   // HSV 暗色过滤时保护障碍物
    bool enable_dsg_detection_in_pointcloud = false;   // 点云中显示检测框
    bool enable_dsg_outlier_removal = false;           // 点云融合时启用离群点移除

    // ========== bestMow CDT 前方矩形框配置 ==========
    bool enable_bestmow_cdt = false;                   // bestMow 模式下启用 CDT 前方矩形框修正

    // ========== 路径配置 ==========
    std::string model_dir = "/app/models/";  // Docker 容器中的模型路径
    std::string input_dir = "";
    std::string output_dir = "";  // 留空，由 auto_configure() 自动生成
    std::string pointcloud_dir = "";

    // 模型文件名（根据推理模式和硬件模式自动选择）
    std::string mul_sub_model_name = "";  // Model 6
    std::string dsg_model_name = "";      // Model 7
    std::string cdt_model_name = "";      // bestMow CDT

    // ========== 输出控制 ==========
    bool save_segmentation = true;   // 保存分割结果
    bool save_pointcloud = true;     // 保存点云
    bool save_detection = true;      // 保存检测结果（K100 模式）
    bool save_depth = true;          // 保存深度图
    bool enable_debug_show = true;   // 保存合并可视化图（原图+分割+点云）

    // ========== 自动设置 ==========
    void auto_configure() {
        // 根据推理模式和硬件模式自动选择模型文件
        if (infer_mode == 6) {
            // Model 6: Sub (multi_sub)
            mul_sub_model_name = "sub_20260303_640x384.bin";
        } else if (infer_mode == 7) {
            // Model 7: DSG
            if (use_k100_mode) {
                dsg_model_name = "dsg_multi_20260407_640x384.bin";
            } else {
                // bestmow 模式也使用 dsg_multi 模型
                dsg_model_name = "dsg_multi_20260407_640x384.bin";
            }
        }
        if (!use_k100_mode && enable_bestmow_cdt) {
            cdt_model_name = "cdt_20251125_640x384.bin";
        }

        // 构造输出目录
        std::string mode_name;
        if (infer_mode == 6) {
            mode_name = "Sub";
        } else if (infer_mode == 7) {
            mode_name = "DSG";
        } else {
            mode_name = "Mode" + std::to_string(infer_mode);
        }

        std::string hw_suffix = use_k100_mode ? "K100" : "bestmow";
        std::string erode_suffix = erode_pixel > 0 ? "_erode" + std::to_string(erode_pixel) : "";

        if (output_dir.empty()) {
            if (infer_mode == 6) {
                output_dir = input_dir + (use_k100_mode ? "/sub_6_205_432" : "/sub_6_205_384");
            } else if (infer_mode == 7) {
                output_dir = input_dir + (use_k100_mode ? "/dsg_7_205_432" : "/dsg_7_205_384");
            } else {
                output_dir = input_dir + "/output_" + mode_name + "_" + hw_suffix + erode_suffix + "/";
            }
        }

        if (pointcloud_dir.empty()) {
            if (infer_mode == 6) {
                pointcloud_dir = input_dir + (use_k100_mode ? "/pcd_6_205_432" : "/pcd_6_205_384");
            } else if (infer_mode == 7) {
                pointcloud_dir = input_dir + (use_k100_mode ? "/pcd_7_205_432" : "/pcd_7_205_384");
            } else {
                pointcloud_dir = output_dir + "/pointcloud";
            }
        }
    }

    // ========== 打印配置 ==========
    void print() const {
        std::cout << "\n========== Offline Test Configuration ==========" << std::endl;
        std::cout << "Hardware Mode: " << (use_k100_mode ? "K100" : "bestmow") << std::endl;
        std::cout << "  - DSG decoding: " << (use_k100_mode ? "Full YOLO" : "Simplified") << std::endl;
        std::cout << "  - Stereo params: " << (use_k100_mode ? "Adaptive" : "Fixed") << std::endl;
        std::cout << "  - Point cloud: " << (use_k100_mode ? "Label-aware" : "Generic") << std::endl;
        std::cout << "  - Depth post-proc: " << (use_k100_mode ? "Morphology" : "None") << std::endl;
        std::cout << "\nInference mode: " << infer_mode;
        if (infer_mode == 6) {
            std::cout << " (Sub/multi_sub)" << std::endl;
            std::cout << "Model: " << mul_sub_model_name << std::endl;
        } else if (infer_mode == 7) {
            std::cout << " (DSG)" << std::endl;
            std::cout << "Model: " << dsg_model_name << std::endl;
        } else {
            std::cout << " (Unknown)" << std::endl;
        }
        std::cout << "Erode pixel: " << erode_pixel << std::endl;
        std::cout << "Detection threshold: " << detection_threshold << std::endl;
        std::cout << "Area threshold: " << area_threshold << std::endl;
        std::cout << "bestMow CDT: "
                  << ((!use_k100_mode && enable_bestmow_cdt) ? "enabled" : "disabled")
                  << std::endl;
        if (!cdt_model_name.empty()) {
            std::cout << "CDT Model: " << cdt_model_name << std::endl;
        }
        std::cout << "\nInput dir: " << input_dir << std::endl;
        std::cout << "Output dir: " << output_dir << std::endl;
        std::cout << "Pointcloud dir: " << pointcloud_dir << std::endl;
        std::cout << "\nOutput options:" << std::endl;
        std::cout << "  - Segmentation: " << (save_segmentation ? "yes" : "no") << std::endl;
        std::cout << "  - Point cloud: " << (save_pointcloud ? "yes" : "no") << std::endl;
        std::cout << "  - Detection: " << (save_detection ? "yes" : "no") << std::endl;
        std::cout << "  - Depth: " << (save_depth ? "yes" : "no") << std::endl;
        std::cout << "===============================================\n" << std::endl;
    }
};

#endif // OFFLINE_CONFIG_HPP
