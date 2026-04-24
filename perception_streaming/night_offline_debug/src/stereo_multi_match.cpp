#include "stereo_multi_match.h"
#include <opencv2/highgui.hpp>
#include <pcl/filters/passthrough.h>
#include <pcl/filters/statistical_outlier_removal.h>
#include <pcl/filters/radius_outlier_removal.h>
#include <pcl/filters/voxel_grid.h>
#include <chrono>

#define VALID_HEIGHT 384

void StereoMultiMatch::stereo_base_param_init(){

    Pl = (cv::Mat_<double>(3, 4) <<  244.9567633,   0.,  321.05016538,   0.,
            0.000000000000000,  244.9567633, 234.44410892,   0.,
            0.0, 0.0, 1.0, 0.0);
    Pr = (cv::Mat_<double> (3, 4) << 244.9567633,   0.,  321.05016538,  -19.57480185,
            0.000000000000000, 244.9567633, 234.44410892,   0.,
            0.0, 0.0, 1.0, 0.0);

    cx = Pl.at<double>(0, 2);  // Principal point x
    cy = Pl.at<double>(1, 2);  // Principal point y
    fx = Pl.at<double>(0, 0);;  // Focal length x
    fy = Pl.at<double>(1, 1);;  // Focal length y
}


void StereoMultiMatch::stereo_dis_init(){
    disparity_16S_.create(cv::Size(640, 480), CV_16S);
//    disparity_32F_.create(cv::Size(640, 480), CV_32F);
    disparity_.create(cv::Size(640, 480), CV_32F);
    depth_.create(cv::Size(640, 480), CV_32F);
    disparity_valid_mask_.create(cv::Size(640, 480), CV_8U);
    intensity_mask_.create(cv::Size(640, 480), CV_8U);
}

void StereoMultiMatch::stereo_block_matcher_init(){
    stereo_block_matcher_ = cv::StereoBM::create();
    stereo_block_matcher_->setMinDisparity(0);
    stereo_block_matcher_->setNumDisparities(48);
    stereo_block_matcher_->setBlockSize(13);
    stereo_block_matcher_->setSpeckleWindowSize(64);
    stereo_block_matcher_->setSpeckleRange(16);
    stereo_block_matcher_->setDisp12MaxDiff(0);
    stereo_block_matcher_->setPreFilterType(1);
    stereo_block_matcher_->setPreFilterSize(15);
    stereo_block_matcher_->setPreFilterCap(31);
    stereo_block_matcher_->setTextureThreshold(5);
    stereo_block_matcher_->setUniquenessRatio(4);
}

void StereoMultiMatch::half_top_stereo_block_matcher_init(){
    half_top_stereo_block_matcher_ = cv::StereoBM::create();
    half_top_stereo_block_matcher_->setMinDisparity(0);
    half_top_stereo_block_matcher_->setNumDisparities(32);
    half_top_stereo_block_matcher_->setBlockSize(13);
    half_top_stereo_block_matcher_->setSpeckleWindowSize(80);
    half_top_stereo_block_matcher_->setSpeckleRange(2);
    half_top_stereo_block_matcher_->setDisp12MaxDiff(0);
    half_top_stereo_block_matcher_->setPreFilterType(1);
    half_top_stereo_block_matcher_->setPreFilterSize(15);
    half_top_stereo_block_matcher_->setPreFilterCap(31);
    half_top_stereo_block_matcher_->setTextureThreshold(10);
    half_top_stereo_block_matcher_->setUniquenessRatio(10);
}

void StereoMultiMatch::half_bottom_stereo_block_matcher_init(){
    half_bottom_stereo_block_matcher_ = cv::StereoSGBM::create();
    half_bottom_stereo_block_matcher_->setMinDisparity(0);
    half_bottom_stereo_block_matcher_->setNumDisparities(24);
    half_bottom_stereo_block_matcher_->setBlockSize(5);
    half_bottom_stereo_block_matcher_->setSpeckleWindowSize(64);
    half_bottom_stereo_block_matcher_->setSpeckleRange(16);
    half_bottom_stereo_block_matcher_->setDisp12MaxDiff(0);
    half_bottom_stereo_block_matcher_->setPreFilterCap(63);
    half_bottom_stereo_block_matcher_->setUniquenessRatio(20);
    half_bottom_stereo_block_matcher_->setP1(100);
    half_bottom_stereo_block_matcher_->setP2(500);
    half_bottom_stereo_block_matcher_->setMode(0);
}

