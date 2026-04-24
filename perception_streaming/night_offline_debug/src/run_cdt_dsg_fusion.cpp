#include <chrono>
#include <iostream>
#include "perception.h"
#include "dsg_perception.h"
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
#include "rapidjson/istreamwrapper.h"
#include "rapidjson/writer.h"
#include "rapidjson/stringbuffer.h"
#include <json/json.h>
#include "cdt_perception.h"

namespace fs = std::filesystem;

using namespace cv;
using namespace std;

// 定义类型别名以提高代码可读性
//using ColorMap = std::unordered_map<int, std::array<uint8_t, 3>>;

using ColorMap = std::unordered_map<int, cv::Scalar>;
ColorMap colorMap;

// 定义颜色映射为全局变量
map<int, string> mul_map_class;

#define OVER_AREA 2500

//void initColorMap() {
//// 初始化颜色映射
//    colorMap[0] = {119, 119, 119};
//    colorMap[1] = {0, 0, 200};       // 类别 1: background 蓝色
//    colorMap[2] = {100, 255, 102};   // 类别 2: grass 绿色
//    colorMap[3] = {118, 89, 0};      // 类别 3: road 褐色
//    colorMap[4] = {255, 255, 0};     // 类别 4: dynamic 黄色
//    colorMap[5] = {255, 0, 0};       // 类别 5: static_obstacle 红色
//    colorMap[6] = {255, 165, 0};     // 类别 6: wall obstacle 墙面类障碍物（亮橙色）
//    colorMap[7] = {255, 20, 147};    // 类别 7: vehicle obstacle 车辆类障碍物（洋红）
//    colorMap[8] = {0, 255, 255};     // 类别 8: pole 杆子类障碍物（青色）
//    colorMap[9] = {245, 130, 48};    // 类别 9: impassable obstacle 不可通行类障碍物（深天蓝）
//    colorMap[10] = {0, 64, 128};     // 类别 10: depression obstacle 凹陷类障碍物（棕色）
//    colorMap[11] = {34, 139, 34};    // 类别 11: grass_bush 草类灌木（森林绿）
//    colorMap[12] = {255, 192, 203};  // 类别 12: limb_bush 枝干结构灌木（浅紫）
//}

