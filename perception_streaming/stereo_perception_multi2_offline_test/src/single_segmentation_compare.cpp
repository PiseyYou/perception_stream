#include <algorithm>
#include <cstdlib>
#include <cctype>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>

#include <opencv2/opencv.hpp>

#include "dsg_perception.h"
#include "multi_sub_perception.h"
#include "offline_config.hpp"
#include "offline_utils.hpp"

namespace fs = std::filesystem;

namespace {
constexpr const char* kInputDir = "/home/youfeng/debug/custom/0337/20260629/";
constexpr int kInferMode = 6;
constexpr bool kUseK100Mode = true;
constexpr int kErodePixel = 0;
constexpr int kModelWidth = 640;
constexpr int kModelHeight = 384;

cv::Mat prepareModelInput(const cv::Mat& original_img) {
    cv::Mat resized;
    cv::resize(original_img, resized, cv::Size(kModelWidth, kModelHeight), 0, 0, cv::INTER_LINEAR);
    return resized;
}

cv::Mat resizeLabelToOriginalSize(const cv::Mat& label, const cv::Size& original_size) {
    if (label.size() == original_size) {
        return label.clone();
    }

    cv::Mat restored;
    cv::resize(label, restored, original_size, 0, 0, cv::INTER_NEAREST);
    return restored;
}

cv::Mat normalizeSubLabel(const cv::Mat& label) {
    cv::Mat normalized = label.clone();
    cv::Mat zero_mask;
    cv::compare(normalized, 0, zero_mask, cv::CMP_EQ);
    normalized.setTo(2, zero_mask);
    return normalized;
}

std::string buildOutputPath(const std::string& image_path) {
    const fs::path input_path(image_path);
    return (input_path.parent_path() / (input_path.stem().string() + "_seg_compare.jpg")).string();
}

bool isGeneratedCompareImage(const std::string& image_path) {
    const std::string stem = fs::path(image_path).stem().string();
    constexpr const char* suffix = "_seg_compare";
    if (stem.size() < std::char_traits<char>::length(suffix)) {
        return false;
    }
    return stem.compare(stem.size() - std::char_traits<char>::length(suffix),
                        std::char_traits<char>::length(suffix),
                        suffix) == 0;
}

cv::Mat runSubSegmentation(multi_perception& perception,
                           cv::Mat& model_input,
                           int erode_pixel) {
    std::vector<Detection> detections;
    cv::Mat img_label384 = cv::Mat::zeros(kModelHeight, kModelWidth, CV_8UC1) + 2;
    cv::Mat lab_out;
    perception.perception_process_bgr_no_argmax_erode(
        model_input, detections, img_label384, lab_out, erode_pixel);

    if (lab_out.empty()) {
        return lab_out;
    }
    return normalizeSubLabel(lab_out);
}

cv::Mat runDsgSegmentation(dsg_perception& perception,
                           cv::Mat& model_input,
                           int erode_pixel) {
    (void)erode_pixel;
    cv::Mat lab_dst;
    perception.process_infer_match(model_input, lab_dst);
    return lab_dst;
}

bool saveSegmentationCompare(const cv::Mat& original_img,
                             const cv::Mat& restored_label,
                             const std::string& output_path) {
    cv::Mat overlay;
    cv::Mat pure_seg = drawResultOptimized(original_img, restored_label, {}, overlay, false);

    cv::Mat compared;
    cv::hconcat(std::vector<cv::Mat>{original_img, pure_seg, overlay}, compared);
    return cv::imwrite(output_path, compared);
}

struct PerceptionReleaseGuard {
    multi_perception* sub = nullptr;
    dsg_perception* dsg = nullptr;

    ~PerceptionReleaseGuard() {
        if (sub != nullptr) {
            sub->perception_release();
        }
        if (dsg != nullptr) {
            dsg->perception_release();
        }
    }
};
}  // namespace

int main() {
    const std::string input_dir = kInputDir;

    if (!fs::exists(input_dir) || !fs::is_directory(input_dir)) {
        std::cerr << "[Error] Input directory does not exist: " << input_dir << std::endl;
        return 1;
    }

    if (setenv("HARDWARE_MODE", kUseK100Mode ? "K100" : "bestmow", 1) != 0) {
        std::cerr << "[Error] Failed to set HARDWARE_MODE" << std::endl;
        return 1;
    }

    OfflineConfig config;
    config.input_dir = input_dir;
    config.use_k100_mode = kUseK100Mode;
    config.infer_mode = kInferMode;
    config.erode_pixel = kErodePixel;
    config.auto_configure();

    std::vector<std::string> image_files = scanImageFiles(input_dir);
    if (image_files.empty()) {
        std::cout << "[Warning] No image files found in: " << input_dir << std::endl;
        return 0;
    }

    multi_perception sub_perception;
    dsg_perception dsg_perception_model;
    PerceptionReleaseGuard release_guard;

    if (config.infer_mode == 6) {
        const std::string model_path = config.model_dir + config.mul_sub_model_name;
        if (!fs::exists(model_path)) {
            std::cerr << "[Error] Model file does not exist: " << model_path << std::endl;
            return 1;
        }
        sub_perception.perception_init(model_path.c_str());
        release_guard.sub = &sub_perception;
        std::cout << "[Init] Loaded Sub model: " << model_path << std::endl;
    } else if (config.infer_mode == 7) {
        const std::string model_path = config.model_dir + config.dsg_model_name;
        if (!fs::exists(model_path)) {
            std::cerr << "[Error] Model file does not exist: " << model_path << std::endl;
            return 1;
        }
        dsg_perception_model.perception_init(model_path.c_str());
        release_guard.dsg = &dsg_perception_model;
        std::cout << "[Init] Loaded DSG model: " << model_path << std::endl;
    } else {
        std::cerr << "[Error] Unsupported inference mode: " << config.infer_mode << std::endl;
        return 1;
    }

    int success_count = 0;
    int fail_count = 0;

    for (const std::string& image_path : image_files) {
        if (isGeneratedCompareImage(image_path)) {
            continue;
        }

        cv::Mat original_img = cv::imread(image_path, cv::IMREAD_COLOR);
        if (original_img.empty()) {
            std::cerr << "[Error] Cannot read image: " << image_path << std::endl;
            ++fail_count;
            continue;
        }

        std::cout << "[Process] " << image_path << " size=" << original_img.cols
                  << "x" << original_img.rows << std::endl;

        cv::Mat model_input = prepareModelInput(original_img);
        cv::Mat label;
        if (config.infer_mode == 6) {
            label = runSubSegmentation(sub_perception, model_input, config.erode_pixel);
        } else {
            label = runDsgSegmentation(dsg_perception_model, model_input, config.erode_pixel);
        }

        if (label.empty()) {
            std::cerr << "[Error] Empty segmentation output: " << image_path << std::endl;
            ++fail_count;
            continue;
        }

        cv::Mat restored_label = resizeLabelToOriginalSize(label, original_img.size());
        const std::string output_path = buildOutputPath(image_path);
        if (!saveSegmentationCompare(original_img, restored_label, output_path)) {
            std::cerr << "[Error] Failed to write: " << output_path << std::endl;
            ++fail_count;
            continue;
        }

        std::cout << "[Save] " << output_path << std::endl;
        ++success_count;
    }

    std::cout << "[Summary] success=" << success_count << ", failed=" << fail_count << std::endl;
    return fail_count == 0 ? 0 : 1;
}