void StereoMultiMatch::stereo_multi_param_init(){
    stereo_dis_init();
    stereo_base_param_init();
    stereo_block_matcher_init();
    if (use_multiscale_filter_) {
        half_top_stereo_block_matcher_init();
        half_bottom_stereo_block_matcher_init();
    }
//    orig_param_ = MultiScaleFilterParams(diff_threshold, potential_threshold,growing_window_size,
//                                         growing_threshold,excessive_threshold);
//
//    half_param_ = MultiScaleFilterParams(diff_threshold, potential_threshold,growing_window_size,
//                                         growing_threshold,excessive_threshold);

    orig_param_ = MultiScaleFilterParams(1.5, 4, 3, 1, 15);

    half_param_ = MultiScaleFilterParams(2.5, 8, 7, 3, 25);

}



cv::Mat StereoMultiMatch::backgroundSubstract(const cv::Mat& image) {
    cv::Mat gray_image;
    cv::Mat preprocessed_image;

    // Convert image to grayscale if it's a color image
    if (image.channels() == 3) {
        cv::cvtColor(image, gray_image, cv::COLOR_BGR2GRAY);
    }
    else {
        gray_image = image.clone(); // If already grayscale, use a copy
    }

    // Create large Gaussian kernel
    int kernel_size = 15;
    double sigma_large = 3;
    cv::Mat large_gaussian_blurred;

    // Apply Gaussian blur
    cv::GaussianBlur(gray_image, large_gaussian_blurred, cv::Size(kernel_size, kernel_size), sigma_large);

    // Background subtraction: Original image minus large Gaussian blurred image
    cv::Mat float_image, float_blurred, subtracted_image;
    gray_image.convertTo(float_image, CV_32F);
    large_gaussian_blurred.convertTo(float_blurred, CV_32F);

    cv::subtract(float_image, float_blurred, subtracted_image);

    // Normalize the result to full range [0, 255]
    cv::normalize(subtracted_image, preprocessed_image, 0, 255, cv::NORM_MINMAX);

    // Convert the image back to 8-bit
    preprocessed_image.convertTo(preprocessed_image, CV_8U);

    return preprocessed_image;
}


