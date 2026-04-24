#include <chrono>
#include <iostream>
#include "perception.h"
#include "dsg_perception.h"
#include "config_loader.h"
#include <rapidjson/document.h>
#include <fstream>
#include <opencv2/opencv.hpp>
#include "stereo_multi_match.h"

#include <pcl/common/common_headers.h>
#include <pcl/console/parse.h>
#include <pcl/point_types.h> //PCL中支持的点类型的头文件
#include "stereo_point_cloud_rgbl.h"
#include <filesystem>
#include <string>
#include <regex>
#include "rapidjson/istreamwrapper.h"
#include "rapidjson/writer.h"
#include "rapidjson/stringbuffer.h"
#include <json/json.h>

namespace fs = std::filesystem;

using namespace cv;
using namespace std;

using ColorMap = std::unordered_map<int, cv::Scalar>;
ColorMap colorMap;

map<int, string> mul_map_class;

void initColorMap()
{
    // 初始化颜色映射 (BGR格式)
    colorMap[0] = cv::Scalar(119, 119, 119); // 灰色
    colorMap[1] = cv::Scalar(200, 0, 0); // 类别 1: background 蓝色
    colorMap[2] = cv::Scalar(102, 255, 100); // 类别 2: grass 绿色
    colorMap[3] = cv::Scalar(0, 89, 118); // 类别 3: road 褐色
    colorMap[4] = cv::Scalar(0, 255, 255); // 类别 4: dynamic 黄色
    colorMap[5] = cv::Scalar(0, 0, 255); // 类别 5: static_obstacle 红色
    colorMap[6] = cv::Scalar(0, 165, 255); // 类别 6: wall obstacle 墙面类障碍物（亮橙色）
    colorMap[7] = cv::Scalar(147, 20, 255); // 类别 7: vehicle obstacle 车辆类障碍物（洋红）
    colorMap[8] = cv::Scalar(255, 255, 0); // 类别 8: pole 杆子类障碍物（青色）
    colorMap[9] = cv::Scalar(48, 130, 245); // 类别 9: impassable obstacle 不可通行类障碍物（深天蓝）
    colorMap[10] = cv::Scalar(128, 64, 0); // 类别 10: depression obstacle 凹陷类障碍物（棕色）
    colorMap[11] = cv::Scalar(34, 139, 34); // 类别 11: grass_bush 草类灌木（森林绿）
    colorMap[12] = cv::Scalar(203, 192, 255); // 类别 12: limb_bush 枝干结构灌木（浅紫）
    colorMap[13] = cv::Scalar(226, 43, 138);

    colorMap[100] = cv::Scalar(255, 255, 0);
    colorMap[101] = cv::Scalar(0, 0, 255);
    colorMap[102] = cv::Scalar(0, 0, 255);
    colorMap[103] = cv::Scalar(255, 255, 0);
    colorMap[104] = cv::Scalar(0, 0, 255);
    colorMap[105] = cv::Scalar(0, 255, 255);
    colorMap[106] = cv::Scalar(0, 0, 255);
    colorMap[107] = cv::Scalar(0, 255, 255);
}


void initMulClassMap()
{
    mul_map_class[0] = "unla";
    mul_map_class[1] = "back";
    mul_map_class[2] = "gras";
    mul_map_class[3] = "road";
    mul_map_class[4] = "dyna";
    mul_map_class[5] = "stat";
    mul_map_class[6] = "wall";
    mul_map_class[7] = "vehi";
    mul_map_class[8] = "pole";
    mul_map_class[9] = "impa";
    mul_map_class[10] = "depr";
    mul_map_class[11] = "bush";
    mul_map_class[12] = "limb";
    mul_map_class[13] = "grass_around";

    mul_map_class[100] = "pole";
    mul_map_class[101] = "obst";
    mul_map_class[102] = "fixo";
    mul_map_class[103] = "car";
    mul_map_class[104] = "stat";
    mul_map_class[105] = "dyna";
    mul_map_class[106] = "chst";
    mul_map_class[107] = "pers";
}

