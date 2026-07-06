#include <iostream>
#include <string>
#include <vector>
#include <filesystem>
#include <algorithm>
#include <cctype>

#include "offline_config.hpp"
#include "offline_processor.hpp"
#include "offline_utils.hpp"

namespace fs = std::filesystem;

void printUsage(const char* program_name) {
    std::cout << "\n========== Stereo Perception Offline Test Tool ==========" << std::endl;
    std::cout << "Version: v2.1.0" << std::endl;
    std::cout << "\nUsage:" << std::endl;
    std::cout << "  " << program_name << " <input_dir> <output_dir> [hardware_mode] [sub_model_name]" << std::endl;
    std::cout << "\nArguments:" << std::endl;
    std::cout << "  input_dir      : Input directory containing images" << std::endl;
    std::cout << "  output_dir     : Output directory for results" << std::endl;
    std::cout << "  hardware_mode  : Hardware mode (optional)" << std::endl;
    std::cout << "                   - k100 or K100: K100 mode (default)" << std::endl;
    std::cout << "                   - bestmow or BESTMOW: bestmow mode" << std::endl;
    std::cout << "  sub_model_name : Optional Model 6 model file name under models/" << std::endl;
    std::cout << "\nExamples:" << std::endl;
    std::cout << "  " << program_name << " /path/to/images /path/to/output" << std::endl;
    std::cout << "  " << program_name << " /path/to/images /path/to/output k100" << std::endl;
    std::cout << "  " << program_name << " /path/to/images /path/to/output k100 sub_20260611_640x384.bin" << std::endl;
    std::cout << "  " << program_name << " /path/to/images /path/to/output bestmow" << std::endl;
    std::cout << "\nSupported image formats: .jpg, .jpeg, .png, .bmp" << std::endl;
    std::cout << "Stereo format: 1280x480 (auto-split to left/right)" << std::endl;
    std::cout << "========================================================\n" << std::endl;
}

