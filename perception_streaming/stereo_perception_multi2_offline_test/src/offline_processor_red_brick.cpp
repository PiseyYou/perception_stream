#include "offline_processor.hpp"
#include <opencv2/opencv.hpp>
#include <vector>
#include <algorithm>

/**
 * @brief 计算边缘直线度得分
 *
 * 使用 Canny 边缘检测和 Hough 直线检测来评估区域边缘的直线程度
 *
 * @param grayROI 灰度图 ROI
 * @param compMask 连通区域掩码
 * @return float 直线度得分 [0, 1]，越高表示边缘越直
 */
static float computeStraightEdgeScore(const cv::Mat& grayROI, const cv::Mat& compMask) {
    // 1. Canny 边缘检测
    cv::Mat edges;
    cv::Canny(grayROI, edges, 50, 150);
    edges &= compMask;  // 只保留连通区域内的边缘

    int total_edge_pixels = cv::countNonZero(edges);
    if (total_edge_pixels < 10) {
        return 0.0f;  // 边缘像素太少，无法判断
    }

    // 2. Hough 直线检测
    std::vector<cv::Vec4i> lines;
    cv::HoughLinesP(edges, lines, 1, CV_PI / 180, 15, 10, 5);
    if (lines.empty()) {
        return 0.0f;  // 没有检测到直线
    }

    // 3. 计算直线覆盖的边缘像素比例
    cv::Mat line_mask = cv::Mat::zeros(edges.size(), CV_8UC1);
    for (const auto& l : lines) {
        cv::line(line_mask, cv::Point(l[0], l[1]),
                 cv::Point(l[2], l[3]), 255, 2);
    }
    cv::Mat line_edge = line_mask & edges;
    int line_edge_pixels = cv::countNonZero(line_edge);

    // 返回直线边缘占总边缘的比例
    return static_cast<float>(line_edge_pixels) / static_cast<float>(total_edge_pixels);
}