cv::Mat StereoMultiMatch::stereo_multi_process(cv::Mat& rectifyL, cv::Mat& rectifyR, bool enable_height_filter_) {
    if (rectifyL.empty() || rectifyR.empty()) {
        throw std::runtime_error("Input images are empty!");
    }
    if (rectifyL.size() != rectifyR.size()) {
        throw std::runtime_error("Input images have different sizes!");
    }

    const auto start = std::chrono::high_resolution_clock::now();
    const cv::Size orig_size = rectifyL.size();

    cv::Mat rectifyL_orig = rectifyL.clone();

    // 预处理图像
    cv::Mat rectifyL_processed, rectifyR_processed;

    // 根据配置选择不同预处理方式
    if (bilateral_filter_kernel_size_ > 0) {
        cv::bilateralFilter(rectifyL, rectifyL_processed,
                            bilateral_filter_kernel_size_,
                            bilateral_filter_sigma_color_,
                            bilateral_filter_sigma_space_);
        cv::bilateralFilter(rectifyR, rectifyR_processed,
                            bilateral_filter_kernel_size_,
                            bilateral_filter_sigma_color_,
                            bilateral_filter_sigma_space_);
    }
    else if (use_background_substract_) {
        rectifyL_processed = backgroundSubstract(rectifyL);
        rectifyR_processed = backgroundSubstract(rectifyR);
    }
    else {
        rectifyL.copyTo(rectifyL_processed);
        rectifyR.copyTo(rectifyR_processed);
    }

    // 降采样
    cv::pyrDown(rectifyL_processed, rectifyL_processed);
    cv::pyrDown(rectifyR_processed, rectifyR_processed);

    // 复用或调整缓冲区大小
    if (disparity_16S_.empty() || disparity_16S_.size() != rectifyL_processed.size())
        disparity_16S_.create(rectifyL_processed.size(), CV_16S);

    // 计算视差
    stereo_block_matcher_->compute(rectifyL_processed, rectifyR_processed, disparity_16S_);

    // 中值滤波
    if (median_filter_kernel_size_ > 0) {
        cv::medianBlur(disparity_16S_, disparity_16S_, median_filter_kernel_size_);
    }

    // 转换视差数据
    if (disparity_.empty() || disparity_.size() != disparity_16S_.size())
        disparity_.create(disparity_16S_.size(), CV_32F);
    disparity_16S_.convertTo(disparity_, CV_32F, 1.0f / 16.0f);

    // 多尺度处理或调整尺寸
    if (use_multiscale_filter_) {
        // 计算baseline: baseline = |Pr(0,3)| / fx
        double baseline = std::abs(Pr.at<double>(0, 3)) / fx;

        disparity_ = computeMultiScaleDisparity(half_top_stereo_block_matcher_,
                                                half_bottom_stereo_block_matcher_,
                                                rectifyL_processed, rectifyR_processed,
                                                disparity_, orig_param_, half_param_,
                                                cv::Mat(), fx, fy, cx, cy, baseline,
                                                enable_height_filter_);
    }
    else if (disparity_.size() != orig_size) {
        cv::resize(disparity_, disparity_, orig_size, 0, 0, cv::INTER_NEAREST);
    }

    // 创建 mask 缓冲区
    if (disparity_valid_mask_.empty() || disparity_valid_mask_.size() != disparity_.size())
        disparity_valid_mask_.create(disparity_.size(), CV_8U);
    disparity_valid_mask_ = (disparity_ > 0.01);

    if (intensity_mask_.empty() || intensity_mask_.size() != rectifyL_orig.size())
        intensity_mask_.create(rectifyL_orig.size(), CV_8U);
    intensity_mask_ = (rectifyL_orig >= intensity_low_) & (rectifyL_orig <= intensity_high_);

    // 合并有效区域
    disparity_valid_mask_ &= intensity_mask_;

    // 计算深度图
    static thread_local cv::Mat depth_; // 使用 thread_local 避免多线程冲突
    if (depth_.empty() || depth_.size() != disparity_.size()){
        depth_.release(); // 显式释放旧内容
        depth_.create(disparity_.size(), CV_32F);
    }

    double Bf = abs(Pr.at<double>(0, 3)); // baseline * focal length
    cv::divide(Bf, disparity_, depth_, 1, CV_32F); // 避免除零错误
    depth_.setTo(100.0f, ~disparity_valid_mask_);

    // cv::Mat filtered_depth;
    // cv::medianBlur(depth_, filtered_depth, 5); // 使用5x5窗口
    // depth_ = filtered_depth;

    // 应用形态学操作去除孤立点
    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(3, 3));
    cv::Mat opened_depth, closed_depth;

    // 开运算：先腐蚀后膨胀，去除小噪声点
    cv::morphologyEx(depth_, opened_depth, cv::MORPH_OPEN, kernel);
    // 闭运算：先膨胀后腐蚀，填补小孔洞
    cv::morphologyEx(opened_depth, closed_depth, cv::MORPH_CLOSE, kernel);
    depth_ = closed_depth;


    // 释放中间变量以减少内存占用
    rectifyL_processed.release();
    rectifyR_processed.release();

    return depth_.clone(); // 或者使用 std::move(depth_)
}

Mat StereoMultiMatch::stereo_multi_process_depth(Mat &rectifyL, Mat &rectifyR) {

    auto start = Clock::now();

    temp_grayImageL = rectifyL.clone();

    if (bilateral_filter_kernel_size_ > 0) {
        cv::bilateralFilter(rectifyL, l_filtered_,
                            bilateral_filter_kernel_size_,
                            bilateral_filter_sigma_color_,
                            bilateral_filter_sigma_space_);

        cv::bilateralFilter(rectifyR, r_filtered_,
                            bilateral_filter_kernel_size_,
                            bilateral_filter_sigma_color_,
                            bilateral_filter_sigma_space_);

        rectifyL = l_filtered_;
        rectifyR = r_filtered_;

    }
    else if (use_background_substract_) {
        rectifyL = backgroundSubstract(rectifyL);
        rectifyR = backgroundSubstract(rectifyR);
    }

    // To 320x240
    cv::pyrDown(rectifyL, half_grayImageL);
    cv::pyrDown(rectifyR, half_grayImageR);

    // Calculate disparity
    auto start_disparity = Clock::now();
    // cv::Mat disparity;
    stereo_block_matcher_->compute(half_grayImageL, half_grayImageR, disparity_16S_);

    if (median_filter_kernel_size_ > 0) {
        cv::medianBlur(disparity_16S_, disparity_16S_, median_filter_kernel_size_);
    }

    // Converting disparity values to CV_32F from CV_16S and scaling down
    disparity_16S_.convertTo(disparity_, CV_32F);
    disparity_ = (disparity_ / 16.0f);
    return disparity_;
}