void convertIdToRGB(const cv::Mat& img_lab, cv::Mat& parsing_img)
{
    for (int i = 0; i < img_lab.rows; ++i)
    {
        for (int j = 0; j < img_lab.cols; ++j)
        {
            int id = img_lab.at<uchar>(i, j);

            auto it = colorMap.find(id);
            if (it != colorMap.end())
            {
                const cv::Scalar& color = it->second;
                parsing_img.at<cv::Vec3b>(i, j) = cv::Vec3b(
                    static_cast<uchar>(color[0]),
                    static_cast<uchar>(color[1]),
                    static_cast<uchar>(color[2])
                );
            }
            else
            {
                parsing_img.at<cv::Vec3b>(i, j) = cv::Vec3b(0, 0, 0);
            }
        }
    }
}


int savePcdfile_with_rgb_label(pcl::PointCloud<pcl::PointXYZRGBL> xyz_rgbi_cloud, string save_name)
{
    std::string pc_name = save_name + ".pcd";
    std::ofstream fout_pc_name(pc_name);

    fout_pc_name << "# .PCD v0.7 - Point Cloud Data file format" << std::endl;
    fout_pc_name << "VERSION 0.7" << std::endl;
    fout_pc_name << "FIELDS x y z rgb label" << std::endl;
    fout_pc_name << "SIZE 4 4 4 4 4" << std::endl;
    fout_pc_name << "TYPE F F F F U" << std::endl;
    fout_pc_name << "COUNT 1 1 1 1 1" << std::endl;
    fout_pc_name << "WIDTH " << xyz_rgbi_cloud.points.size() << std::endl;
    fout_pc_name << "HEIGHT 1" << std::endl;
    fout_pc_name << "VIEWPOINT 0 0 0 1 0 0 0" << std::endl;
    fout_pc_name << "POINTS " << xyz_rgbi_cloud.points.size() << std::endl;
    fout_pc_name << "DATA ascii" << std::endl;

    for (auto& point : xyz_rgbi_cloud.points)
    {
        fout_pc_name << point.x << " " << point.y << " " << point.z << " "
            << point.rgb << " " << point.label << std::endl;
    }
    fout_pc_name.close();
    return 1;
}

Mat drawResult(Mat& img_src, Mat& img_lab, std::vector<Detection>& dect_src, Mat& img_seg_show, bool enable_draw_dect = false)
{
    cv::Mat parsing_img = Mat::zeros(img_lab.rows, img_lab.cols, CV_8UC3);
    initColorMap();
    convertIdToRGB(img_lab, parsing_img);
    cv::resize(parsing_img, parsing_img, img_src.size(), 0, 0, cv::INTER_NEAREST);

    float alpha_f = 0.6;
    addWeighted(img_src, alpha_f, parsing_img, 1 - alpha_f, 0.0, img_seg_show);

    if (enable_draw_dect)
    {
        for (size_t i = 0; i < dect_src.size(); i++)
        {
            int dect_num = dect_src[i].id;
            std::string obj_name = mul_map_class[dect_num];
            stringstream text_ss;
            text_ss << obj_name << ":" << std::fixed << std::setprecision(2) << dect_src[i].score;
            Bbox obj_box = dect_src.at(i).bbox;
            int xmin = std::max(static_cast<int>(obj_box.xmin), 0);
            int ymin = std::max(static_cast<int>(obj_box.ymin), 0);
            int xmax = std::min(static_cast<int>(obj_box.xmax), img_seg_show.cols);
            int ymax = std::min(static_cast<int>(obj_box.ymax), img_seg_show.rows);
            if (xmin >= xmax || ymin >= ymax)
                continue;
            cv::Rect rect_tmp(xmin, ymin, xmax - xmin, ymax - ymin);
            cv::rectangle(img_seg_show, rect_tmp, cv::Scalar(0, 255, 0), 2);
            cv::putText(img_seg_show, text_ss.str(), cv::Point(xmin, ymin + 15), FONT_HERSHEY_SIMPLEX,
                        0.5, cv::Scalar(0, 255, 0), 1, cv::LINE_AA);
        }
    }
    return parsing_img;
}