void initColorMap() {
    // 初始化颜色映射 (BGR格式)
    colorMap[0] = cv::Scalar(119, 119, 119);  // 灰色
    colorMap[1] = cv::Scalar(200, 0, 0);      // 类别 1: background 蓝色
    colorMap[2] = cv::Scalar(102, 255, 100);  // 类别 2: grass 绿色
    colorMap[3] = cv::Scalar(0, 89, 118);     // 类别 3: road 褐色
    colorMap[4] = cv::Scalar(0, 255, 255);    // 类别 4: dynamic 黄色
    colorMap[5] = cv::Scalar(0, 0, 255);      // 类别 5: static_obstacle 红色
    colorMap[6] = cv::Scalar(0, 165, 255);    // 类别 6: wall obstacle 墙面类障碍物（亮橙色）
    colorMap[7] = cv::Scalar(147, 20, 255);   // 类别 7: vehicle obstacle 车辆类障碍物（洋红）
    colorMap[8] = cv::Scalar(255, 255, 0);    // 类别 8: pole 杆子类障碍物（青色）
    colorMap[9] = cv::Scalar(48, 130, 245);   // 类别 9: impassable obstacle 不可通行类障碍物（深天蓝）
    colorMap[10] = cv::Scalar(128, 64, 0);    // 类别 10: depression obstacle 凹陷类障碍物（棕色）
    colorMap[11] = cv::Scalar(34, 139, 34);   // 类别 11: grass_bush 草类灌木（森林绿）
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


void initMulClassMap() {
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

//cv::Vec3b getColorVec3b(int class_id) {
//    auto it = colorMap.find(class_id);
//    if (it != colorMap.end()) {
//        const auto& color = it->second;
//        return cv::Vec3b(color[2], color[1], color[0]); // BGR格式
//    }
//    return cv::Vec3b(119, 119, 119); // 默认灰色
//}

cv::Vec3b getColorVec3b(int class_id) {
    auto it = colorMap.find(class_id);
    if (it != colorMap.end()) {
        // 从 cv::Scalar 提取 BGR 值
        const cv::Scalar& color = it->second;
        return cv::Vec3b(static_cast<uchar>(color[0]),
                         static_cast<uchar>(color[1]),
                         static_cast<uchar>(color[2]));
    }
    return cv::Vec3b(119, 119, 119); // 默认灰色
}


//void convertIdToRGB(const cv::Mat& img_lab, cv::Mat& parsing_img) {
//    for (int i = 0; i < img_lab.rows; ++i) {
//        for (int j = 0; j < img_lab.cols; ++j) {
//            int id = img_lab.at<uchar>(i, j); // 获取ID值
//
//            auto it = colorMap.find(id);
//            if(it != colorMap.end()) {
//                // 直接获取对应id的RGB颜色数组
//                const std::array<uint8_t, 3>& rgb = it->second;
//
//                // 将RGB值设置到新图像中
//                parsing_img.at<cv::Vec3b>(i, j) = cv::Vec3b(rgb[2], rgb[1], rgb[0]); // 注意OpenCV的颜色顺序是BGR
//            } else {
//                // 如果没有找到对应id的颜色，可以设置为默认颜色或者抛出错误等
////                std::cout << "No color defined for id: " << id << std::endl;
//                // 示例中采用跳过的方式，也可以分配一个默认颜色
//                parsing_img.at<cv::Vec3b>(i, j) = cv::Vec3b(0, 0, 0); // 默认设为黑色
//            }
//        }
//    }
//}

void convertIdToRGB(const cv::Mat& img_lab, cv::Mat& parsing_img) {
    for (int i = 0; i < img_lab.rows; ++i) {
        for (int j = 0; j < img_lab.cols; ++j) {
            int id = img_lab.at<uchar>(i, j); // 获取ID值

            auto it = colorMap.find(id);
            if(it != colorMap.end()) {
                // 从 cv::Scalar 获取颜色值
                const cv::Scalar& color = it->second;
                parsing_img.at<cv::Vec3b>(i, j) = cv::Vec3b(
                        static_cast<uchar>(color[0]),
                        static_cast<uchar>(color[1]),
                        static_cast<uchar>(color[2])
                );
            } else {
                parsing_img.at<cv::Vec3b>(i, j) = cv::Vec3b(0, 0, 0); // 默认设为黑色
            }
        }
    }
}


int savePcdfile_with_rgb_label(pcl::PointCloud<pcl::PointXYZRGBL> xyz_rgbi_cloud, string save_name){
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

    for (auto& point : xyz_rgbi_cloud.points){
        fout_pc_name << point.x << " " << point.y << " " << point.z << " "
        << point.rgb << " " << point.label<<std::endl;
    }
    fout_pc_name.close();
    return 1;
}
void filterLabelDect(Mat &src_lab, std::vector<Detection> &dect_src,
                     Mat &lab_dst, std::vector<Detection> &dect_dst)
{
    // 先克隆，避免污染原图
    src_lab.copyTo(lab_dst);

    for (size_t i = 0; i < dect_src.size(); i++)
    {
        Bbox obj_box = dect_src[i].bbox;
        int8_t target_id = dect_src[i].id;

        int xmin = std::max(static_cast<int>(std::lround(obj_box.xmin)), 0);
        int ymin = std::max(static_cast<int>(std::lround(obj_box.ymin)), 0);
        int xmax = std::min(static_cast<int>(std::lround(obj_box.xmax)), lab_dst.cols - 1);
        int ymax = std::min(static_cast<int>(std::lround(obj_box.ymax)), lab_dst.rows - 1);

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
//        else if (target_id == 6)
//        {
//            process_roi(106);
//        }else {
//            Detection det = dect_src[i];
//            det.id = 100 + det.id; // 更新 id
//            if(det.id>200) continue;
//            dect_dst.push_back(det);
//        }

        // 检查原始图（src_lab）中该区域是否包含有效标签
//        bool pic_ret = checkLabelInRegion(src_lab, obj_box);
//        bool pic_ret = true;
//        if (pic_ret)
//        {
//            Detection det = dect_src[i];
//            det.id = 100 + det.id; // 更新 id
//            if(det.id>200) continue;
//            dect_dst.push_back(det);
//        }
    }
}

Mat drawResult(Mat &img_src, Mat &img_lab, std::vector<Detection> &dect_src, Mat &img_seg_show)
{
    cv::Mat parsing_img=Mat::zeros(img_lab.rows, img_lab.cols, CV_8UC3);
    Mat_<uint8_t> lawn_label = img_lab;
    initColorMap();
    convertIdToRGB(img_lab, parsing_img);
    for(size_t i=0;i<dect_src.size();i++) {
        int dect_num = dect_src[i].id;
        std::string obj_name = mul_map_class[dect_num];
        stringstream text_ss;
        text_ss << obj_name << ":" << std::fixed << std::setprecision(2) << dect_src[i].score;
//        cout << text_ss.str() << endl;
        Bbox obj_box =dect_src.at(i).bbox;
        cv::Rect rect_tmp(obj_box.xmin, obj_box.ymin, (obj_box.xmax - obj_box.xmin), (obj_box.ymax - obj_box.ymin));
        cv::rectangle(img_seg_show, rect_tmp, cv::Scalar(0, 255, 0), 2);
        cv::putText(img_seg_show, text_ss.str(), cv::Point(obj_box.xmin, obj_box.ymin + 15), FONT_HERSHEY_SIMPLEX,
                    0.5, cv::Scalar(0, 255, 0), 1, cv::LINE_AA);
    }
    cv::resize(parsing_img, parsing_img, img_src.size(), 0, 0, cv::INTER_NEAREST);

    float alpha_f = 0.6;
    addWeighted(img_src, alpha_f, parsing_img, 1 - alpha_f, 0.0, img_seg_show);
    return parsing_img;
}
//
//Mat visualize_results(const cv::Mat& original_img, std::vector<Detection> &detections, Mat &img_label){
//
//    initColorMap();
////    initMulClassMap();
//    cv::Mat bgr_mat = original_img.clone();
//
//    // 保存检测结果
////    cv::imwrite(output_detect_file, bgr_mat);
//
//    // 可视化分割结果
//    int height = bgr_mat.rows;
//    int width = bgr_mat.cols;
//    cv::Mat segmentation_result(height, width, CV_8UC3);
//
//    Mat_ <uint8_t> lawn_label = img_label;
//    // 填充 segmentation_result 图像，根据 mask_info 映射类别
//    for (int h = 0; h < height; h++) {
//        for (int w = 0; w < width; w++) {
////            int mask_class = result.mask_info[h * width + w];  // 获取该像素的类别
//            int8_t mask_class = lawn_label(h, w);
////            segmentation_result.at<cv::Vec3b>(h, w) = color_map[mask_class];
//            segmentation_result.at<cv::Vec3b>(h, w) = getColorVec3b(mask_class);
//        }
//    }
//
//    // 叠加分割结果到原图，50%透明度
//    cv::Mat blended_image;
//    float alpha = 0.5;  // 透明度
//    cv::addWeighted(bgr_mat, alpha, segmentation_result, 1 - alpha, 0.0, blended_image);
//
//
//    // 绘制检测框
//    for (const auto& det : detections) {
//        // 使用 cv::rectangle 绘制检测框
//        cv::rectangle(blended_image, cv::Point(det.bbox.xmin, det.bbox.ymin),
//                      cv::Point(det.bbox.xmax, det.bbox.ymax), cv::Scalar(0, 255, 0), 2);
//
////        int det_num = 100+det.id;
//        int det_num = det.id;
//        std::string obj_name =mul_map_class[det_num];
//
//        stringstream text_ss;
//        text_ss << obj_name << ":" << std::fixed<< std::setprecision(2) << det.score;
//        cv::putText(blended_image, text_ss.str(), cv::Point(det.bbox.xmin+5, det.bbox.ymin + 15),
//                    cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(0, 255, 0), 2);
//    }
//
//
//    // 保存分割结果
////    cv::imwrite(output_seg_file, blended_image);
//    return blended_image;
//}


void checkDir(string path){
    if (access(path.c_str(), 0) == -1) //如果文件夹不存在
        mkdir(path.c_str(), 0777); //则创建
}

int extractLastFourDigits(std::string& filename) {
    // 找到最后一个下划线的位置
    size_t lastUnderscorePos = filename.rfind('_');
//    if (lastUnderscorePos == std::string::npos || lastUnderscorePos + 5 >= filename.size()) {
//        throw std::invalid_argument("Invalid filename format");
//    }

    // 提取下划线之后的四位字符
    std::string lastPart = filename.substr(lastUnderscorePos + 1, 4);

    // 检查这四位字符是否都是数字
    if (!std::all_of(lastPart.begin(), lastPart.end(), ::isdigit)) {
        throw std::invalid_argument("The last part is not a number");
    }

    // 将提取的部分转换为整数
    return std::stoi(lastPart);
}

std::map<std::string, int> countLabelsWithNames(const cv::Mat& label_image) {
    // 确保 mul_map_class 已经初始化
//    if (mul_map_class.empty()) {
//        initMulClassMap();
//    }

    std::map<std::string, int> label_counts;

    // 遍历图像的每个像素
    for (int y = 0; y < label_image.rows; ++y) {
        for (int x = 0; x < label_image.cols; ++x) {
            // 获取当前像素的标签值
            int label_id = static_cast<int>(label_image.at<uint8_t>(y, x));

            // 查找标签对应的名称
            auto it = mul_map_class.find(label_id);
            std::string label_name;
            if (it != mul_map_class.end()) {
                label_name = it->second;
            } else {
                // 如果找不到对应名称，则使用默认名称
                label_name = "unknown_" + std::to_string(label_id);
            }

            // 增加该标签的计数
            label_counts[label_name]++;
        }
    }

    return label_counts;
}

// 修正后的专业伪彩图生成函数
Mat createColorMappedImage(const Mat& input, int colormap = COLORMAP_JET, const string& title = "") {
    Mat result;

    if(input.empty()) {
        cerr << "Error: Input image is empty!" << endl;
        return result;
    }

    // 方法1：简单的有效值掩码（适用于视差图/深度图）
    Mat valid_mask = (input > 0); // 通常深度/视差值大于0

    // 方法2：如果需要处理NaN和无穷大，转换为CV_32F或CV_64F处理
    Mat input_float;
    input.convertTo(input_float, CV_32F);

    // 创建更严格的掩码（处理NaN、无穷大和负值）
    valid_mask = (input_float > 0) & (input_float < FLT_MAX);

    // 找到有效区域的范围
    double minVal, maxVal;
    minMaxLoc(input, &minVal, &maxVal, 0, 0, valid_mask);

    cout << title << " range: [" << minVal << ", " << maxVal << "]" << endl;

    // 归一化到0-255范围
    Mat normalized;
    if(maxVal > minVal) {
        input.convertTo(normalized, CV_8UC1, 255.0/(maxVal-minVal), -minVal*255.0/(maxVal-minVal));
    } else {
        normalized = Mat(input.size(), CV_8UC1, Scalar(128));
    }

    // 应用伪彩色映射
    applyColorMap(normalized, result, colormap);

    // 将无效区域标记为黑色
    result.setTo(Scalar(0, 0, 0), ~valid_mask);

    // 添加标题（可选）
    if(!title.empty()) {
        putText(result, title, Point(10, 30), FONT_HERSHEY_SIMPLEX, 1.0, Scalar(255,255,255), 2);
    }

    return result;
}

Rect getCombinedBoundingRectOfContours(const Mat &binaryMask)
{
    vector<vector<Point>> contours;
    findContours(binaryMask, contours, RETR_EXTERNAL, CHAIN_APPROX_SIMPLE);

    Rect combined;
    for (const auto &contour : contours)
    {
        if (contour.size() < 3)
            continue;
        combined |= boundingRect(contour);
    }
    return combined;
}

Rect detectAndMarkAbnormalRegion(
        const Mat &croppedImg,
        Mat &img_label,
        const Rect &roi,
        const Scalar &lower1, const Scalar &upper1,
        const Scalar &lower2, const Scalar &upper2)
{
    // 检查输入图像有效性
    if (croppedImg.empty() || img_label.empty())
    {
        cerr << "Invalid input image." << endl;
        return Rect(); // 返回空 Rect
    }

    // 调整 ROI 不越界
    Rect safeROI = roi & Rect(0, 0, croppedImg.cols, croppedImg.rows);
    safeROI.width = max(0, safeROI.width);
    safeROI.height = max(0, safeROI.height);
    if (safeROI.area() <= 0)
    {
        cerr << "Invalid ROI area after clipping." << endl;
        return Rect(); // 返回空 Rect
    }

    // 提取 ROI 图像
    Mat roiImage = croppedImg(safeROI).clone();

    // 转换为 HSV
    Mat hsvImage;
    cvtColor(roiImage, hsvImage, COLOR_BGR2HSV);

    // 第一次颜色检测
    Mat mask1;
    inRange(hsvImage, lower1, upper1, mask1);
    Rect abnormalBox = getCombinedBoundingRectOfContours(mask1);

    bool validBox = (abnormalBox.area() > 0 &&
                     abnormalBox.width > 8 &&
                     abnormalBox.height > 4);

    // 如果第一次没找到，尝试第二次颜色检测
    if (!validBox)
    {
        Mat mask2;
        inRange(hsvImage, lower2, upper2, mask2);
        abnormalBox = getCombinedBoundingRectOfContours(mask2);
    }

    // 如果仍然无效，直接返回空 Rect
    if (abnormalBox.area() <= 0)
    {
        return Rect();
    }

    // 转换为全局坐标系
    abnormalBox.x += safeROI.x;
    abnormalBox.y += safeROI.y;

    // 再次限制在图像范围内
    Rect imgBounds(0, 0, croppedImg.cols, croppedImg.rows);
    Rect finalBox = abnormalBox & imgBounds;

    // 最终确保宽高 > 0
    if (finalBox.width <= 0 || finalBox.height <= 0)
    {
        return Rect(); // 宽或高无效，返回空 Rect
    }

    // 更新 label
    if (!img_label(finalBox).empty() && finalBox.width > 0 && finalBox.height > 0)
    {
//        img_label(finalBox).setTo(Scalar(2));
        img_label(finalBox).setTo(Scalar(-3));
    }

    return finalBox;
}
cv::Rect processCroppedImage(const cv::Mat& croppedImg, cv::Mat& lab_dst, const std::vector<Detection>& ct_dect_src) {
    // 检查 ct_dect_src 是否为空或者包含2个以上元素
    if (ct_dect_src.empty() || ct_dect_src.size() >= 2) {
        return cv::Rect(); // 返回空矩形
    }

    // 如果 ct_dect_src 包含一个元素
    if (ct_dect_src.size() == 1) {
//        cv::Rect rect = ct_dect_src[0].bbox;;
        cv::Rect rect = cv::Rect(ct_dect_src[0].bbox.xmin, ct_dect_src[0].bbox.ymin,
                                      ct_dect_src[0].bbox.xmax, ct_dect_src[0].bbox.ymax);


        // 将 lab_dst 中对应区域的标签设置为 -1
        // 假设 lab_dst 是单通道矩阵，且数据类型支持赋值 -1
        if (rect.x >= 0 && rect.y >= 0 &&
            rect.x + rect.width <= lab_dst.cols &&
            rect.y + rect.height <= lab_dst.rows) {
            lab_dst(rect) = -1;
        } else {
            // 如果矩形超出范围，返回空矩形
            return cv::Rect();
        }

        return rect; // 返回该矩形
    }

    // 其他情况返回空矩形（理论上不会执行到这里）
    return cv::Rect();
}


cv::Rect get_cdt_rect(const std::vector<Detection>& ct_dect_src) {
    // 检查 ct_dect_src 是否为空或者包含2个以上元素
    if (ct_dect_src.empty() || ct_dect_src.size() >= 2) {
        return cv::Rect(); // 返回空矩形
    }

    // 如果 ct_dect_src 包含一个元素
    if (ct_dect_src.size() == 1) {
        int rect_xmin = ct_dect_src[0].bbox.xmin;
        int rect_xmax = ct_dect_src[0].bbox.xmax;
        int rect_ymin = ct_dect_src[0].bbox.ymin;
        int rect_ymax = ct_dect_src[0].bbox.ymax;

        int rect_width = rect_xmax - rect_xmin;
        // int rect_heigh = rect_ymax - rect_ymin;
        int rect_heigh = 384 - rect_ymin;
        cout << "rect_heigh: " << rect_heigh << endl;
        cv::Rect rect = cv::Rect(rect_xmin, rect_ymin, rect_width, rect_heigh);
        if(rect_xmin >0 && rect_ymin>0 && rect_xmax<=640 && rect_ymax<=480 && rect_heigh<50) {
            return rect; // 返回该矩形
        } else {
            return cv::Rect();
        }
    }
    // 其他情况返回空矩形（理论上不会执行到这里）
    return cv::Rect();
}
std::string getParentDirectory(const std::string& filePath) {
    if (filePath.empty()) {
        return "";
    }

    size_t lastSlash = filePath.find_last_of("/\\");
    if (lastSlash == std::string::npos) {
        return "";
    }

    return filePath.substr(0, lastSlash);
}

void processLabelContours(cv::Mat& label_img, bool& all_neighbors_are_lawn) {
    if (label_img.empty()) {
        return;
    }

    cv::Mat result = label_img.clone();

    // 创建掩码，找出非0、1、2的区域
    cv::Mat mask_non_target = (label_img != 0) & (label_img != 1) & (label_img != 2);

    // 查找连通区域
    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(mask_non_target, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);

    // 定义8邻域
    int dx[8] = {-1, -1, -1, 0, 0, 1, 1, 1};
    int dy[8] = {-1, 0, 1, -1, 1, -1, 0, 1};

    // 遍历每个连通区域
    for (const auto& contour : contours) {
        // 创建区域掩码
        cv::Mat region_mask = cv::Mat::zeros(label_img.size(), CV_8UC1);
        cv::fillPoly(region_mask, {contour}, cv::Scalar(255));

        // 统计边界邻域的标签分布
        int lawn_neighbor_count = 0;      // label==2的邻域数量
        int label1_neighbor_count = 0;    // label==1的邻域数量
        int other_neighbor_count = 0;     // 其他label的邻域数量
        int total_neighbor_count = 0;     // 总邻域数量
        bool region_touches_boundary = false;  // 检查区域是否接触边界

        // 遍历区域的边界点
        for (const auto& point : contour) {
            int x = point.x;
            int y = point.y;

            // 检查是否接触图片边界
            if (x == 0 || x == label_img.cols - 1 || y == 0 || y == label_img.rows - 1) {
                region_touches_boundary = true;
            }

            // 确保点在图像范围内
            if (x < 1 || x >= label_img.cols - 1 || y < 1 || y >= label_img.rows - 1) {
                continue;
            }

            // 检查当前边界点的8邻域
            for (int i = 0; i < 8; i++) {
                int nx = x + dx[i];
                int ny = y + dy[i];

                // 检查邻域点是否在图像范围内
                if (nx >= 0 && nx < label_img.cols && ny >= 0 && ny < label_img.rows) {
                    // 检查邻域点是否不在区域内
                    if (region_mask.at<uchar>(ny, nx) == 0) {
                        total_neighbor_count++;
                        uchar neighbor_label = label_img.at<uchar>(ny, nx);

                        if (neighbor_label == 2) {
                            lawn_neighbor_count++;
                        } else if (neighbor_label == 1) {
                            label1_neighbor_count++;
                        } else {
                            other_neighbor_count++;
                        }
                    }
                }
            }
        }

        // 计算草坪邻域的比例
        float lawn_ratio = (total_neighbor_count > 0) ?
                          (float)lawn_neighbor_count / total_neighbor_count : 0.0f;

        // 优化后的判断条件：
        // 1. 没有label==1的邻域 (不是background边界)
        // 2. 满足以下任一条件：
        //    a) 草坪邻域占比 >= 60% (主要被草坪包围)
        //    b) 接触图片边界
        bool should_mark_as_13 = (label1_neighbor_count == 0) &&
                                 (lawn_ratio >= 0.8f || region_touches_boundary);

        if (should_mark_as_13) {
            // 遍历整个图像，将区域内点设置为13
            for (int y = 0; y < label_img.rows; y++) {
                for (int x = 0; x < label_img.cols; x++) {
                    if (region_mask.at<uchar>(y, x) == 255) {
                        // 确保原来的标签不是0、1、2
                        if (label_img.at<uchar>(y, x) != 0 &&
                            label_img.at<uchar>(y, x) != 1 &&
                            label_img.at<uchar>(y, x) != 2) {
                            result.at<uchar>(y, x) = 13;
                        }
                    }
                }
            }
            all_neighbors_are_lawn = true; // 存在符合条件的区域，设置为true
        }
    }

    label_img = result;
}

//
// void processLabelContours(cv::Mat& label_img, bool& all_neighbors_are_lawn) {
//     if (label_img.empty()) {
//         return;
//     }
//
//     cv::Mat result = label_img.clone();
//
//     // 创建掩码，找出非0、1、2的区域
//     cv::Mat mask_non_target = (label_img != 0) & (label_img != 1) & (label_img != 2);
//
//     // 查找连通区域
//     std::vector<std::vector<cv::Point>> contours;
//     cv::findContours(mask_non_target, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);
//
//     // 定义8邻域
//     int dx[8] = {-1, -1, -1, 0, 0, 1, 1, 1};
//     int dy[8] = {-1, 0, 1, -1, 1, -1, 0, 1};
//
//     // 遍历每个连通区域
//     for (const auto& contour : contours) {
//         // 创建区域掩码
//         cv::Mat region_mask = cv::Mat::zeros(label_img.size(), CV_8UC1);
//         cv::fillPoly(region_mask, {contour}, cv::Scalar(255));
//
//         // 检查区域边界是否都被label==2包围
//         bool region_completely_surrounded_by_lawn = true;
//         bool region_touches_boundary = false;  // 新增：检查区域是否接触边界
//
//         // 遍历区域的边界点
//         for (const auto& point : contour) {
//             int x = point.x;
//             int y = point.y;
//
//             // 检查是否接触图片边界
//             if (x == 0 || x == label_img.cols - 1 || y == 0 || y == label_img.rows - 1) {
//                 region_touches_boundary = true;
//             }
//
//             // 确保点在图像范围内
//             if (x < 1 || x >= label_img.cols - 1 || y < 1 || y >= label_img.rows - 1) {
//                 region_completely_surrounded_by_lawn = false;
//                 continue;  // 继续检查其他点，因为可能接触边界
//             }
//
//             // 检查当前边界点的8邻域
//             for (int i = 0; i < 8; i++) {
//                 int nx = x + dx[i];
//                 int ny = y + dy[i];
//
//                 // 检查邻域点是否在图像范围内
//                 if (nx >= 0 && nx < label_img.cols && ny >= 0 && ny < label_img.rows) {
//                     // 如果邻域点不在区域内且不是label==2，则说明区域没有被完全包围
//                     if (region_mask.at<uchar>(ny, nx) == 0 && label_img.at<uchar>(ny, nx) != 2) {
//                         region_completely_surrounded_by_lawn = false;
//                         break;
//                     }
//                 } else {
//                     // 邻域点超出图像边界，说明区域接触边界
//                     region_touches_boundary = true;
//                 }
//             }
//
//             if (!region_completely_surrounded_by_lawn && region_touches_boundary) {
//                 break;  // 两种条件都满足时提前退出
//             }
//         }
//
//         // 如果整个区域都被label==2包围，或者区域接触图片边界，则将区域内所有点设置为13
//         if (region_completely_surrounded_by_lawn || region_touches_boundary) {
//             // 遍历整个图像，将区域内点设置为13
//             for (int y = 0; y < label_img.rows; y++) {
//                 for (int x = 0; x < label_img.cols; x++) {
//                     if (region_mask.at<uchar>(y, x) == 255) {
//                         // 确保原来的标签不是0、1、2
//                         if (label_img.at<uchar>(y, x) != 0 &&
//                             label_img.at<uchar>(y, x) != 1 &&
//                             label_img.at<uchar>(y, x) != 2) {
//                             result.at<uchar>(y, x) = 13;
//                         }
//                     }
//                 }
//             }
//             all_neighbors_are_lawn = true; // 存在符合条件的区域，设置为true
//         }
//     }
//
//     label_img = result;
// }


std::map<uchar, int> countLabels(const cv::Mat& label_img) {
    std::map<uchar, int> label_count;

    if (label_img.empty()) {
        return label_count;
    }

    // 遍历图像中的每个像素
    for (int y = 0; y < label_img.rows; y++) {
        for (int x = 0; x < label_img.cols; x++) {
            uchar label = label_img.at<uchar>(y, x);
            label_count[label]++;
        }
    }

    return label_count;
}

void checkLabelClasses(Mat &img) {
    // 读取图像为单通道（灰度图）
    std::map<uchar, int> histogram;

    // 遍历图像中的所有像素
    for (int y = 0; y < img.rows; ++y) {
        const uchar* rowPtr = img.ptr<uchar>(y);
        for (int x = 0; x < img.cols; ++x) {
            uchar pixelValue = rowPtr[x];
            histogram[pixelValue]++;
        }
    }

    std::cout << "result：" << std::endl;
    for (const auto& pair : histogram) {
        std::cout << "label: " << static_cast<int>(pair.first)
                  << ", count: " << pair.second << std::endl;
    }
}


int main(){
    cout << "==offline debug initial start====" << endl;
    int count_stereo=0;
    int frq_cdt=5;
    int m_erode_pixel=205;
    bool m_enable_roi = true;
    bool enable_height_filter_=true;
    bool enable_ces_show =true;
    bool all_neighbors_are_lawn=false;
    Rect cdt_rect;
//    string model_file = "/home/youfeng/CLionProjects/05-offline_debug_fusion/offline_debug_xyzi_multi/model/mul_20250807_640x384.bin";
    // string roiConfigPath = "/home/youfeng/CLionProjects/05-offline_debug_fusion/offline_debug_xyzrgbl_multi_sub/model/roi_config.json";

    string cdt_model_file = "/home/youfeng/CLionProjects/20-multask/07_dsg_perception/04_fusion_cdt_dsg/model/cdt_20251125_640x384.bin";
    // string model_file = "/home/youfeng/CLionProjects/05-offline_debug_fusion/offline_debug_xyzrgbl_multi_sub/model/sub_20251202_640x384.bin";
    // string model_file = "/home/youfeng/CLionProjects/20-multask/07_dsg_perception/04_fusion_cdt_dsg/model/dsg_20260115_640x384.bin";
    string model_file = "/home/youfeng/CLionProjects/04-offline_debug_seperate/night_segmentation/with_argmax/fpn+mobilev2.bin";
    // string img_full_path = "/home/youfeng/CLionProjects/05-offline_debug_fusion/offline_debug_xyzrgbl_dsg/data/dark1/match_0128_pcl20260109_191541_031_L20260109_191541_031_R20260109_191541_031.jpg";
    // string img_full_path = "/home/youfeng/CLionProjects/05-offline_debug_fusion/offline_debug_xyzrgbl_dsg/data/dark1/match_0002_pcl20260109_191500_031_L20260109_191500_031_R20260109_191500_031.jpg";
    string img_full_path = "/home/youfeng/CLionProjects/05-offline_debug_fusion/offline_debug_xyzrgbl_dsg/data/dark1/match_0002_pcl20260109_191500_031_L20260109_191500_031_R20260109_191500_031.jpg";
    std::string picDirpath = getParentDirectory(img_full_path);

    // string saveMultiDirPath = picDirpath + "/dsg_" + to_string(m_erode_pixel)+"_cdt/";
    string saveMultiDirPath = picDirpath + "/debug_pc/";
    string savePcdDirPath = picDirpath +"/dsg_cdt_pcd/";
    // string saveDisDirPath = picDirpath +"/dsg_dis_modify/";
    // string saveDepDirPath = picDirpath +"/dsg_dep_modify/";
//    string saveLabelDirPath = picDirpath +"/multi_label_1107_modify/";
//    string saveOriPcdDirPath = picDirpath +"/ori_pcd_0814/";

    double m_detection_threshold = 0.51;

    checkDir(saveMultiDirPath);
    checkDir(savePcdDirPath);
    // checkDir(saveDisDirPath);
    // checkDir(saveDepDirPath);
//    checkDir(saveLabelDirPath);

    initMulClassMap();

    StereoMultiMatch stereo_multi_match;
    stereo_point_cloud stereoPointCloud;
    dsg_perception dsgPerception;
    cdt_perception cdtPerception;

    bool m_enable_debug_show = true;
    const char *model_file_name = model_file.c_str();

//    std::string filename = std::filesystem::path(stereo_path).stem().string();
    cdtPerception.perception_init(cdt_model_file.c_str());
    dsgPerception.perception_init(model_file.c_str());
    stereo_multi_match.stereo_multi_param_init();

    // stereo_multi_match.enable_height_filter_ = true;

    // std::vector<cv::String> fileNames;
    // cv::glob(picDirpath, fileNames);	//获取文件夹下文件名序列
    // cout << "Frome Path "<<picDirpath << "  get test image count: " << fileNames.size() << endl;
    // for(size_t i=0;i<fileNames.size();i++)
    // {
        // string img_full_path = fileNames.at(i);

    int pos = img_full_path.find_last_of("/");
    int pos2 = img_full_path.find_last_of('.');
    string suf = img_full_path.substr(pos2 + 1, 3);
    // if (suf != "jpg") continue;
    string name = img_full_path.substr(pos + 1, pos2 - pos - 1);
    cout << "name: " << name << endl;

    //        string picPath = img_full_path;
    //        string segPicPath = saveMultiDirPath + name + "_seg.jpg";
    string finalPicPath = saveMultiDirPath + name + "_dsg_cdt_debug.jpg";
    string labelPcdPath = savePcdDirPath + name + "_rgbl";

    //        string singlePath = saveLabelDirPath + name + "_8u.png";
    //        string cropPicPath = saveLabelDirPath + name + "_crop.jpg";

    std::vector<Detection> dect_src, dect_dst, ct_dect_src;
    // Mat img_label = Mat::zeros(384, 640, CV_8UC1) + 2;
    Mat stereo_img = imread(img_full_path);
    Mat lab_out;
    cv::Mat lab_dst(384, 640, CV_8UC1);

    cv::Rect left_region(0, 0, 640, 480);  // 左半部分
    cv::Rect right_region(640, 0, 640, 480);  // 右半部分

    // 提取左半部分和右半部分
    Mat rectifyImageL = stereo_img(left_region);
    Mat rectifyImageR = stereo_img(right_region);

    Mat grayImageL, grayImageR;
    cvtColor(rectifyImageL, grayImageL, COLOR_BGR2GRAY);
    cvtColor(rectifyImageR, grayImageR, COLOR_BGR2GRAY);

    Mat xyz_rgbl, final_compared;
    auto start = std::chrono::high_resolution_clock::now();  // 开始时间

    cv::Rect cropRegion(0, 0, rectifyImageL.cols, 384);
    cv::Mat croppedImg = rectifyImageL(cropRegion);

    if(m_enable_roi){
        ct_dect_src.clear();
        cdtPerception.perception_process_bgr(croppedImg, ct_dect_src);
        // cout << "ct_dect_src size: " << ct_dect_src.size() << endl;
        cdt_rect = get_cdt_rect(ct_dect_src);
        // RCLCPP_INFO(this->get_logger(), "[global]===depth_time_cost: %.2f===reciev_latency: %.2f", depth_time_cost, depth_reciev_latency);
        cout << "cdt_rect: " << cdt_rect << endl;
        cout << "cdt_rect.area: " << cdt_rect.area() << endl;
        // RCLCPP_INFO(this->get_logger(), "cdt_rect: [x=%d, y=%d, w=%d, h=%d], area=%d",
        // cdt_rect.x, cdt_rect.y, cdt_rect.width, cdt_rect.height, static_cast<int>(cdt_rect.area()));
        // ret_cdt=1;
    }
    dsgPerception.process_infer_match(croppedImg, lab_dst);

    lab_dst(cdt_rect)=-1;

    // checkLabelClasses(lab_dst);


    // if (enable_ces_show)
    // {
    //     // Mat target_lab = processLabelContours(lab_dst, all_neighbors_are_lawn);
    //     processLabelContours(lab_dst, all_neighbors_are_lawn);
    //     std::map<uchar, int> label_counts = countLabels(lab_dst);
    //     // 打印统计结果
    //     for (const auto& pair : label_counts) {
    //         std::cout << "Label " << static_cast<int>(pair.first)
    //                   << ": " << pair.second << " pixels" << std::endl;
    //     }
    //
    //     if (all_neighbors_are_lawn)
    //     {
    //         cout <<"[exist]there are exist all_neighbors_are_lawn area..." <<endl;
    //     }
    // }


    // auto t1 = std::chrono::high_resolution_clock::now();
    // Mat disparity = stereo_multi_match.stereo_multi_process_depth(grayImageL, grayImageR);

    // Mat disparity_color = createColorMappedImage(disparity, COLORMAP_JET, "Disparity");
    // imwrite("disparity_color.jpg", disparity_color);
    // string dis_name = saveDisDirPath + name + "_color_dis.jpg";
    // imwrite(dis_name, disparity_color);

    // auto t2 = std::chrono::high_resolution_clock::now();
    // Mat depth_cal = stereo_multi_match.stereo_multi_process_filter(disparity, lab_dst, enable_height_filter_);
    Mat depth_cal = stereo_multi_match.stereo_multi_process(grayImageL, grayImageR, enable_height_filter_);

    // Mat depth_color = createColorMappedImage(depth_cal, COLORMAP_JET, "depth_cal");
    // string dep_name = saveDepDirPath + name + "_color_dep.jpg";


    // imwrite(dep_name, depth_color);
    // auto t3 = std::chrono::high_resolution_clock::now();
    //
    // auto t21 = std::chrono::duration_cast<std::chrono::microseconds>(t2-t1);
    // auto t32 = std::chrono::duration_cast<std::chrono::microseconds>(t3-t2);
    // auto t_whole = std::chrono::duration_cast<std::chrono::microseconds>(t3-t1);


    // // 转换为伪彩图并保存
    // Mat disp_norm, depth_norm;
    // normalize(disparity, disp_norm, 0, 255, NORM_MINMAX, CV_8UC1);
    // normalize(depth_cal, depth_norm, 0, 255, NORM_MINMAX, CV_8UC1);

    // Mat disp_color, depth_color;
    // applyColorMap(disp_norm, disp_color, COLORMAP_JET);
    // applyColorMap(depth_norm, depth_color, COLORMAP_VIRIDIS);

    // imwrite(dis_name, disp_color);
    // imwrite(dep_name, depth_color);

    // std::cout << "process_depth: " << t21.count() / 1000.0 << " ms" << std::endl;
    // std::cout << "depth_filter: " << t32.count() / 1000.0 << " ms" << std::endl;
    // std::cout << "t_whole: " << t_whole.count() / 1000.0 << " ms" << std::endl;


    pcl::PointCloud<pcl::PointXYZRGBL> xyz_rgbi_cloud = pcl::PointCloud<pcl::PointXYZRGBL>();
    pcl::PointCloud<pcl::PointXYZRGBL> out_xyz_rgbi_cloud = pcl::PointCloud<pcl::PointXYZRGBL>();
    stereo_multi_match.stereo_process_pci_depth_rgb_seg_det_fusion(depth_cal,lab_dst, dect_dst, croppedImg, xyz_rgbi_cloud,
                                                             out_xyz_rgbi_cloud);

    // // ========== 方案B：补充缺失点云 ==========
    // pcl::PointCloud<pcl::PointXYZRGBL> supplemented_cloud = pcl::PointCloud<pcl::PointXYZRGBL>();
    // stereo_multi_match.stereo_supplement_missing_points(depth_cal, lab_dst, croppedImg,
    //                                                     out_xyz_rgbi_cloud,
    //                                                     supplemented_cloud);
    // ========================================

    // ========== 关闭：生成无过滤版本的点云和三视图 ==========
    // pcl::PointCloud<pcl::PointXYZRGBL> no_filter_cloud = pcl::PointCloud<pcl::PointXYZRGBL>();
    // string no_filter_save_path = saveMultiDirPath + name;
    // stereo_multi_match.stereo_generate_pointcloud_no_filter(depth_cal, lab_dst, croppedImg,
    //                                                          no_filter_cloud, no_filter_save_path);
    // ========================================

    auto end = std::chrono::high_resolution_clock::now();  // 结束时间
    std::chrono::duration<double, std::milli> duration = end - start;  // 计算耗时（以毫秒为单位）

    //        savePcdfile_with_rgb_label(xyz_rgbi_cloud, oriPcdPath);
    // savePcdfile_with_rgb_label(supplemented_cloud, labelPcdPath);  // 使用补充后的点云
    // stereoPointCloud.show_xyz_rgbl_plane_point_cloud_final(supplemented_cloud, xyz_rgbl);  // 使用补充后的点云
    stereoPointCloud.show_xyz_rgbl_plane_point_cloud_final(out_xyz_rgbi_cloud, xyz_rgbl);  // 使用补充后的点云
    if (m_enable_debug_show) {
        Mat img_seg_show;
        Mat pure_seg_mat = drawResult(croppedImg, lab_dst, dect_dst, img_seg_show);
        Mat origin_seg;
        cv::resize(pure_seg_mat, pure_seg_mat, Size(640, 384));
        cv::resize(img_seg_show, img_seg_show, Size(640, 384));

        cv::hconcat(croppedImg, pure_seg_mat, origin_seg);  // 拼接图片1和图片2
        cv::hconcat(origin_seg, img_seg_show, origin_seg);  // 拼接图片1和图片2

        cv::vconcat(origin_seg, xyz_rgbl, final_compared); // 再将图片3拼接到结果中

        imwrite(finalPicPath, final_compared);
    }
    count_stereo++;
    std::unordered_map<uint32_t, size_t> label_count;
    for (const auto &point: out_xyz_rgbi_cloud) {
        label_count[point.label]++;
    }
    cout << "out_xyz_rgbi_cloud.size: " << out_xyz_rgbi_cloud.size() << endl;

    cout << "=====[dsg]back: " << label_count[1] << ", road:" << label_count[3] << ", stat:" << label_count[5] << "=======" << endl;
    // }
    dsgPerception.perception_release();

    return 0;
}

