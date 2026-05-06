#ifndef STEREO_POINT_CLOUD_RGBL_H
#define STEREO_POINT_CLOUD_RGBL_H

// 使用 PCL 包装器来避免 FLANN 冲突
#include "pcl_wrapper.h"

#include <iostream>

// 注意: statistical_outlier_removal 依赖 kdtree,会引入 FLANN
// 如果需要使用,需要解决 FLANN 冲突
// #include <pcl/filters/statistical_outlier_removal.h>

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