Mat StereoMultiMatch::stereo_multi_process_filter(Mat &disparity_, cv::Mat lab_dst, bool enable_height_filter_){

    cv::Mat label_mask = create_label_mask(lab_dst, {1, 3, 5});
    cv::Mat padded_label_mask = cv::Mat::zeros(cv::Size(640, 480), CV_8UC1);
    label_mask.copyTo(padded_label_mask(cv::Rect(0, 0, 640, 384)));
    label_mask = padded_label_mask;

    if (use_multiscale_filter_) {
        // 计算baseline: baseline = |Pr(0,3)| / fx
        double baseline = std::abs(Pr.at<double>(0, 3)) / fx;

        disparity_ = computeMultiScaleDisparity(half_top_stereo_block_matcher_,
                                                half_bottom_stereo_block_matcher_,
                                                half_grayImageL, half_grayImageR, disparity_, orig_param_, half_param_,
                                                label_mask, fx, fy, cx, cy, baseline,
                                                enable_height_filter_);
    }
    else {
        cv::Size orig_size = temp_grayImageL.size(); // 640x480
        cv::resize(disparity_, disparity_, orig_size, 0, 0, cv::INTER_NEAREST);
    }

    // Convert to depth
    auto start_depth = Clock::now();
    // cv::Mat depth = cv::Mat::zeros(disparity_.size(), CV_32F);
    disparity_valid_mask_ = (disparity_ > 0.01); // Valid disparities

    intensity_mask_ = (temp_grayImageL >= intensity_low_) & (temp_grayImageL <= intensity_high_);
    disparity_valid_mask_ = disparity_valid_mask_ & intensity_mask_;

    double Bf = abs(Pr.at<double>(0, 3)); // baseline * focal length
    cv::divide(Bf, disparity_, depth_, CV_32F);
    depth_.setTo(100.0f, ~disparity_valid_mask_);

    double minVal, maxVal;
    cv::Mat depth_vis;

    // Max depth cutoff in visualization
    float MAX_DEPTH = 10.0;
    cv::Mat max_depth_mask = depth_ > MAX_DEPTH;
    depth_.setTo(MAX_DEPTH, max_depth_mask);

    cv::minMaxLoc(depth_, &minVal, &maxVal);
    return depth_;
}


cv::Mat StereoMultiMatch::create_label_mask(const cv::Mat& label_image, const std::vector<int>& labels)
{
    cv::Mat mask = cv::Mat::zeros(label_image.size(), CV_8UC1);
    for (int label : labels)
    {
        cv::Mat label_mask = (label_image == label);
        label_mask.convertTo(label_mask, CV_8UC1, 255);
        mask |= label_mask;
    }
    return mask;    
}

bool StereoMultiMatch::in_range(const cv::Point& top_left, const cv::Point& bottom_right, const cv::Point& pt_2d) {
    int u = pt_2d.x, v = pt_2d.y;
    if (u < top_left.x || v < top_left.y) return false;
    if (u > bottom_right.x || v > bottom_right.y) return false;
    return true;
}

void StereoMultiMatch::det_pc_rgb_label(Detection& det, const cv::Point& pt, pcl::PointXYZRGBL& pci) {
    Point left(det.bbox.xmin, det.bbox.ymin);
    Point right(det.bbox.xmax, det.bbox.ymax);
    if(in_range(left, right, pt)) {
        int temp_id = det.id+100;
        if(temp_id < 200) {
            pci.label = temp_id;
        }
    }
}

