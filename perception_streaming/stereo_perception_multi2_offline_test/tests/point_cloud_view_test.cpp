#include "stereo_point_cloud_rgbl.h"

#include <opencv2/opencv.hpp>
#include <pcl/point_cloud.h>
#include <pcl/point_types.h>

#include <iostream>

namespace {

pcl::PointXYZRGBL makePoint(float x, float y, float z, std::uint32_t label) {
    pcl::PointXYZRGBL point;
    point.x = x;
    point.y = y;
    point.z = z;
    point.label = label;
    return point;
}

bool expectPixel(const cv::Mat& image,
                 int row,
                 int col,
                 const cv::Vec3b& expected,
                 const char* message) {
    const cv::Vec3b actual = image.at<cv::Vec3b>(row, col);
    if (actual == expected) {
        return true;
    }

    std::cerr << message << ": expected BGR("
              << static_cast<int>(expected[0]) << ", "
              << static_cast<int>(expected[1]) << ", "
              << static_cast<int>(expected[2]) << "), got BGR("
              << static_cast<int>(actual[0]) << ", "
              << static_cast<int>(actual[1]) << ", "
              << static_cast<int>(actual[2]) << ")\n";
    return false;
}

}  // namespace

int main() {
    pcl::PointCloud<pcl::PointXYZRGBL> cloud;
    cloud.points.push_back(makePoint(-1.0f, 0.0f, 0.0f, 1));
    cloud.points.push_back(makePoint(1.0f, 0.0f, 2.0f, 1));
    cloud.points.push_back(makePoint(0.0f, 0.0f, 1.0f, 6));
    cloud.points.push_back(makePoint(0.0f, 0.1f, 1.0f, 2));
    cloud.width = static_cast<std::uint32_t>(cloud.points.size());
    cloud.height = 1;
    cloud.is_dense = true;

    stereo_point_cloud viewer;
    cv::Mat xyz_rgbl;
    viewer.show_xyz_rgbl_plane_point_cloud_final(cloud, xyz_rgbl);

    const int yview_col_offset = 640;
    const int projected_row = 240;
    const int projected_col = yview_col_offset + 320;
    const cv::Vec3b wall_obstacle_bgr(0, 165, 255);

    return expectPixel(xyz_rgbl, projected_row, projected_col, wall_obstacle_bgr,
                       "YView_l should draw obstacle labels above grass labels")
               ? 0
               : 1;
}
