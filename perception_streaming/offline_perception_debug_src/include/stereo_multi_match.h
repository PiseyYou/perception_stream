// 在包含任何库之前，先定义宏阻止 PCL 包含 FLANN 头文件
#ifndef PCL_NO_FLANN
#define PCL_NO_FLANN
#endif

#include <iostream>
#include <vector>
#include <string>
#include <chrono>
#include <math.h>

// 先包含 OpenCV (包括 FLANN),确保 cv::flann 命名空间先被定义
#include <opencv2/opencv.hpp>
#include <opencv2/flann.hpp>

// 然后包含 PCL 头文件
#include <pcl/point_cloud.h>
#include <pcl/point_types.h>
// #include <pcl/visualization/pcl_visualizer.h>  // 离线测试不需要可视化
#include <pcl/filters/passthrough.h>
// #include <pcl/search/kdtree.h>  // 不需要，会引入 FLANN 依赖
// #include <pcl/segmentation/extract_clusters.h>  // 不需要
#include <pcl/filters/voxel_grid.h>
// #include <pcl/search/search.h>  // 不需要
// #include <pcl/memory.h>  // PCL 1.10 不需要此头文件

// OpenCV 头文件在 PCL 之后
#include "opencv2/calib3d.hpp"
#include "opencv2/imgproc.hpp"
#include "opencv2/highgui.hpp"
#include "opencv2/core/ocl.hpp"

#include "multiscale_filter.hpp"
#include <perception_common.h>

// 不在头文件中使用 using namespace，避免污染包含此头文件的所有文件
// using namespace std;
// using namespace cv;

class StereoMultiMatch
{
public:
    double cx, cy, fx, fy;
    cv::Mat Pl, Pr;
    cv::Mat P2, Q;
    bool match_enable_ces_show=false;

    cv::Mat depth_;
    cv::Mat disparity_;

    void stereo_multi_param_init();

    cv::Mat stereo_multi_process_depth(cv::Mat &rectifyL, cv::Mat &rectifyR);
    cv::Mat stereo_multi_process_filter(cv::Mat &disparity_, cv::Mat lab_dst, bool enable_height_filter_);

    cv::Mat stereo_multi_process(cv::Mat& rectifyL, cv::Mat& rectifyR, bool enable_height_filter_);

    void stereo_point_ori_rgb_filter(pcl::PointCloud<pcl::PointXYZRGBL> &xyz_rgbl_cloud, pcl::PointCloud<pcl::PointXYZRGBL> &out_xyz_rgbl_cloud);

    void stereo_process_pc_rgbl_depth(const cv::Mat &depth, cv::Mat &ori_mat, pcl::PointCloud<pcl::PointXYZRGBL> &xyz_rgbl_cloud, pcl::PointCloud<pcl::PointXYZRGBL> &out_xyz_rgbl_cloud);

    void stereo_process_pc_rgbl_dest(const cv::Mat &depth, cv::Mat &ori_mat, std::vector<Detection> &dect_src,
                                                       pcl::PointCloud<pcl::PointXYZRGBL> &xyz_rgbl_cloud, pcl::PointCloud<pcl::PointXYZRGBL> &out_xyz_rgbl_cloud);
    void stereo_process_pci_depth_rgb_seg_fusion(const cv::Mat &depth, const cv::Mat &lab, cv::Mat &ori_mat,
                                                                   pcl::PointCloud<pcl::PointXYZRGBL> &xyz_rgbl_cloud,
                                                                   pcl::PointCloud<pcl::PointXYZRGBL> &out_xyz_rgbl_cloud);
    void stereo_process_pci_depth_rgb_seg_det_fusion(const cv::Mat &depth, const cv::Mat &lab, std::vector<Detection> &dect_src, cv::Mat &ori_mat,
                                                                       pcl::PointCloud<pcl::PointXYZRGBL> &xyz_rgbl_cloud,
                                                                       pcl::PointCloud<pcl::PointXYZRGBL> &out_xyz_rgbl_cloud);
    void det_pc_rgb_label(Detection& det, const cv::Point& pt, pcl::PointXYZRGBL& pci);
    bool in_range(const cv::Point& top_left, const cv::Point& bottom_right, const cv::Point& pt_2d);

private:
    using Clock = std::chrono::high_resolution_clock;

    cv::Mat stereoImg;
    cv::Mat rgbImageL, rgbImageR;
    cv::Mat grayImageL, grayImageR;
    cv::Mat rectifyImageL, rectifyImageR;

    cv::Mat half_grayImageL, half_grayImageR;
    cv::Mat temp_grayImageL;

    bool use_background_substract_= false;
    bool use_multiscale_filter_= true;

    int intensity_low_ = 15;
    int intensity_high_ = 235;

    int bilateral_filter_kernel_size_= -1;
    double bilateral_filter_sigma_space_= 75.0;
    double bilateral_filter_sigma_color_= 75.0;
    int median_filter_kernel_size_= -1;

    int diff_threshold=2;
    int potential_threshold=6;
    int growing_window_size=5;
    int growing_threshold=2;
    int excessive_threshold=20;

    void stereo_block_matcher_init();
    void half_top_stereo_block_matcher_init();
    void half_bottom_stereo_block_matcher_init();
    void stereo_dis_init();

    void stereo_base_param_init();
    bool setStereoMatcherParameters(std::string dirPath);
    cv::Mat backgroundSubstract(const cv::Mat& src);


    // Variable
    cv::Ptr<cv::StereoBM> stereo_block_matcher_;
    cv::Ptr<cv::StereoBM> half_top_stereo_block_matcher_;
    cv::Ptr<cv::StereoSGBM> half_bottom_stereo_block_matcher_;
    cv::Mat disparity_16S_;

    cv::Mat disparity_half_16S_;
    cv::Mat disparity_half_;
    cv::Mat disparity_half_upscale_;
    cv::Mat intensity_mask_;
    cv::Mat disparity_valid_mask_;
    cv::Mat l_filtered_, r_filtered_;

    MultiScaleFilterParams orig_param_, half_param_;
};