int main(int argc, char** argv) {
    std::cout << "===========================================================" << std::endl;
    std::cout << "  Stereo Perception Offline Test Tool v2.1.0" << std::endl;
    std::cout << "  Based on stereo_perception_multi2 with K100/bestmow support" << std::endl;
    std::cout << "===========================================================" << std::endl;

//    std::string input_dir = "/home/youfeng/debug/custom/0102/0423/stereo/";
//    std::string input_dir = "/home/youfeng/debug/boluo/0286/20260511/";
//    std::string input_dir = "/home/youfeng/debug/boluo/0027/20260520/rosbag_LK-MR541EU000027_navigation_202605201059/stereo_output_rosbag_LK-MR541EU000027_navigation_202605201059_0/error_test/cdt_sub_6_205_det_0.3_pc_432_bak/select_origin/";
//    std::string input_dir = "/home/youfeng/debug/boluo/0027/20260520/rosbag_LK-MR541EU000027_navigation_202605201059/stereo_output_rosbag_LK-MR541EU000027_navigation_202605201059_0/error_test/cdt_sub_6_205_det_0.3_pc_432_bak/select_origin/single_test/";
//    std::string input_dir = "/home/youfeng/debug/boluo/0027/20260520/rosbag_LK-MR541EU000027_navigation_202605201059/stereo_output_rosbag_LK-MR541EU000027_navigation_202605201059_0/error_test/cdt_sub_6_205_det_0.3_pc_432_bak/select_origin/";
//    std::string input_dir = "/home/youfeng/debug/boluo/0027/20260528/rosbag/rosbag_LK-MR6P1US000124_navigation_202605281113/stereo_output_rosbag_LK-MR6P1US000124_navigation_202605281113_0/images/extracted_interval/";
//    std::string input_dir = "/home/youfeng/debug/select/rain_data/rosbag/0725/rosbag_MR1P1251US0007622_camera_202507241507/stereo_output_rosbag_MR1P1251US0007622_camera_202507241507_0/images/extracted_interval/";
//    std::string input_dir = "/home/youfeng/debug/boluo/0337/20260623/select/";
//    std::string input_dir = "/home/youfeng/debug/boluo/0337/20260623/select/output_Sub_bestmow/stereo/select_part/point_cloud_error/";
//    std::string input_dir = "/home/youfeng/debug/boluo/0337/20260623/select/output_Sub_bestmow/stereo/select_part/point_cloud_error/";
//    std::string input_dir = "/home/youfeng/debug/custom/0337/20260629/";
//    std::string input_dir = "/home/youfeng/debug/boluo/0027/20260629/rosbag_LK-MR541EU000027_navigation_202606291439/stereo_output_rosbag_LK-MR541EU000027_navigation_202606291439_0/images/";
//    std::string input_dir = "/home/youfeng/debug/boluo/0027/20260629/rosbag_LK-MR541EU000027_navigation_202606291436/stitched_every_8/";
//    std::string input_dir = "/home/youfeng/debug/boluo/0368/20260701/";
    std::string input_dir = "/home/youfeng/debug/boluo/0339/20260704/";
    std::string output_dir;
    if (argc == 2 && (std::string(argv[1]) == "-h" || std::string(argv[1]) == "--help")) {
        printUsage(argv[0]);
        return 0;
    }

    if (argc >= 2) {
        input_dir = argv[1];
    }
    if (argc >= 3) {
        output_dir = argv[2];
    }

    // 解析硬件模式（默认 K100）
    bool use_k100_mode = true;  // 使用 K100 模式和 dsg_multi_20260403_640x384.bin 模型
    if (argc >= 4) {
        std::string mode_str = argv[3];
        std::transform(mode_str.begin(), mode_str.end(), mode_str.begin(),
                       [](unsigned char c) { return std::tolower(c); });
        if (mode_str == "bestmow") {
            use_k100_mode = true;
        } else if (mode_str != "k100") {
            std::cerr << "[Error] Unsupported hardware mode: " << argv[3] << std::endl;
            printUsage(argv[0]);
            return 1;
        }
    }

    std::string model_override;
    if (argc >= 5) {
        model_override = argv[4];
    }

    // 设置环境变量，让 HardwareDetector 读取到正确的模式
    if (use_k100_mode) {
        setenv("HARDWARE_MODE", "K100", 1);
        std::cout << "[Config] Set HARDWARE_MODE=K100" << std::endl;
    } else {
        setenv("HARDWARE_MODE", "bestmow", 1);
        std::cout << "[Config] Set HARDWARE_MODE=bestmow" << std::endl;
    }

    // ========== 配置 ==========
    OfflineConfig config;

    // 手动配置硬件模式（核心修改点）
    config.use_k100_mode = use_k100_mode;

    // 基础配置
    config.infer_mode = 6;              // 6: Sub模式 (sub_20260320), 7: DSG模式 (dsg_multi_20260407)
    config.erode_pixel = 0;             // 形态学腐蚀像素
    config.detection_threshold = 0.3f;  // 检测阈值
    config.area_threshold = 0.5f;       // 区域阈值
    config.depth_inpainting_strategy = 2;  // 只使用语义障碍物深度补全，不依赖检测框

    // K100 专用配置
    config.enable_dsg_hsv_dark_filter = false;
    config.enable_dsg_detection_in_pointcloud = false;

    // 路径配置
    config.input_dir = input_dir;
    config.output_dir = output_dir;

    // 输出控制
    config.save_segmentation = true;
    config.save_pointcloud = true;
    config.save_detection = true;
    config.save_depth = true;
    config.enable_debug_show = true;  // 启用合并可视化保存

    // 自动配置（根据硬件模式选择模型等）
    config.auto_configure();
    if (!model_override.empty()) {
        config.mul_sub_model_name = model_override;
        std::cout << "[Config] Override Model 6 model: " << config.mul_sub_model_name << std::endl;
    }

    // 打印配置
    config.print();

    // ========== 检查输入目录 ==========
    if (!fs::exists(input_dir) || !fs::is_directory(input_dir)) {
        std::cerr << "[Error] Input directory does not exist: " << input_dir << std::endl;
        return 1;
    }

    // ========== 创建输出目录 ==========
    createOutputDirectories(config.output_dir);

    // ========== 扫描图像文件 ==========
    std::cout << "\n[Scan] Scanning input directory..." << std::endl;
    std::vector<std::string> image_files = scanImageFiles(input_dir);

    if (image_files.empty()) {
        std::cout << "[Warning] No image files found in: " << input_dir << std::endl;
        std::cout << "Supported formats: .jpg, .jpeg, .png, .bmp" << std::endl;
        return 0;
    }

    std::cout << "[Scan] Found " << image_files.size() << " image file(s)" << std::endl;

    // ========== 初始化处理器 ==========
    OfflineProcessor processor(config);
    if (!processor.init()) {
        std::cerr << "[Error] Failed to initialize processor" << std::endl;
        return 1;
    }

    // ========== 处理图像 ==========
    int success_count = 0;
    int fail_count = 0;

    for (size_t i = 0; i < image_files.size(); ++i) {
        const std::string& image_path = image_files[i];
        std::string image_name = fs::path(image_path).stem().string();

        std::cout << "\n========================================" << std::endl;
        std::cout << "[" << (i + 1) << "/" << image_files.size() << "] " << image_name << std::endl;
        std::cout << "========================================" << std::endl;

        // 读取图像
        cv::Mat full_img = cv::imread(image_path);
        if (full_img.empty()) {
            std::cerr << "[Error] Cannot read image: " << image_path << std::endl;
            fail_count++;
            continue;
        }

        std::cout << "[Load] Image size: " << full_img.size() << std::endl;

        // 分割左右图
        cv::Mat left_img, right_img;
        bool is_stereo = splitStereoImage(full_img, left_img, right_img);

        if (is_stereo) {
            std::cout << "[Load] Stereo image detected, split to: "
                      << left_img.size() << " (left) + " << right_img.size() << " (right)" << std::endl;
        } else {
            std::cout << "[Load] Mono image, using as left image" << std::endl;
        }

        // 处理
        auto result = processor.process(left_img, right_img, image_name);

        if (result.success) {
            // 保存结果
            processor.saveResults(result, image_name, left_img);
            success_count++;
            std::cout << "[Done] Processing completed successfully" << std::endl;
        } else {
            std::cerr << "[Error] Processing failed" << std::endl;
            fail_count++;
        }
    }

    // ========== 总结 ==========
    std::cout << "\n===========================================================" << std::endl;
    std::cout << "Processing Summary:" << std::endl;
    std::cout << "  Total images: " << image_files.size() << std::endl;
    std::cout << "  Success: " << success_count << std::endl;
    std::cout << "  Failed: " << fail_count << std::endl;
    std::cout << "  Output directory: " << config.output_dir << std::endl;
    std::cout << "===========================================================" << std::endl;

    return (fail_count == 0) ? 0 : 1;
}