void StereoMultiMatch::stereo_process_pc_rgbl_depth(const Mat &depth, Mat &ori_mat, pcl::PointCloud<pcl::PointXYZRGBL> &xyz_rgbl_cloud, pcl::PointCloud<pcl::PointXYZRGBL> &out_xyz_rgbl_cloud){
//    for (int y = 0; y < depth_.rows; y+=2) {
    for (int y = 0; y < VALID_HEIGHT; y+=3) {
        for (int x = 0; x < depth.cols; x+=3) {
            float d = depth.at<float>(y, x);
            pcl::PointXYZRGBL pc_rgbl;
            if (d >= 0 && d < 6.0f) { // Valid depth
                pc_rgbl.x = (x - cx) * d / fx;
                pc_rgbl.y = (y - cy) * d / fy;
                pc_rgbl.z = d;
                Vec3b color = ori_mat.at<Vec3b>(y, x);
                uint8_t r = static_cast<uint8_t>(color[2]); // 红色分量
                uint8_t g = static_cast<uint8_t>(color[1]); // 绿色分量
                uint8_t b = static_cast<uint8_t>(color[0]); // 蓝色分量

                uint32_t rgb_packed = ((uint32_t)r << 16 | (uint32_t)g << 8 | (uint32_t)b);
                pc_rgbl.rgb = *reinterpret_cast<float*>(&rgb_packed);
//                pc_rgbl.label = (int) lab.at<uchar>(y, x);

                pc_rgbl.label = 2;
                if(pc_rgbl.label<=0 ||pc_rgbl.label>200) continue;
                xyz_rgbl_cloud.push_back(pc_rgbl);
            }
        }
    }

    stereo_point_ori_rgb_filter(xyz_rgbl_cloud, out_xyz_rgbl_cloud);

    out_xyz_rgbl_cloud.height = 1;
    out_xyz_rgbl_cloud.width = out_xyz_rgbl_cloud.points.size();
    out_xyz_rgbl_cloud.points.resize(out_xyz_rgbl_cloud.width * out_xyz_rgbl_cloud.height);
//    cout << "point xyzi_cloud size = " << xyzi_cloud.points.size() << endl;
}


void StereoMultiMatch::stereo_process_pc_rgbl_dest(const Mat &depth, Mat &ori_mat, std::vector<Detection> &dect_src,
                                                   pcl::PointCloud<pcl::PointXYZRGBL> &xyz_rgbl_cloud, pcl::PointCloud<pcl::PointXYZRGBL> &out_xyz_rgbl_cloud){
    for (int y = 0; y < VALID_HEIGHT; y+=3) {
        for (int x = 0; x < depth.cols; x+=3) {
            float d = depth.at<float>(y, x);
            pcl::PointXYZRGBL pc_rgbl;
            if (d >= 0 && d < 6.0f) { // Valid depth
                pc_rgbl.x = (x - cx) * d / fx;
                pc_rgbl.y = (y - cy) * d / fy;
                pc_rgbl.z = d;

                Vec3b color = ori_mat.at<Vec3b>(y, x);
                uint8_t r = static_cast<uint8_t>(color[2]);  // 红色分量
                uint8_t g = static_cast<uint8_t>(color[1]);  // 绿色分量
                uint8_t b = static_cast<uint8_t>(color[0]);  // 蓝色分量

                uint32_t rgb_packed = ((uint32_t)r << 16 | (uint32_t)g << 8 | (uint32_t)b);
                pc_rgbl.rgb = *reinterpret_cast<float*>(&rgb_packed);
                pc_rgbl.label = 2;
                if(pc_rgbl.label<=0 ||pc_rgbl.label>200) continue;
                for (int i = 0; i < dect_src.size(); i++) {
                    det_pc_rgb_label(dect_src[i], cv::Point(x, y), pc_rgbl);
                }
                xyz_rgbl_cloud.push_back(pc_rgbl);
            }
        }
    }

    stereo_point_ori_rgb_filter(xyz_rgbl_cloud, out_xyz_rgbl_cloud);

    out_xyz_rgbl_cloud.height = 1;
    out_xyz_rgbl_cloud.width = out_xyz_rgbl_cloud.points.size();
    out_xyz_rgbl_cloud.points.resize(out_xyz_rgbl_cloud.width * out_xyz_rgbl_cloud.height);
}

void StereoMultiMatch::stereo_process_pci_depth_rgb_seg_fusion(const Mat &depth, const Mat &lab, Mat &ori_mat,
                                                               pcl::PointCloud<pcl::PointXYZRGBL> &xyz_rgbl_cloud,
                                                               pcl::PointCloud<pcl::PointXYZRGBL> &out_xyz_rgbl_cloud){
    for (int y = 0; y < VALID_HEIGHT; y+=4) {
        for (int x = 0; x < depth.cols; x+=4) {
            float d = depth.at<float>(y, x);
            pcl::PointXYZRGBL pc_rgbl;
            if (d > 0 && d < 6.0f) { // Valid depth
                pc_rgbl.x = (x - cx) * d / fx;
                pc_rgbl.y = (y - cy) * d / fy;
                pc_rgbl.z = d;

                Vec3b color = ori_mat.at<Vec3b>(y, x);
                uint8_t r = static_cast<uint8_t>(color[2]);  // 红色分量
                uint8_t g = static_cast<uint8_t>(color[1]);  // 绿色分量
                uint8_t b = static_cast<uint8_t>(color[0]);  // 蓝色分量

                uint32_t rgb_packed = ((uint32_t)r << 16 | (uint32_t)g << 8 | (uint32_t)b);
                pc_rgbl.rgb = *reinterpret_cast<float*>(&rgb_packed);
                pc_rgbl.label = (int) lab.at<uchar>(y, x);
                if(pc_rgbl.label<=0 ||pc_rgbl.label>200) continue;
                xyz_rgbl_cloud.push_back(pc_rgbl);
            }
        }
    }

    stereo_point_ori_rgb_filter(xyz_rgbl_cloud, out_xyz_rgbl_cloud);

    out_xyz_rgbl_cloud.height = 1;
    out_xyz_rgbl_cloud.width = out_xyz_rgbl_cloud.points.size();
    out_xyz_rgbl_cloud.points.resize(out_xyz_rgbl_cloud.width * out_xyz_rgbl_cloud.height);
};


