#ifndef PCL_WRAPPER_H
#define PCL_WRAPPER_H

// 完全隔离 PCL 和 OpenCV 的 FLANN 冲突
// 策略: 先包含 OpenCV,然后用命名空间别名隔离 FLANN

// 1. 先包含 OpenCV 及其 FLANN
#include <opencv2/opencv.hpp>
#include <opencv2/flann.hpp>

// 2. 保存 cv::flann 命名空间
namespace cv_flann = cv::flann;

// 3. 取消 flann 宏定义(如果有)
#ifdef flann
#undef flann
#endif

// 4. 包含 PCL 头文件
#include <pcl/point_types.h>
#include <pcl/point_cloud.h>
#include <pcl/io/pcd_io.h>
#include <pcl/common/common.h>
#include <pcl/console/parse.h>
#include <pcl/filters/passthrough.h>
#include <pcl/filters/voxel_grid.h>

// 5. 尝试包含可能有问题的 filters (如果失败就注释掉)
// #include <pcl/filters/statistical_outlier_removal.h>
// #include <pcl/filters/radius_outlier_removal.h>

#endif // PCL_WRAPPER_H