void OfflineProcessor::refineObstacleByColorAndEdge(cv::Mat& label_map,
                                                     const cv::Mat& bgr_img,
                                                     int min_area) {
    if (label_map.empty() || bgr_img.empty())
        return;
    if (label_map.size() != bgr_img.size())
        return;

    const float min_edge_score = 0.20f;
    const float min_solidity = 0.50f;
    const float min_green_ratio = 0.50f;
    const int img_h = label_map.rows;
    const int img_w = label_map.cols;
    const int roi_y_top = static_cast<int>(img_h * 0.5);
    const int roi_y_bot = static_cast<int>(img_h * 0.9);

    cv::Mat blurred;
    cv::Mat hsv_img;
    cv::GaussianBlur(bgr_img, blurred, cv::Size(5, 5), 0);
    cv::cvtColor(blurred, hsv_img, cv::COLOR_BGR2HSV);

    cv::Mat green_mask;
    cv::inRange(hsv_img, cv::Scalar(25, 40, 40), cv::Scalar(85, 255, 255),
                green_mask);
    cv::Mat roi_green = green_mask(cv::Range(roi_y_top, roi_y_bot),
                                   cv::Range(0, img_w));
    const int green_pixels = cv::countNonZero(roi_green);
    const int total_roi_pixels = static_cast<int>(roi_green.total());
    const float green_ratio =
        total_roi_pixels > 0
            ? static_cast<float>(green_pixels) / total_roi_pixels
            : 0.0f;
    if (green_ratio < min_green_ratio)
        return;

    cv::Mat non_veg_mask;
    cv::inRange(hsv_img, cv::Scalar(15, 30, 40), cv::Scalar(85, 255, 255),
                non_veg_mask);
    cv::bitwise_not(non_veg_mask, non_veg_mask);

    cv::Mat hsv_channels[3];
    cv::split(hsv_img, hsv_channels);
    cv::Mat color_ok = (hsv_channels[1] > 25) | (hsv_channels[2] > 150);
    cv::Mat not_too_dark = hsv_channels[2] > 40;
    non_veg_mask &= color_ok;
    non_veg_mask &= not_too_dark;

    cv::Mat label_2_mask;
    cv::Mat label_3_mask;
    cv::compare(label_map, 2, label_2_mask, cv::CMP_EQ);
    cv::compare(label_map, 3, label_3_mask, cv::CMP_EQ);
    cv::Mat lawn_road_mask = label_2_mask | label_3_mask;
    non_veg_mask &= lawn_road_mask;

    non_veg_mask(cv::Range(0, roi_y_top), cv::Range(0, img_w)).setTo(0);
    non_veg_mask(cv::Range(roi_y_bot, img_h), cv::Range(0, img_w)).setTo(0);

    cv::Mat kernel_5x5 =
        cv::getStructuringElement(cv::MORPH_ELLIPSE, cv::Size(5, 5));
    cv::morphologyEx(non_veg_mask, non_veg_mask, cv::MORPH_OPEN, kernel_5x5);
    cv::morphologyEx(non_veg_mask, non_veg_mask, cv::MORPH_CLOSE, kernel_5x5);

    cv::Mat cc_labels;
    cv::Mat cc_stats;
    cv::Mat cc_centroids;
    int n_labels = cv::connectedComponentsWithStats(
        non_veg_mask, cc_labels, cc_stats, cc_centroids, 8, CV_32S);

    cv::Mat gray_img;
    cv::cvtColor(bgr_img, gray_img, cv::COLOR_BGR2GRAY);
    cv::Mat result_mask = cv::Mat::zeros(label_map.size(), CV_8UC1);

    for (int i = 1; i < n_labels; i++) {
        int area = cc_stats.at<int>(i, cv::CC_STAT_AREA);
        if (area < min_area)
            continue;

        int x = cc_stats.at<int>(i, cv::CC_STAT_LEFT);
        int y = cc_stats.at<int>(i, cv::CC_STAT_TOP);
        int w = cc_stats.at<int>(i, cv::CC_STAT_WIDTH);
        int h = cc_stats.at<int>(i, cv::CC_STAT_HEIGHT);

        cv::Rect roi_rect(x, y, w, h);
        cv::Mat comp_mask_roi = (cc_labels(roi_rect) == i);
        cv::Mat gray_roi = gray_img(roi_rect);

        float edge_score = computeStraightEdgeScore(gray_roi, comp_mask_roi);

        float solidity = 0.0f;
        std::vector<std::vector<cv::Point>> contours;
        cv::findContours(comp_mask_roi.clone(), contours, cv::RETR_EXTERNAL,
                         cv::CHAIN_APPROX_SIMPLE);
        if (!contours.empty()) {
            auto& contour = *std::max_element(
                contours.begin(), contours.end(),
                [](const auto& a, const auto& b) {
                    return cv::contourArea(a) < cv::contourArea(b);
                });
            double contour_area = cv::contourArea(contour);
            std::vector<cv::Point> hull;
            cv::convexHull(contour, hull);
            double hull_area = cv::contourArea(hull);
            if (hull_area > 0) {
                solidity = static_cast<float>(contour_area / hull_area);
            }
        }

        float eff_edge_thresh = min_edge_score;
        if (area > min_area * 5) {
            eff_edge_thresh *= 0.6f;
        }

        if (edge_score >= eff_edge_thresh && solidity >= min_solidity) {
            for (int py = y; py < y + h && py < cc_labels.rows; py++) {
                const int* label_row = cc_labels.ptr<int>(py);
                uchar* result_row = result_mask.ptr<uchar>(py);
                for (int px = x; px < x + w && px < cc_labels.cols; px++) {
                    if (label_row[px] == i)
                        result_row[px] = 255;
                }
            }
        }
    }

    label_map.setTo(5, result_mask);
}