void StereoMultiMatch::stereo_process_pci_depth_rgb_seg_det_fusion(const Mat &depth, const Mat &lab, std::vector<Detection> &dect_src, Mat &ori_mat,
                                                                   pcl::PointCloud<pcl::PointXYZRGBL> &xyz_rgbl_cloud,
                                                                   pcl::PointCloud<pcl::PointXYZRGBL> &out_xyz_rgbl_cloud){
    for (int y = 0; y < VALID_HEIGHT; y+=3) {
        for (int x = 0; x < depth.cols; x+=3) {
            float d = depth.at<float>(y, x);
            pcl::PointXYZRGBL pc_rgbl;
            if (d > 0 && d < 6.0f) { // Valid depth
                pc_rgbl.x = (x - cx) * d / fx;
                pc_rgbl.y = (y - cy) * d / fy;
                pc_rgbl.z = d;

                Vec3b color = ori_mat.at<Vec3b>(y, x);
                uint8_t r = static_cast<uint8_t>(color[2]);  // 红色分量
                uint8_t g = static_cast<uint8_t>(color[1]);  // 绿色分量
                uint8_t b = static_cast<uint8_t>(color[0]);  // 蓝色分量

                uint32_t rgb_packed = ((uint32_t)r << 16 | (uint32_t)g << 8 | (uint32_t)b);
                pc_rgbl.rgb = *reinterpret_cast<float*>(&rgb_packed);
                pc_rgbl.label = lab.at<uchar>(y, x);
                if(pc_rgbl.label<=0 ||pc_rgbl.label>200) continue;
                xyz_rgbl_cloud.push_back(pc_rgbl);
            }
        }
    }


    stereo_point_ori_rgb_filter(xyz_rgbl_cloud, out_xyz_rgbl_cloud);

    out_xyz_rgbl_cloud.height = 1;
    out_xyz_rgbl_cloud.width = out_xyz_rgbl_cloud.points.size();
    out_xyz_rgbl_cloud.points.resize(out_xyz_rgbl_cloud.width * out_xyz_rgbl_cloud.height);
}


