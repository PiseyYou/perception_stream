#include <iostream>
#include <string>
#include <vector>
#include <filesystem>

#include "offline_config.hpp"
#include "offline_processor.hpp"
#include "offline_utils.hpp"

namespace fs = std::filesystem;

void printUsage(const char* program_name) {
    std::cout << "\n========== Stereo Perception Offline Test Tool ==========" << std::endl;
    std::cout << "Version: v2.1.0" << std::endl;
    std::cout << "\nUsage:" << std::endl;
    std::cout << "  " << program_name << " <input_dir> <output_dir> [infer_mode] [hardware_mode]" << std::endl;
    std::cout << "\nArguments:" << std::endl;
    std::cout << "  input_dir      : Input directory containing images" << std::endl;
    std::cout << "  output_dir     : Output directory for results" << std::endl;
    std::cout << "  infer_mode     : Inference mode (optional, 6=day/sub, 7=night/DSG)" << std::endl;
    std::cout << "  hardware_mode  : Hardware mode (optional)" << std::endl;
    std::cout << "                   - k100 or K100: K100 mode (default)" << std::endl;
    std::cout << "                   - bestmow or BESTMOW: bestmow mode" << std::endl;
    std::cout << "\nExamples:" << std::endl;
    std::cout << "  " << program_name << " /path/to/images /path/to/output" << std::endl;
    std::cout << "  " << program_name << " /path/to/images /path/to/output 7 k100" << std::endl;
    std::cout << "  " << program_name << " /path/to/images /path/to/output 6 bestmow" << std::endl;
    std::cout << "\nSupported image formats: .jpg, .jpeg, .png, .bmp" << std::endl;
    std::cout << "Stereo format: 1280x480 (auto-split to left/right)" << std::endl;
    std::cout << "========================================================\n" << std::endl;
}

int main(int argc, char** argv) {
    std::cout << "===========================================================" << std::endl;
    std::cout << "  Stereo Perception Offline Test Tool v2.1.0" << std::endl;
    std::cout << "  Based on stereo_perception_multi2 with K100/bestmow support" << std::endl;
    std::cout << "===========================================================" << std::endl;

    if (argc >= 2) {
        std::string arg1 = argv[1];
        if (arg1 == "--help" || arg1 == "-h" || arg1 == "help") {
            printUsage(argv[0]);
            return 0;
        }
    }

    // ========== 从环境变量读取配置 ==========
    std::string input_dir;
    std::string output_dir;
    std::string pointcloud_dir;
    int infer_mode = 7;  // 默认使用 DSG 模式
    bool use_k100_mode = true;  // 默认使用 K100 模式

    // 读取输入目录（优先使用环境变量）
    const char* env_input = std::getenv("OFFLINE_INPUT_DIR");
    if (env_input != nullptr) {
        input_dir = env_input;
        std::cout << "[Config] Input dir from env: " << input_dir << std::endl;
    } else if (argc >= 2) {
        input_dir = argv[1];
        std::cout << "[Config] Input dir from argv: " << input_dir << std::endl;
    } else {
        // 默认路径（用于本地测试）
        input_dir = "/home/youfeng/debug/custom/0102/0423/stereo/";
        std::cout << "[Config] Using default input dir: " << input_dir << std::endl;
    }

    // 读取输出目录（可选）
    const char* env_output = std::getenv("OFFLINE_OUTPUT_DIR");
    if (env_output != nullptr) {
        output_dir = env_output;
        std::cout << "[Config] Output dir from env: " << output_dir << std::endl;
    } else if (argc >= 3) {
        output_dir = argv[2];
        std::cout << "[Config] Output dir from argv: " << output_dir << std::endl;
    }

    const char* env_pcd_output = std::getenv("OFFLINE_POINTCLOUD_DIR");
    if (env_pcd_output != nullptr) {
        pointcloud_dir = env_pcd_output;
        std::cout << "[Config] Pointcloud dir from env: " << pointcloud_dir << std::endl;
    }

    // 读取推理模式（命令行参数优先于环境变量）
    if (argc >= 4) {
        infer_mode = std::atoi(argv[3]);
        std::cout << "[Config] Infer mode from argv: " << infer_mode << std::endl;
    } else {
        const char* env_mode = std::getenv("OFFLINE_INFER_MODE");
        if (env_mode != nullptr) {
            infer_mode = std::atoi(env_mode);
            std::cout << "[Config] Infer mode from env: " << infer_mode << std::endl;
        }
    }

    // 读取硬件模式（命令行参数优先于环境变量）
    if (argc >= 5) {
        std::string hw_str = argv[4];
        std::transform(hw_str.begin(), hw_str.end(), hw_str.begin(), ::tolower);
        use_k100_mode = (hw_str == "k100");
        std::cout << "[Config] Hardware mode from argv: " << (use_k100_mode ? "K100" : "bestmow") << std::endl;
    } else {
        const char* env_hardware = std::getenv("HARDWARE_MODE");
        if (env_hardware != nullptr) {
            std::string hw_str = env_hardware;
            std::transform(hw_str.begin(), hw_str.end(), hw_str.begin(), ::tolower);
            use_k100_mode = (hw_str == "k100");
            std::cout << "[Config] Hardware mode from env: " << (use_k100_mode ? "K100" : "bestmow") << std::endl;
        }
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
    config.infer_mode = infer_mode;         // 从环境变量或命令行读取
    config.erode_pixel = 0;                 // 形态学腐蚀像素
    config.detection_threshold = 0.3f;      // 检测阈值
    config.area_threshold = 0.5f;           // 区域阈值

    // K100 专用配置
    config.enable_dsg_hsv_dark_filter = false;
    config.enable_dsg_detection_in_pointcloud = false;
    config.enable_bestmow_cdt = !use_k100_mode;

    // 路径配置
    // 优先使用环境变量中的模型目录，否则使用相对路径
    const char* env_model_dir = std::getenv("MODEL_DIR");
    if (env_model_dir != nullptr) {
        config.model_dir = std::string(env_model_dir) + "/";
        std::cout << "[Config] Model dir from env: " << config.model_dir << std::endl;
    } else {
        config.model_dir = "../models/";        // 模型目录（相对于可执行文件）
    }
    config.input_dir = input_dir;

    // 如果指定了输出目录，使用指定的；否则自动生成
    if (!output_dir.empty()) {
        config.output_dir = output_dir;
        std::cout << "[Config] Using specified output dir: " << output_dir << std::endl;
    }
    if (!pointcloud_dir.empty()) {
        config.pointcloud_dir = pointcloud_dir;
        std::cout << "[Config] Using specified pointcloud dir: " << pointcloud_dir << std::endl;
    }
    // 否则留空，让 auto_configure() 自动生成带模式信息的目录名

    // 输出控制
    config.save_segmentation = false;
    config.save_pointcloud = true;
    config.save_detection = false;
    config.save_depth = false;
    config.enable_debug_show = true;  // 启用合并可视化保存

    // 自动配置（根据硬件模式选择模型等）
    config.auto_configure();

    std::cout << "[Config] Effective infer mode: " << config.infer_mode << std::endl;
    std::cout << "[Config] Effective hardware mode: " << (config.use_k100_mode ? "K100" : "bestmow") << std::endl;

    // 打印配置
    config.print();

    // ========== 检查输入目录 ==========
    if (!fs::exists(input_dir) || !fs::is_directory(input_dir)) {
        std::cerr << "[Error] Input directory does not exist: " << input_dir << std::endl;
        return 1;
    }

    // ========== 创建输出目录 ==========
    createOutputDirectories(config.output_dir, config.pointcloud_dir);

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
