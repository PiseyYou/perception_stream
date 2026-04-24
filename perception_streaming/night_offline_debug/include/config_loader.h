#ifndef CONFIG_LOADER_H
#define CONFIG_LOADER_H

#include <string>
#include <vector>
#include <json/json.h>
#include <fstream>
#include <iostream>

struct ProcessingConfig {
    std::string dsg_model_path;
    std::string cdt_model_path;
    std::string image_directory;
    std::vector<std::string> image_extensions;
    std::string output_base_directory;
    std::string visualization_subdir;
    std::string pointcloud_subdir;

    int erode_pixel;
    double detection_threshold;
    bool enable_height_filter;
    bool enable_ces_show;
    bool enable_hsv_dark_filter;
    int hsv_dark_threshold;
    bool enable_debug_show;
    bool enable_draw_detection_box;

    int input_width;
    int input_height;
    int crop_height;
    int model_width;
    int model_height;

    float alpha_blend;
    float font_scale;
    int box_thickness;
};

class ConfigLoader {
public:
    static bool loadConfig(const std::string& config_path, ProcessingConfig& config) {
        std::ifstream config_file(config_path);
        if (!config_file.is_open()) {
            std::cerr << "Failed to open config file: " << config_path << std::endl;
            return false;
        }

        Json::Value root;
        Json::CharReaderBuilder builder;
        std::string errs;

        if (!Json::parseFromStream(builder, config_file, &root, &errs)) {
            std::cerr << "Failed to parse config file: " << errs << std::endl;
            return false;
        }

        try {
            // Model paths
            config.dsg_model_path = root["model"]["dsg_model_path"].asString();
            config.cdt_model_path = root["model"]["cdt_model_path"].asString();

            // Input
            config.image_directory = root["input"]["image_directory"].asString();
            config.image_extensions.clear();
            for (const auto& ext : root["input"]["image_extensions"]) {
                config.image_extensions.push_back(ext.asString());
            }

            // Output
            config.output_base_directory = root["output"]["base_directory"].asString();
            config.visualization_subdir = root["output"]["subdirs"]["visualization"].asString();
            config.pointcloud_subdir = root["output"]["subdirs"]["pointcloud"].asString();

            // Processing parameters
            config.erode_pixel = root["processing"]["erode_pixel"].asInt();
            config.detection_threshold = root["processing"]["detection_threshold"].asDouble();
            config.enable_height_filter = root["processing"]["enable_height_filter"].asBool();
            config.enable_ces_show = root["processing"]["enable_ces_show"].asBool();
            config.enable_hsv_dark_filter = root["processing"]["enable_hsv_dark_filter"].asBool();
            config.hsv_dark_threshold = root["processing"]["hsv_dark_threshold"].asInt();
            config.enable_debug_show = root["processing"]["enable_debug_show"].asBool();
            config.enable_draw_detection_box = root["processing"]["enable_draw_detection_box"].asBool();

            // Image size
            config.input_width = root["image_size"]["input_width"].asInt();
            config.input_height = root["image_size"]["input_height"].asInt();
            config.crop_height = root["image_size"]["crop_height"].asInt();
            config.model_width = root["image_size"]["model_width"].asInt();
            config.model_height = root["image_size"]["model_height"].asInt();

            // Visualization
            config.alpha_blend = root["visualization"]["alpha_blend"].asFloat();
            config.font_scale = root["visualization"]["font_scale"].asFloat();
            config.box_thickness = root["visualization"]["box_thickness"].asInt();

            return true;
        } catch (const std::exception& e) {
            std::cerr << "Error parsing config values: " << e.what() << std::endl;
            return false;
        }
    }

    static void printConfig(const ProcessingConfig& config) {
        std::cout << "=== Configuration ===" << std::endl;
        std::cout << "DSG Model: " << config.dsg_model_path << std::endl;
        std::cout << "CDT Model: " << config.cdt_model_path << std::endl;
        std::cout << "Image Directory: " << config.image_directory << std::endl;
        std::cout << "Output Base: " << config.output_base_directory << std::endl;
        std::cout << "Erode Pixel: " << config.erode_pixel << std::endl;
        std::cout << "Detection Threshold: " << config.detection_threshold << std::endl;
        std::cout << "Enable Height Filter: " << (config.enable_height_filter ? "Yes" : "No") << std::endl;
        std::cout << "Enable Debug Show: " << (config.enable_debug_show ? "Yes" : "No") << std::endl;
        std::cout << "=====================" << std::endl;
    }
};

#endif // CONFIG_LOADER_H