void StereoMultiMatch::stereo_point_ori_rgb_filter(pcl::PointCloud<pcl::PointXYZRGBL> &xyz_rgbl_cloud, pcl::PointCloud<pcl::PointXYZRGBL> &out_xyz_rgbl_cloud) {
    pcl::PointCloud<pcl::PointXYZRGBL>::Ptr input_cloud = std::make_shared<pcl::PointCloud<pcl::PointXYZRGBL>>(xyz_rgbl_cloud);
    pcl::PointCloud<pcl::PointXYZRGBL>::Ptr output_cloud(new pcl::PointCloud<pcl::PointXYZRGBL>());

    if (input_cloud->empty()) {
//        RCLCPP_WARN(rclcpp::get_logger("StereoMultiMatch"), "Input cloud is empty, nothing to filter.");
        cout << "Input cloud is empty, nothing to filter." << endl;
        out_xyz_rgbl_cloud.clear();
        return;
    }

//    auto y_start = std::chrono::high_resolution_clock::now();  // 开始时间
    pcl::PassThrough<pcl::PointXYZRGBL> pass;
    pass.setInputCloud(input_cloud);            // 设置输入点云
    pass.setFilterFieldName("y");                // 设置过滤时所需要点云类型的Y字段
    pass.setFilterLimits(-3.0, 0.5);             // 设置在过滤字段的范围
    pass.setNegative(false);
    pass.filter(*output_cloud);                  // 执行滤波

//    auto y_end = std::chrono::high_resolution_clock::now();  // 结束时间
//    std::chrono::duration<double, std::milli> y_duration = y_end - y_start;  // 计算耗时（以毫秒为单位）
//    RCLCPP_INFO(rclcpp::get_logger("StereoMultiMatch"), "Y-axis PassThrough executed in: %.2f ms.", y_duration.count());
//    cout << "Y-axis PassThrough executed in: " << y_duration.count() << " ms." << endl;

//    auto z_start = std::chrono::high_resolution_clock::now();  // 开始时间
    pcl::PassThrough<pcl::PointXYZRGBL> pass2;
    pass2.setInputCloud(output_cloud);           // 设置输入点云
    pass2.setFilterFieldName("z");               // 设置过滤时所需要点云类型的Z字段
    pass2.setFilterLimits(0.0, 5.0);             // 设置在过滤字段的范围
    pass2.setNegative(false);
    pass2.filter(*output_cloud);

//    auto z_end = std::chrono::high_resolution_clock::now();  // 结束时间
//    std::chrono::duration<double, std::milli> z_duration = z_end - z_start;  // 计算耗时（以毫秒为单位）
//    RCLCPP_INFO(rclcpp::get_logger("StereoMultiMatch"), "Z-axis PassThrough executed in: %.2f ms.", z_duration.count());
//    cout<< "Z-axis PassThrough executed in: " << z_duration.count() << " ms." << endl;
    if (match_enable_ces_show)
    {
        cout << "[噪点过滤] match_enable_ces_show=true, 开始执行过滤..." << endl;
        // ========== 离群点过滤（组合优化版-方案4）==========
        auto filter_start = std::chrono::high_resolution_clock::now();

        int points_before_filter = output_cloud->size();
        int points_after_voxel = 0;
        int points_after_ror = 0;
        int points_after_label = 0;

        // 步骤1：VoxelGrid快速降采样（CPU友好，大幅减少点数）
        pcl::VoxelGrid<pcl::PointXYZRGBL> vg;
        vg.setInputCloud(output_cloud);
        vg.setLeafSize(0.025f, 0.025f, 0.025f);  // 2.5cm体素
        pcl::PointCloud<pcl::PointXYZRGBL>::Ptr downsampled(new pcl::PointCloud<pcl::PointXYZRGBL>);
        vg.filter(*downsampled);
        points_after_voxel = downsampled->size();

        // 步骤2：在降采样点云上做轻量级离群点移除（参数降低以适应降采样后的点云密度）
        pcl::RadiusOutlierRemoval<pcl::PointXYZRGBL> ror;
        ror.setInputCloud(downsampled);
        ror.setRadiusSearch(0.08);              // 降低搜索半径到8cm（降采样后密度降低）
        ror.setMinNeighborsInRadius(6);         // 降低邻居数到6（降采样后邻居少）
        ror.filter(*output_cloud);
        points_after_ror = output_cloud->size();

        // 步骤3：利用分割信息过滤（排除背景和未知标签）
        pcl::PointCloud<pcl::PointXYZRGBL>::Ptr label_filtered(new pcl::PointCloud<pcl::PointXYZRGBL>);
        label_filtered->reserve(output_cloud->size());
        for (const auto& pt : output_cloud->points) {
            if (pt.label > 0 && pt.label <= 200) {  // 保留有效标签（排除0=未知, 1=背景）
                label_filtered->push_back(pt);
            }
        }
        *output_cloud = *label_filtered;
        points_after_label = output_cloud->size();

        auto filter_end = std::chrono::high_resolution_clock::now();
        std::chrono::duration<double, std::milli> filter_duration = filter_end - filter_start;

        // 打印过滤统计信息
        if (points_before_filter > 0) {
            cout << "[离群点过滤-组合优化版v4]" << endl;
            cout << "  原始点数: " << points_before_filter << endl;
            cout << "  VoxelGrid降采样后: " << points_after_voxel
                 << " (-" << (points_before_filter - points_after_voxel)
                 << ", " << (100.0 * (points_before_filter - points_after_voxel) / points_before_filter) << "%)" << endl;
            cout << "  离群点移除后: " << points_after_ror
                 << " (-" << (points_after_voxel - points_after_ror)
                 << ", " << (100.0 * (points_after_voxel - points_after_ror) / points_after_voxel) << "%)" << endl;
            cout << "  Label过滤后: " << points_after_label
                 << " (-" << (points_after_ror - points_after_label)
                 << ", " << (100.0 * (points_after_ror - points_after_label) / points_after_ror) << "%)" << endl;
            cout << "  总移除: " << (points_before_filter - points_after_label)
                 << " (" << (100.0 * (points_before_filter - points_after_label) / points_before_filter) << "%)" << endl;
            cout << "  过滤耗时: " << filter_duration.count() << " ms" << endl;
        }
        // ========================================
    }

    output_cloud->width = output_cloud->points.size();
    output_cloud->height = 1;
    output_cloud->is_dense = true;

    out_xyz_rgbl_cloud = *output_cloud;
}


