#include "offline_processor.hpp"
#include "semantic_depth_utils.hpp"
#include <algorithm>
#include <vector>

/**
 * @brief 基于检测框的深度补全
 *
 * 对检测框区域内的无效深度进行补全，使用边界深度的中值填充
 *
 * @param depth 输入深度图
 * @param label 标签图
 * @param detections 检测框列表
 * @return 补全后的深度图
 */
cv::Mat OfflineProcessor::depthInpaintingByDetections(
    const cv::Mat& depth,
    const cv::Mat& label,
    const std::vector<Detection>& detections) {

    if (depth.empty() || label.empty() || depth.size() != label.size()) {
        return depth.clone();
    }

    cv::Mat depth_inpainted = depth.clone();

    std::vector<float> valid_depths;
    std::vector<float> boundary_depths;

    for (size_t i = 0; i < detections.size(); i++) {
        const Detection& det = detections[i];

        if (det.id != 4) continue;

        int xmin = std::max(0, static_cast<int>(det.bbox.xmin));
        int ymin = std::max(0, static_cast<int>(det.bbox.ymin));
        int xmax = std::min(depth.cols, static_cast<int>(det.bbox.xmax));
        int ymax = std::min(depth.rows, static_cast<int>(det.bbox.ymax));

        if (xmax <= xmin || ymax <= ymin) continue;

        int bbox_area = (xmax - xmin) * (ymax - ymin);
        int total_pixels = bbox_area;
        int invalid_depth_pixels = 0;

        valid_depths.clear();
        valid_depths.reserve(bbox_area);

        for (int y = ymin; y < ymax; y++) {
            const float* depth_row = depth.ptr<float>(y);
            for (int x = xmin; x < xmax; x++) {
                float d = depth_row[x];
                if (d > 0 && d < 9.5f) {
                    valid_depths.push_back(d);
                } else {
                    invalid_depth_pixels++;
                }
            }
        }

        // 如果无效深度比例超过20%，进行补全
        if (invalid_depth_pixels > total_pixels * 0.2f) {
            int boundary_width = 10;
            int bx0 = std::max(0, xmin - boundary_width);
            int bx1 = std::min(depth.cols, xmax + boundary_width);
            int by0 = std::max(0, ymin - boundary_width);
            int by1 = std::min(depth.rows, ymax + boundary_width);

            boundary_depths.clear();
            int boundary_perimeter = 2 * ((bx1 - bx0) + (by1 - by0)) * boundary_width;
            boundary_depths.reserve(boundary_perimeter);

            for (int y = by0; y < by1; y++) {
                const float* depth_row = depth.ptr<float>(y);
                for (int x = bx0; x < bx1; x++) {
                    if (y < ymin || y >= ymax || x < xmin || x >= xmax) {
                        float d = depth_row[x];
                        if (d > 0 && d < 9.5f) {
                            boundary_depths.push_back(d);
                        }
                    }
                }
            }

            // 计算填充深度值
            float fill_depth = 0;
            if (!boundary_depths.empty()) {
                auto mid = boundary_depths.begin() + boundary_depths.size() / 2;
                std::nth_element(boundary_depths.begin(), mid, boundary_depths.end());
                fill_depth = *mid;
            } else if (!valid_depths.empty()) {
                auto mid = valid_depths.begin() + valid_depths.size() / 2;
                std::nth_element(valid_depths.begin(), mid, valid_depths.end());
                fill_depth = *mid;
            }

            if (fill_depth > 0) {
                for (int y = ymin; y < ymax; y++) {
                    const uchar* label_row = label.ptr<uchar>(y);
                    float* inpaint_row = depth_inpainted.ptr<float>(y);
                    for (int x = xmin; x < xmax; x++) {
                        if (label_row[x] == 104) {
                            float d = inpaint_row[x];
                            if (d <= 0 || d >= 9.5f) {
                                inpaint_row[x] = fill_depth;
                            }
                        }
                    }
                }
            }
        }
    }

    return depth_inpainted;
}

/**
 * @brief 基于语义分割的深度补全
 *
 * 对障碍物区域（label >= 100 或 label == 4/5）的无效深度进行补全
 *
 * @param depth 输入深度图
 * @param label 标签图
 * @return 补全后的深度图
 */
cv::Mat OfflineProcessor::depthInpaintingForObstacles(
    const cv::Mat& depth,
    const cv::Mat& label) {

    if (depth.empty() || label.empty() || depth.size() != label.size()) {
        return depth.clone();
    }

    cv::Mat protected_label = cv::Mat::zeros(label.size(), label.type());
    const int min_y = label.rows * 3 / 5;
    for (int y = min_y; y < label.rows; ++y) {
        const uchar* label_row = label.ptr<uchar>(y);
        uchar* protected_row = protected_label.ptr<uchar>(y);
        for (int x = 0; x < label.cols; ++x) {
            if (isBottomSemanticRepairRegion(label.cols, label.rows, x, y) &&
                isSemanticObstacleLabel(label_row[x])) {
                protected_row[x] = label_row[x];
            }
        }
    }

    return inpaintSemanticObstacleDepth(depth, protected_label);
}
