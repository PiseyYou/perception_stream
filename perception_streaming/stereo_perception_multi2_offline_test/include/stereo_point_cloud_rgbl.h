#ifndef STEREO_POINT_CLOUD_RGBL_H
#define STEREO_POINT_CLOUD_RGBL_H

// 在包含任何库之前，先定义宏阻止 PCL 包含 FLANN 头文件
#define PCL_NO_FLANN

#include <iostream>
#include <opencv2/opencv.hpp>
#include <pcl/filters/passthrough.h>
#include <pcl/filters/statistical_outlier_removal.h>
#include <pcl/io/pcd_io.h>
#include <pcl/point_types.h>
// #include <pcl/visualization/pcl_visualizer.h>  // 离线测试不需要可视化
#include <pcl/common/common.h>
#include <pcl/console/parse.h>

using namespace std;
using namespace cv;

class stereo_point_cloud {
public:
  std::map<int, cv::Scalar> colorMap;
  std::map<int, std::string> mul_map_class;

  void initColorMap();
  void initMulClassMap();
  void
  stereo_xyz_rgbl_plane(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud,
                        Mat &xyz_rgb, Mat &xyz_l, Mat &xyz_rgbl);
  void show_xyz_rgbl_plane_point_cloud(
      pcl::PointCloud<pcl::PointXYZRGBL> xyz_rgbl_cloud, Mat &xyz_rgb,
      Mat &xyz_l, Mat &xyz_rgbl);

  void show_xyz_rgbl_plane_point_cloud_final(
      pcl::PointCloud<pcl::PointXYZRGBL> xyz_rgbl_cloud, Mat &xyz_rgbl);
  void stereo_xyz_rgbl_plane_final(
      pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud, Mat &xyz_rgbl);

private:
  cv::Mat getXView_l(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud);
  cv::Mat getYView_l(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud);
  cv::Mat getZView_l(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud);

  cv::Mat getXView_rgb(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud);
  cv::Mat getYView_rgb(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud);
  cv::Mat getZView_rgb(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud);
};

#endif // STEREO_POINT_CLOUD_RGBL_H