// ========== 新增：基于分割图补充缺失点云的函数 ==========
void StereoMultiMatch::stereo_supplement_missing_points(
    const Mat &depth, const Mat &lab, Mat &ori_mat,
    pcl::PointCloud<pcl::PointXYZRGBL> &existing_cloud,
    pcl::PointCloud<pcl::PointXYZRGBL> &supplemented_cloud)
{
    // 先复制已有点云
    supplemented_cloud = existing_cloud;
    int original_size = existing_cloud.size();

    // 创建已有点云的2D投影掩码（标记哪些像素已经有点云）
    cv::Mat coverage_mask = cv::Mat::zeros(depth.size(), CV_8U);

    // 遍历已有点云，标记覆盖区域
    for (const auto& pt : existing_cloud.points) {
        // 将3D点投影回2D图像坐标
        int u = static_cast<int>(std::round(pt.x * fx / pt.z + cx));
        int v = static_cast<int>(std::round(pt.y * fy / pt.z + cy));  // 正Y坐标

        if (u >= 0 && u < depth.cols && v >= 0 && v < depth.rows) {
            coverage_mask.at<uchar>(v, u) = 255;
        }
    }

    // 统计信息
    int missing_pixels = 0;
    int supplemented_count = 0;
    std::map<int, int> supplemented_labels;

    // 获取深度图尺寸
    int depth_height = depth.rows;
    int depth_width = depth.cols;
    int sample_height = std::min(depth_height, VALID_HEIGHT);

    // 遍历图像，补充缺失的点
    for (int y = 0; y < sample_height; y++) {
        for (int x = 0; x < depth_width; x++) {
            float d = depth.at<float>(y, x);
            uchar label_val = lab.at<uchar>(y, x);

            // 检查该像素是否：1) 有有效深度 2) 未被覆盖 3) 有有效标签
            if (d > 0 && d < 6.0f && coverage_mask.at<uchar>(y, x) == 0) {
                // ⚠️ 补充策略：补充所有非背景标签 (label != 0 && label != 1)
                // 底部区域 (y>300) 也补充background点 (label==1)
                bool is_bottom_region = (y > 300);
                bool should_supplement = (label_val != 0 && label_val != 1) ||
                                        (is_bottom_region && label_val == 1);

                if (should_supplement) {
                    missing_pixels++;

                    pcl::PointXYZRGBL pc_rgbl;

                    // 计算3D坐标（与主函数保持一致：正Y坐标）
                    pc_rgbl.x = (x - cx) * d / fx;
                    pc_rgbl.y = (y - cy) * d / fy;
                    pc_rgbl.z = d;

                    // ⚠️ 限制Y值范围，避免引入噪音
                    // Y坐标范围：-3.0（上方/天空）到 0.5（接近地面）
                    if (pc_rgbl.y >= -3.0 && pc_rgbl.y <= 0.5) {
                        // 获取RGB颜色
                        if (y < ori_mat.rows && x < ori_mat.cols) {
                            Vec3b color = ori_mat.at<Vec3b>(y, x);
                            uint8_t r = static_cast<uint8_t>(color[2]);
                            uint8_t g = static_cast<uint8_t>(color[1]);
                            uint8_t b = static_cast<uint8_t>(color[0]);

                            uint32_t rgb_packed = ((uint32_t)r << 16 | (uint32_t)g << 8 | (uint32_t)b);
                            pc_rgbl.rgb = *reinterpret_cast<float*>(&rgb_packed);
                            pc_rgbl.label = label_val;

                            supplemented_cloud.push_back(pc_rgbl);
                            supplemented_count++;
                            supplemented_labels[label_val]++;
                        }
                    }
                }
            }
        }
    }

    // 更新点云属性
    supplemented_cloud.height = 1;
    supplemented_cloud.width = supplemented_cloud.size();

    // 简化输出统计信息
    cout << "\n[补充点云] 原始: " << original_size
         << " | 补充: " << supplemented_count
         << " | 总计: " << supplemented_cloud.size() << endl;
}