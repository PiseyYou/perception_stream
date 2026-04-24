#include <iostream>
#include <pcl/io/pcd_io.h>
#include <pcl/point_types.h>
#include <opencv2/opencv.hpp>
#include <pcl/visualization/pcl_visualizer.h>
#include <pcl/filters/statistical_outlier_removal.h>
#include <pcl/filters/passthrough.h>
//#include "perception_common.h"
#include <pcl/console/parse.h>
#include <pcl/point_types.h> //PCL中支持的点类型的头文件
#include <pcl/common/common.h>

using namespace std;
using namespace cv;

class stereo_point_cloud {
public:
    std::map<int, cv::Scalar> colorMap;
    void stereo_xyz_rgbl_plane(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr& xyz_rgbl_cloud, Mat &xyz_rgb,  Mat &xyz_l, Mat &xyz_rgbl);
    void show_xyz_rgbl_plane_point_cloud(pcl::PointCloud<pcl::PointXYZRGBL> xyz_rgbl_cloud, Mat &xyz_rgb,  Mat &xyz_l, Mat &xyz_rgbl);

    void show_xyz_rgbl_plane_point_cloud_final(pcl::PointCloud<pcl::PointXYZRGBL> xyz_rgbl_cloud, Mat &xyz_rgbl);
    void stereo_xyz_rgbl_plane_final(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr& xyz_rgbl_cloud, Mat &xyz_rgbl);
private:

    cv::Mat getXView_l(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud);
    cv::Mat getYView_l(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud);
    cv::Mat getZView_l(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud);

    cv::Mat getXView_rgb(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud);
    cv::Mat getYView_rgb(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud);
    cv::Mat getZView_rgb(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud);

};