void checkDir(string path)
{
    if (access(path.c_str(), 0) == -1)
        mkdir(path.c_str(), 0777);
}

int extractSequenceNumber(const std::string& fileName) {
    std::vector<std::regex> patterns = {
        std::regex(R"(.*?_(\d{4})_?.*)"),
        std::regex(R"(.*?_(\d{3})_?.*)"),
        std::regex(R"(.*?_(\d{2})_?.*)"),
        std::regex(R"(.*?(\d{4})\.?.*)"),
        std::regex(R"(.*?(\d{3})\.?.*)"),
        std::regex(R"(.*?(\d{2})\.?.*)"),
        std::regex(R"(.*?(\d+)\.?.*)")
    };

    for (const auto& pattern : patterns) {
        std::smatch match;
        if (std::regex_match(fileName, match, pattern)) {
            try {
                return std::stoi(match[1].str());
            } catch (...) {
                continue;
            }
        }
    }

    std::regex numberPattern(R"(\d+)");
    std::sregex_iterator iter(fileName.begin(), fileName.end(), numberPattern);
    std::sregex_iterator end;

    int lastNumber = -1;
    for (; iter != end; ++iter) {
        try {
            lastNumber = std::stoi(iter->str());
        } catch (...) {
            continue;
        }
    }

    return lastNumber;
}


int main(int argc, char** argv)
{
    cout << "==offline debug initial start====" << endl;

    // ===== 直接配置（无需 config.json）=====
    ProcessingConfig config;

    // 从环境变量读取模型路径，如果没有则使用默认值
    const char* env_model_path = std::getenv("DSG_MODEL_PATH");
    if (env_model_path != nullptr && strlen(env_model_path) > 0) {
        config.dsg_model_path = std::string(env_model_path);
        cout << "Using DSG_MODEL_PATH from environment: " << config.dsg_model_path << endl;
    } else {
        config.dsg_model_path = "/home/youfeng/CLionProjects/05-offline_debug_fusion/offline_perception_debug/models/dsg_multi_20260407_640x384.bin";
        cout << "Using default DSG model: " << config.dsg_model_path << endl;
    }

    // 从环境变量读取输入目录，如果没有则使用默认值
    const char* env_input_dir = std::getenv("NIGHT_INPUT_DIR");
    if (env_input_dir != nullptr && strlen(env_input_dir) > 0) {
        config.image_directory = std::string(env_input_dir);
        cout << "Using NIGHT_INPUT_DIR from environment: " << config.image_directory << endl;
    } else {
        config.image_directory = "/home/youfeng/debug/custom/0124/20260402/debug/";
        cout << "Using default image directory: " << config.image_directory << endl;
    }

    config.image_extensions    = {".jpg", ".jpeg", ".png"};
    config.output_base_directory = "";
    config.visualization_subdir  = "dsg_multi_debug";
    config.pointcloud_subdir     = "dsg_pcd_debug";

    config.erode_pixel           = 205;
    config.detection_threshold   = 0.51;
    config.enable_height_filter  = false;
    config.enable_hsv_dark_filter = false;
    config.hsv_dark_threshold    = 80;
    config.enable_debug_show     = true;
    config.enable_draw_detection_box = false;

    config.input_width   = 640;
    config.input_height  = 480;
    config.crop_height   = 432;
    config.model_width   = 640;
    config.model_height  = 384;

    config.alpha_blend   = 0.6f;
    config.font_scale    = 0.5f;
    config.box_thickness = 2;
    // =========================================

    ConfigLoader::printConfig(config);

    std::string picDirpath = config.image_directory;
    if (picDirpath.back() == '/') {
        picDirpath = picDirpath.substr(0, picDirpath.length() - 1);
    }

    string saveMultiDirPath = picDirpath + "/" + config.visualization_subdir + "/";
    string savePcdDirPath = picDirpath + "/" + config.pointcloud_subdir + "/";

    checkDir(saveMultiDirPath);
    checkDir(savePcdDirPath);

    initMulClassMap();

    StereoMultiMatch stereo_multi_match;
    stereo_point_cloud stereoPointCloud;
    dsg_perception dsgPerception;

    dsgPerception.perception_init(config.dsg_model_path.c_str());
    stereo_multi_match.stereo_multi_param_init();

    // 获取图像文件列表
    std::vector<cv::String> fileNames;
    for (const auto& ext : config.image_extensions) {
        std::vector<cv::String> files;
        cv::glob(picDirpath + "/*" + ext, files);
        fileNames.insert(fileNames.end(), files.begin(), files.end());
    }

    cout << "From Path " << picDirpath << " get test image count: " << fileNames.size() << endl;

    // 排序文件
    std::vector<std::pair<int, std::string>> sortedFiles;
    for (const auto& fullPath : fileNames) {
        std::filesystem::path filePath(fullPath);
        std::string fileName = filePath.stem().string();
        int seqNum = extractSequenceNumber(fileName);
        sortedFiles.push_back({seqNum, fullPath});
    }

    std::sort(sortedFiles.begin(), sortedFiles.end());

    int count_stereo = 0;

    for (size_t i = 0; i < sortedFiles.size(); i++)
    {
        string current_file_path = sortedFiles[i].second;
        int sequence_number = sortedFiles[i].first;

        std::filesystem::path file_path(current_file_path);
        string name = file_path.stem().string();

        cout << "sequence_number: " << sequence_number << ", name: " << name << endl;

        Mat stereo_img = imread(current_file_path);
        if (stereo_img.empty())
        {
            cerr << "Warning: failed to load image: " << current_file_path << ", skipping." << endl;
            continue;
        }
        if (stereo_img.cols < config.input_width * 2 || stereo_img.rows < config.input_height)
        {
            cerr << "Warning: image size " << stereo_img.cols << "x" << stereo_img.rows
                 << " too small, skipping." << endl;
            continue;
        }

        string finalPicPath = saveMultiDirPath + name + "_dsg_multi.jpg";
        string labelPcdPath = savePcdDirPath + name + "_rgbl";

        std::vector<Detection> dect_src, dect_dst;
        Mat lab_out, lab_dst;
        cv::Mat img_label = cv::Mat::zeros(config.model_height, config.model_width, CV_8UC1) + 1;

        cv::Rect left_region(0, 0, config.input_width, config.input_height);
        cv::Rect right_region(config.input_width, 0, config.input_width, config.input_height);

        Mat rectifyImageL = stereo_img(left_region);
        Mat rectifyImageR = stereo_img(right_region);

        Mat grayImageL, grayImageR;
        cvtColor(rectifyImageL, grayImageL, COLOR_BGR2GRAY);
        cvtColor(rectifyImageR, grayImageR, COLOR_BGR2GRAY);

        Mat xyz_rgbl, final_compared;
        auto start = std::chrono::high_resolution_clock::now();

        cv::Rect cropRegion(0, 0, rectifyImageL.cols, config.crop_height);
        cv::Mat croppedImg = rectifyImageL(cropRegion);

        // 1. Resize to model dimensions for inference
        cv::Mat resizedImg;
        cv::resize(croppedImg, resizedImg, cv::Size(config.model_width, config.model_height));

        dsgPerception.ori_height = resizedImg.rows;
        dsgPerception.ori_width  = resizedImg.cols;

        // 2. Inference: detection + segmentation (no argmax, with erode)
        dsgPerception.perception_process_bgr_no_argmax_erode(
            resizedImg, dect_src, img_label, lab_out, config.erode_pixel);

        // 3. Resize segmentation result from model size back to crop height
        cv::resize(lab_out, lab_dst, cv::Size(config.model_width, config.crop_height), 0, 0, cv::INTER_NEAREST);

        // 4. Map detection IDs to 100+ format
        dect_dst.clear();
        for (const auto& det : dect_src) {
            Detection fixed_det = det;
            fixed_det.id += 100;
            dect_dst.push_back(fixed_det);
        }

        // 5. Optional HSV dark filter: mark dark regions as road (class 3)
        if (config.enable_hsv_dark_filter) {
            cv::Mat hsvImg;
            cv::cvtColor(croppedImg, hsvImg, cv::COLOR_BGR2HSV);

            cv::Scalar lowerBlack(0, 0, 0);
            cv::Scalar upperBlack(180, 50, config.hsv_dark_threshold);

            cv::Mat darkMask;
            cv::inRange(hsvImg, lowerBlack, upperBlack, darkMask);

            cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(5, 5));
            cv::morphologyEx(darkMask, darkMask, cv::MORPH_CLOSE, kernel);
            cv::morphologyEx(darkMask, darkMask, cv::MORPH_OPEN, kernel);

            cv::Mat resizedMask;
            cv::resize(darkMask, resizedMask, lab_dst.size(), 0, 0, cv::INTER_NEAREST);
            lab_dst.setTo(3, resizedMask);
        }

        // 6. Depth computation
        Mat depth_cal = stereo_multi_match.stereo_multi_process(grayImageL, grayImageR, config.enable_height_filter);

        // 7. Crop depth to match crop_height
        cv::Mat depth_crop = depth_cal(cv::Rect(0, 0, config.model_width, config.crop_height)).clone();

        pcl::PointCloud<pcl::PointXYZRGBL> xyz_rgbi_cloud = pcl::PointCloud<pcl::PointXYZRGBL>();
        pcl::PointCloud<pcl::PointXYZRGBL> out_xyz_rgbi_cloud = pcl::PointCloud<pcl::PointXYZRGBL>();

        stereo_multi_match.stereo_process_pci_depth_rgb_seg_det_fusion(depth_crop, lab_dst, dect_dst, croppedImg,
                                                                       xyz_rgbi_cloud,
                                                                       out_xyz_rgbi_cloud);

        auto end = std::chrono::high_resolution_clock::now();
        std::chrono::duration<double, std::milli> duration = end - start;

        savePcdfile_with_rgb_label(out_xyz_rgbi_cloud, labelPcdPath);
        stereoPointCloud.show_xyz_rgbl_plane_point_cloud_final(out_xyz_rgbi_cloud, xyz_rgbl);

        if (config.enable_debug_show)
        {
            Mat img_seg_show;
            Mat pure_seg_mat = drawResult(croppedImg, lab_dst, dect_dst, img_seg_show, config.enable_draw_detection_box);
            Mat origin_seg;

            cv::resize(pure_seg_mat, pure_seg_mat, Size(config.model_width, config.crop_height));
            cv::resize(img_seg_show, img_seg_show, Size(config.model_width, config.crop_height));

            cv::hconcat(croppedImg, pure_seg_mat, origin_seg);
            cv::hconcat(origin_seg, img_seg_show, origin_seg);

            cv::vconcat(origin_seg, xyz_rgbl, final_compared);

            imwrite(finalPicPath, final_compared);
        }

        count_stereo++;
        std::unordered_map<uint32_t, size_t> label_count;
        for (const auto& point : out_xyz_rgbi_cloud)
        {
            label_count[point.label]++;
        }
        cout << "out_xyz_rgbi_cloud.size: " << out_xyz_rgbi_cloud.size() << endl;

        cout << "=====[dsg]back: " << label_count[1] << ", road:" << label_count[3] << ", stat:" << label_count[5] <<
            "=======" << endl;
    }

    dsgPerception.perception_release();

    cout << "Total processed images: " << count_stereo << endl;
    return 0;
}
