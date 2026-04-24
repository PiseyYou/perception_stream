#include "multiscale_filter.hpp"

#include <chrono>
#include <opencv2/core.hpp>
#include <opencv2/core/mat.hpp>
#include <opencv2/core/types.hpp>
#include <opencv2/highgui.hpp>
#include <opencv2/imgproc.hpp>
using Clock = std::chrono::high_resolution_clock;

// BFS connected component analysis
std::pair<std::vector<cv::Point>, cv::Mat> bfsMarkConnected(
    const cv::Mat& disparity,
    int start_y,
    int start_x,
    cv::Mat& visited,
    float max_diff = 5
) {
    const int height = disparity.rows;
    const int width = disparity.cols;
    std::deque<cv::Point> points_queue;
    std::vector<cv::Point> connected_points;
    points_queue.push_back(cv::Point(start_x, start_y));

    const float center_value = disparity.at<float>(start_y, start_x);

    // 8-connectivity directions
    const int dx[] = { -1, -1, -1, 0, 0, 1, 1, 1 };
    const int dy[] = { -1, 0, 1, -1, 1, -1, 0, 1 };

    while (!points_queue.empty()) {
        cv::Point current = points_queue.front();
        points_queue.pop_front();

        if (visited.at<uchar>(current.y, current.x)) {
            continue;
        }

        visited.at<uchar>(current.y, current.x) = 1;
        connected_points.push_back(current);

        for (int dir = 0; dir < 8; ++dir) {
            int new_y = current.y + dy[dir];
            int new_x = current.x + dx[dir];

            if (new_y >= 0 && new_y < height &&
                new_x >= 0 && new_x < width &&
                !visited.at<uchar>(new_y, new_x)) {

                float val = disparity.at<float>(new_y, new_x);
                if (!std::isnan(val) && std::abs(val - center_value) < max_diff) {
                    points_queue.push_back(cv::Point(new_x, new_y));
                }
            }
        }
    }

    return { connected_points, visited };
}

cv::Mat smallRegionHighDisparityFilter(
    const cv::Mat& disparity,
    float disp_threshold = 50,
    int area_threshold = 200,
    cv::Mat obstacle_mask
) {
    // Create binary mask for high disparity regions
    cv::Mat high_disp_mask = disparity > disp_threshold;

    // Find contours
    std::vector<std::vector<cv::Point>> contours;
    std::vector<cv::Vec4i> hierarchy;
    cv::findContours(high_disp_mask, contours, hierarchy,
        cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);

    // Create output mask
    cv::Mat noise_filter_mask = cv::Mat::zeros(disparity.size(), CV_8U);

    // 统计信息（用于调试）
    int total_contours = contours.size();
    int filtered_contours = 0;
    int kept_by_adaptive = 0;
    int kept_by_label_check = 0;  // 新增：被标签检查保留的区域数

    // Fill small regions with adaptive threshold
    for (const auto& contour : contours) {
        float area = cv::contourArea(contour);

        // ========== 自适应面积阈值 ==========
        // 计算该区域的平均视差
        cv::Mat contour_mask = cv::Mat::zeros(disparity.size(), CV_8U);
        cv::drawContours(contour_mask, std::vector<std::vector<cv::Point>>{contour}, 0, 255, cv::FILLED);
        cv::Scalar mean_scalar = cv::mean(disparity, contour_mask);
        float mean_disp = mean_scalar[0];

        // 根据视差值动态调整面积阈值
        // 修改策略：底部区域(视差15-30)更宽松，避免过滤掉草地/道路点云
        float adaptive_threshold;
        if (mean_disp > 40) {
            // 非常近的距离（视差>40）：降低到20%（更激进）
            adaptive_threshold = area_threshold * 0.2;
        } else if (mean_disp > 30) {
            // 近距离（视差>30）：降低到40%（稍微放宽）
            adaptive_threshold = area_threshold * 0.4;
        } else if (mean_disp > 15) {
            // ⚠️ 关键修改：底部区域（视差15-30），使用更宽松的阈值
            // 这个范围通常对应1-2米的草地/道路区域
            adaptive_threshold = area_threshold * 1.2;  // 允许比原阈值还大20%
        } else {
            // 远距离：保持原阈值
            adaptive_threshold = area_threshold;
        }
        // ====================================

        // 调试输出：第一次调用时打印所有区域信息
        // static bool first_debug = true;
        // if (first_debug && total_contours > 0) {
        //     std::cout << "  [区域" << (&contour - &contours[0]) << "] 面积=" << area
        //              << ", 平均视差=" << mean_disp
        //              << ", 自适应阈值=" << adaptive_threshold << std::endl;
        // }

        if (area < adaptive_threshold) {
            // Check label mask
            if (!obstacle_mask.empty()) {
                int label_area = cv::countNonZero(contour_mask & obstacle_mask);
                if (label_area > 0.5 * area) {
                    // Optional: remove non obstacle area
                    // cv::Mat component_non_obstacle_mask = contour_mask & ~obstacle_mask;
                    // noise_filter_mask |= component_non_obstacle_mask;
                    kept_by_label_check++;
                    // if (first_debug) {
                    //     std::cout << "    -> 标签检查保留 (obstacle占比="
                    //              << (100.0 * label_area / area) << "%)" << std::endl;
                    // }
                    continue;
                }
            }

            // if (first_debug) {
            //     std::cout << "    -> 过滤掉" << std::endl;
            // }
            cv::drawContours(noise_filter_mask, std::vector<std::vector<cv::Point>>{contour},
                0, 255, cv::FILLED);
            filtered_contours++;
        } else if (area < area_threshold) {
            // 这个区域原本会被过滤，但因为自适应阈值而保留
            kept_by_adaptive++;
            // if (first_debug) {
            //     std::cout << "    -> 自适应保留" << std::endl;
            // }
        } else {
            // if (first_debug) {
            //     std::cout << "    -> 超过原阈值，自然保留" << std::endl;
            // }
        }

        // first_debug = false;  // 只在第一次调用时输出详细调试信息
    }

    return noise_filter_mask;
}

bool isLowTextureArea(const std::vector<cv::Point>& connected_points, const cv::Mat& image) {
    // vector<Point> cv_points;
    // for (const auto& p : connected_points) {
    //     cv_points.push_back(Point(p.x, p.y));
    // }

    cv::Rect rect = cv::boundingRect(connected_points);
    cv::Mat block = image(rect);

    cv::Scalar mean, stddev;
    cv::meanStdDev(block, mean, stddev);
    double var = stddev[0] * stddev[0];

    return var < 20;
}

bool isLowTextureArea(const cv::Rect& roi, const cv::Mat& image) {


    // Calculate variance only for the roi region

    cv::Mat block = image(roi);

    cv::Scalar mean, stddev;
    cv::meanStdDev(block, mean, stddev);
    double std_val = stddev[0];
    // double var = stddev[0] * stddev[0];

    int maskedArea = cv::countNonZero(block);

    // std::cout << "maskedArea: " << maskedArea << " , mean: " << mean[0] << " , std: " << std_val << std::endl;

    return std_val < 10;
}

cv::Mat detectDisparityAnomalies(
    const cv::Mat& reference_disparity,
    const cv::Mat& target_disparity,
    const MultiScaleFilterParams& params,
    const cv::Mat& gray
) {
    cv::Mat final_filter_mask = cv::Mat::zeros(target_disparity.size(), CV_8U);
    cv::Mat visited = cv::Mat::zeros(target_disparity.size(), CV_8U);

    const int height = target_disparity.rows;
    const int width = target_disparity.cols;

    // Find initial noise pixels
    auto t1 = Clock::now();
    std::unordered_set<cv::Point, PointHash> noise_pixels;
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            float ref_val = reference_disparity.at<float>(y, x);
            float curr_val = target_disparity.at<float>(y, x);
            float diff = curr_val - ref_val;

            bool is_noise = (ref_val >= 0 && diff > params.diff_threshold) ||
                (ref_val < 0 && diff > params.potential_threshold) ||
                (curr_val > params.excessive_threshold);

            if (is_noise) {
                noise_pixels.insert(cv::Point(x, y));
            }
        }
    }
    auto t2 = Clock::now();
    std::cout << "Find initial noise pixels: " << noise_pixels.size() << std::endl;
    std::cout << " computation time: "
        << std::chrono::duration_cast<std::chrono::milliseconds>(t2 - t1).count()
        << " ms" << std::endl;


    const int padding = params.growing_window_size / 2;

    auto t_while_start = Clock::now();

    while (!noise_pixels.empty()) {
        auto it = noise_pixels.begin();
        cv::Point current = *it;
        noise_pixels.erase(it);

        if (visited.at<uchar>(current.y, current.x) ||
            std::isnan(target_disparity.at<float>(current.y, current.x))) {
            continue;
        }

        cv::Mat window_check_map = cv::Mat::zeros(target_disparity.size(), CV_8U);

        // Window analysis
        cv::Rect roi(
            std::max(0, current.x - padding),
            std::max(0, current.y - padding),
            std::min(width - current.x + padding, params.growing_window_size),
            std::min(height - current.y + padding, params.growing_window_size)
        );

        cv::Mat window = target_disparity(roi);
        float center_value = target_disparity.at<float>(current.y, current.x);

        std::vector<float> valid_values;
        for (int y = 0; y < window.rows; ++y) {
            for (int x = 0; x < window.cols; ++x) {
                float val = window.at<float>(y, x);
                if (!std::isnan(val)) {
                    valid_values.push_back(val);
                }
            }
        }

        if (valid_values.empty()) {
            continue;
        }


        // Calculate median and std
        std::sort(valid_values.begin(), valid_values.end());
        float window_median = valid_values[valid_values.size() / 2];

        float sum = 0, sum_sq = 0;
        for (float val : valid_values) {
            sum += val;
            sum_sq += val * val;
        }
        float mean = sum / valid_values.size();
        float window_std = std::sqrt(sum_sq / valid_values.size() - mean * mean);

        if (std::abs(center_value - window_median) > 2 * window_std ||
            center_value >= params.excessive_threshold) {

            // auto t2 = Clock::now();
            auto [connected_points, updated_visited] = bfsMarkConnected(
                target_disparity, current.y, current.x, visited, params.growing_threshold);
            // auto t3 = Clock::now();
            // std::cout << "bfsMarkConnected computation time: "
            //     << std::chrono::duration_cast<std::chrono::milliseconds>(t3 - t2).count()
            //     << " ms" << std::endl;
            visited = updated_visited;

            for (const auto& p : connected_points) {
                window_check_map.at<uchar>(p.y, p.x) = 1;
                noise_pixels.erase(p);
            }

            cv::Mat ref_check_map = window_check_map & (reference_disparity > 0);
            bool is_area_similar = false;

            // auto t4 = Clock::now();
            if (countNonZero(ref_check_map) > 0) {
                std::vector<float> area_values, ref_area_values;
                for (int i = 0; i < height; ++i) {
                    for (int j = 0; j < width; ++j) {
                        if (window_check_map.at<uchar>(i, j)) {
                            area_values.push_back(target_disparity.at<float>(i, j));
                        }
                        if (ref_check_map.at<uchar>(i, j)) {
                            ref_area_values.push_back(reference_disparity.at<float>(i, j));
                        }
                    }
                }

                std::sort(area_values.begin(), area_values.end());
                std::sort(ref_area_values.begin(), ref_area_values.end());
                float area_median = area_values[area_values.size() / 2];
                float ref_area_median = ref_area_values[ref_area_values.size() / 2];
                float area_diff = abs(area_median - ref_area_median);

                is_area_similar = area_diff < 2.0f;
            }
            // auto t5 = Clock::now();
            // std::cout << "area similar check computation time: "
            //     << std::chrono::duration_cast<std::chrono::milliseconds>(t5 - t4).count()
            //     << " ms" << std::endl;

            // Don't discard too large area in high texture area
            if (connected_points.size() > 800) {
                // auto t6 = Clock::now();
                if (!isLowTextureArea(connected_points, gray)) {
                    window_check_map = cv::Mat::zeros(target_disparity.size(), CV_8U);
                }
                // auto t7 = Clock::now();
                // std::cout << "isLowTextureArea computation time: "
                //     << std::chrono::duration_cast<std::chrono::milliseconds>(t7 - t5).count()
                //     << " ms" << std::endl;
            }

            if (is_area_similar) {
                for (int i = 0; i < height; ++i) {
                    for (int j = 0; j < width; ++j) {
                        if (ref_check_map.at<uchar>(i, j)) {
                            window_check_map.at<uchar>(i, j) = 0;
                        }
                    }
                }
            }

            final_filter_mask = final_filter_mask | window_check_map;

            // for (const auto& point : connected_points) {
            //     final_filter_mask.at<uchar>(point.y, point.x) = 1;
            //     noise_pixels.erase(point);
            // }

        }


    }

    auto t_while_stop = Clock::now();
    std::cout << "while loop computation time: "
        << std::chrono::duration_cast<std::chrono::milliseconds>(t_while_stop - t_while_start).count()
        << " ms" << std::endl;

    return final_filter_mask;
}

cv::Mat detectDisparityAnomaliesOptimized(const cv::Mat& reference_disparity,
    const cv::Mat& target_disparity,
    const MultiScaleFilterParams& params,
    const cv::Mat& gray, 
    const cv::Mat obstacle_mask) {

    cv::Mat final_filter_mask = cv::Mat::zeros(target_disparity.size(), CV_8U);
    cv::Mat diff = target_disparity - reference_disparity;
    cv::Mat reference_disparity_valid = reference_disparity >= 0.0f;
    cv::Mat reference_disparity_invalid = reference_disparity < 0.0f;

    // Convert to binary mask for connected components
    cv::Mat potential_noise = (
        ((diff > params.diff_threshold) & reference_disparity_valid) |
        ((diff > params.potential_threshold) & reference_disparity_invalid) |
        (target_disparity > params.excessive_threshold)
        );
    cv::Mat noise_mask;
    potential_noise.convertTo(noise_mask, CV_8U);

    const int height = target_disparity.rows;
    const int width = target_disparity.cols;

    cv::Mat labels, stats, centroids;
    int num_components = connectedComponentsWithStats(noise_mask, labels, stats, centroids, 4, CV_16U);

    for (int i = 1; i < num_components; i++) {  // Start from 1 to skip background
        // Get component stats
        cv::Mat component_mask = (labels == i);
        int area = stats.at<int>(i, cv::CC_STAT_AREA);
        int left = stats.at<int>(i, cv::CC_STAT_LEFT);
        int top = stats.at<int>(i, cv::CC_STAT_TOP);
        int width = stats.at<int>(i, cv::CC_STAT_WIDTH);
        int height = stats.at<int>(i, cv::CC_STAT_HEIGHT);
        cv::Rect roi(left, top, width, height);

        // Visualize
        // cv::Mat component_disp = target_disparity.clone();
        // component_disp.setTo(0, ~component_mask);
        // cv::Mat obstacle_disp = target_disparity.clone();
        // obstacle_disp.setTo(0, ~component_mask);
        // cv::Mat obstacle_mask = obstacle_mask.clone();
        // obstacle_disp.setTo(0, ~obstacle_mask);
        // cv::Mat roi_disp = gray.clone();
        // // Set outside of roi to zero
        // roi_disp.setTo(0, ~component_mask);
        
        
        // cv::imshow("candidate_dilate", component_disp);
        // cv::imshow("roi", roi_disp);
        // cv::imshow("obstacle", obstacle_disp);
        // cv::waitKey();
        

        // Skip too large region/object
        if (area > 2000) {
            continue;
        }

        // Some small and far away candidates, we can safely remove them
        float mean_val = cv::mean(target_disparity, component_mask)[0];
        if ((area > 1000) && (mean_val < params.potential_threshold)) {
            final_filter_mask |= component_mask;
            continue;
        }

        // Skip processing if component is too large and not in low texture area
        if (area > 400) {
            // Create mask for current component
            if (!isLowTextureArea(roi, gray)) {
                continue;
            }

            // Check obstacle mask
            // If the component is likely an obstacle (area ratio > 0.5), skip it
            if (!obstacle_mask.empty()) {
                cv::Mat component_obstacle_mask = obstacle_mask & component_mask;
                int label_area = cv::countNonZero(component_obstacle_mask);

                // **方案5：草地区域保护逻辑**
                // 如果组件大部分在obstacle_mask之外（即可能是草地、路面等平面），跳过过滤
                int non_obstacle_area = area - label_area;
                if (non_obstacle_area > 0.7 * area) {
                    // 大部分区域不是障碍物，可能是草地/路面，保留视差
                    continue;
                }

                // Only keep close obstacles
                if (label_area > 0.5 * area && mean_val > params.excessive_threshold) {
                    // Optional: remove non obstacle area
                    cv::Mat component_non_obstacle_mask = component_mask & ~obstacle_mask;
                    final_filter_mask |= component_non_obstacle_mask;
                    continue;
                }
            }
        }

        final_filter_mask |= component_mask;
    }

    return final_filter_mask;
}

// 方案4：填充草地等平面区域的视差空洞
cv::Mat fillLawnDisparityHoles(const cv::Mat& disparity, const cv::Mat& obstacle_mask) {
    cv::Mat filled_disparity = disparity.clone();

    if (obstacle_mask.empty()) {
        return filled_disparity;  // 没有语义信息，直接返回
    }

    // 创建草地/平面区域mask（obstacle_mask之外的区域）
    cv::Mat lawn_mask = ~obstacle_mask;

    // 找到视差无效的区域
    cv::Mat invalid_mask = (disparity <= 0);

    // 草地区域中的空洞
    cv::Mat lawn_holes = lawn_mask & invalid_mask;

    if (cv::countNonZero(lawn_holes) == 0) {
        return filled_disparity;  // 没有空洞需要填充
    }

    // === 策略1: 形态学闭运算填充小空洞 ===
    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_ELLIPSE, cv::Size(21, 21));  // 增大到21
    cv::Mat disparity_closed;
    cv::morphologyEx(filled_disparity, disparity_closed, cv::MORPH_CLOSE, kernel);
    disparity_closed.copyTo(filled_disparity, lawn_holes);

    // === 策略2: 对大空洞使用区域统计填充 ===
    cv::Mat still_invalid = (filled_disparity <= 0) & lawn_mask;

    if (cv::countNonZero(still_invalid) > 0) {
        // 将图像分成网格，对每个网格使用周边有效值的中值填充
        int grid_size = 40;  // 网格大小

        for (int y = 0; y < filled_disparity.rows; y += grid_size) {
            for (int x = 0; x < filled_disparity.cols; x += grid_size) {
                int h = std::min(grid_size, filled_disparity.rows - y);
                int w = std::min(grid_size, filled_disparity.cols - x);
                cv::Rect roi(x, y, w, h);

                cv::Mat grid_invalid = still_invalid(roi);
                if (cv::countNonZero(grid_invalid) == 0) continue;

                // 在更大的邻域内寻找有效视差
                int search_size = 80;
                int sx = std::max(0, x - search_size/2);
                int sy = std::max(0, y - search_size/2);
                int sw = std::min(filled_disparity.cols - sx, w + search_size);
                int sh = std::min(filled_disparity.rows - sy, h + search_size);
                cv::Rect search_roi(sx, sy, sw, sh);

                cv::Mat search_region = filled_disparity(search_roi);
                cv::Mat search_valid = search_region > 0;

                if (cv::countNonZero(search_valid) > 10) {
                    // 计算有效区域的统计值
                    cv::Scalar mean_val = cv::mean(search_region, search_valid);
                    float fill_value = mean_val[0];

                    // 填充该网格中的无效值
                    filled_disparity(roi).setTo(fill_value, grid_invalid);
                }
            }
        }
    }

    // === 策略3: 最后的高斯平滑 ===
    still_invalid = (filled_disparity <= 0) & lawn_mask;
    if (cv::countNonZero(still_invalid) > 0) {
        cv::Mat blurred;
        cv::GaussianBlur(filled_disparity, blurred, cv::Size(15, 15), 0);
        blurred.copyTo(filled_disparity, still_invalid);
    }

    return filled_disparity;
}

// cv::Mat computeMultiScaleDisparity(cv::Ptr<cv::StereoBM> half_top_stereo_block_matcher,
//     cv::Ptr<cv::StereoSGBM> half_bottom_stereo_block_matcher,
//     const cv::Mat& gray_left, const cv::Mat& gray_right,
//     cv::Mat& input_disparity,
//     const MultiScaleFilterParams& orig_param, const MultiScaleFilterParams& half_param, cv::Mat obstacle_mask) {

//     // Assume gray_left and gray_right are 320x240
//     int top_block_size = half_top_stereo_block_matcher->getBlockSize();
//     int bottom_block_size = half_bottom_stereo_block_matcher->getBlockSize();
//     cv::Mat disparity = input_disparity.clone();


//     auto t1 = Clock::now();

//     // Compute disparity
//     cv::Mat disparity_small_16S, disparity_small_32F;
//     cv::Mat disparity_half_top;
//     cv::Mat disparity_half_bottom;

//     // Process at 160x120
//     cv::Mat gray_left_half, gray_right_half;
//     cv::pyrDown(gray_left, gray_left_half);
//     cv::pyrDown(gray_right, gray_right_half);
//     int half_width = gray_left_half.cols; // 160
//     int half_height = gray_left_half.rows; // 120
//     disparity_small_32F.create(gray_left_half.size(), CV_32F);

//     cv::Rect half_top_with_pad(0, 0, half_width, half_height / 2 + top_block_size);
//     cv::Rect half_bottom_with_pad(0, half_height / 2 - bottom_block_size, half_width, half_height / 2 + bottom_block_size);

//     cv::Mat gray_left_half_top = gray_left_half(half_top_with_pad);
//     cv::Mat gray_right_half_top = gray_right_half(half_top_with_pad);
//     cv::Mat gray_left_half_bottom = gray_left_half(half_bottom_with_pad);
//     cv::Mat gray_right_half_bottom = gray_right_half(half_bottom_with_pad);

//     half_top_stereo_block_matcher->compute(gray_left_half_top, gray_right_half_top, disparity_half_top);
//     half_bottom_stereo_block_matcher->compute(gray_left_half_bottom, gray_right_half_bottom, disparity_half_bottom);

//     disparity_half_top.convertTo(disparity_half_top, CV_32F);
//     disparity_half_top = disparity_half_top / 16.0f;
//     disparity_half_bottom.convertTo(disparity_half_bottom, CV_32F);
//     disparity_half_bottom = disparity_half_bottom / 16.0f;

//     cv::vconcat(disparity_half_top(cv::Rect(0, 0, half_width, half_height / 2)),
//         disparity_half_bottom(cv::Rect(0, bottom_block_size, half_width, half_height / 2)),
//         disparity_small_32F);

//     // disparity_small_32F(cv::Rect(0, 0, half_width, half_height / 2)) =
//     //     disparity_half_top(cv::Rect(0, 0, half_width, half_height / 2));
//     // disparity_small_32F(cv::Rect(0, half_height / 2, half_width, half_height / 2)) =
//     //     disparity_half_bottom(cv::Rect(0, bottom_block_size, half_width, half_height / 2));

//     // disparity_small_16S.convertTo(disparity_small_32F, CV_32F);
//     // disparity_small_32F /= 16.0f;
//     // std::cout << "disparity_small_32F.size: " << disparity_small_32F.size() << std::endl;
//     // Resize to 320x240 and do comparison
//     cv::resize(disparity_small_32F, disparity_small_32F, input_disparity.size(), 0, 0, cv::INTER_NEAREST);
// //    cv::resize(disparity_small_32F, disparity_small_32F, input_disparity.size(), 0, 0, cv::INTER_LINEAR_EXACT);
//     disparity_small_32F *= 2;

//     // downsample obstacle_mask
//     cv::Mat obstacle_mask_small;
//     if(!obstacle_mask.empty()) {
//         cv::resize(obstacle_mask, obstacle_mask_small, input_disparity.size(), 0, 0, cv::INTER_NEAREST);
//     }   
    

//     auto t2 = Clock::now();
//     // cv::Mat orig_to_small_map = detectDisparityAnomalies(disparity_small_32F, disparity.clone(), orig_param, gray_left);
//     cv::Mat orig_to_small_map = detectDisparityAnomaliesOptimized(
//         disparity_small_32F, disparity.clone(), orig_param, gray_left, obstacle_mask_small);
//     auto t3 = Clock::now();
//     // cv::Mat small_to_orig_map = detectDisparityAnomalies(disparity, disparity_small_32F, half_param, gray_left);
//     cv::Mat small_to_orig_map = detectDisparityAnomaliesOptimized(
//         disparity, disparity_small_32F, half_param, gray_left, obstacle_mask_small);
//     auto t4 = Clock::now();

// //    cv::imshow("orig_to_small_map", orig_to_small_map);
// //    cv::imshow("small_to_orig_map", small_to_orig_map);
// //    cv::waitKey();

//     // Apply filters
//     disparity.setTo(0, orig_to_small_map);
//     disparity.setTo(0, small_to_orig_map);

//     // Complete using small disparity
//     cv::Mat valid_for_complete = disparity < 0;
//     valid_for_complete = valid_for_complete & ~(orig_to_small_map | small_to_orig_map);
//     disparity_small_32F.copyTo(disparity, valid_for_complete);

//     // Final noise filtering
//     // std::cout << "disparity size: " << disparity.size() << std::endl;
//     // double minVal, maxVal;
//     // cv::Point minLoc, maxLoc;

//     // cv::minMaxLoc(disparity, &minVal, &maxVal, &minLoc, &maxLoc);

//     // std::cout << "Minimum value: " << minVal << " at (" << minLoc.x << ", " << minLoc.y << ")" << std::endl;
//     // std::cout << "Maximum value: " << maxVal << " at (" << maxLoc.x << ", " << maxLoc.y << ")" << std::endl;

//     cv::Rect top = cv::Rect(0, 0, disparity.cols, half_height);
//     cv::Rect bottom = cv::Rect(0, half_height, disparity.cols, half_height);  
//     cv::Mat noise_filter_mask0 = cv::Mat::zeros(disparity.size(), CV_8U);  
//     cv::Mat noise_filter_mask1 = cv::Mat::zeros(disparity.size(), CV_8U);    

//     if (!obstacle_mask.empty()) {
//         cv::Mat noise_filter_mask0_top = smallRegionHighDisparityFilter(disparity(top), 12, 1000, obstacle_mask_small(top));
//         cv::Mat noise_filter_mask0_bottom = smallRegionHighDisparityFilter(disparity(bottom), 12, 150, obstacle_mask_small(bottom));
        
//         cv::vconcat(noise_filter_mask0_top, noise_filter_mask0_bottom, noise_filter_mask0);

//         cv::Mat noise_filter_mask1_top = smallRegionHighDisparityFilter(disparity(top), 35, 250, obstacle_mask_small(top));
//         cv::Mat noise_filter_mask1_bottom = smallRegionHighDisparityFilter(disparity(bottom), 35, 250, obstacle_mask_small(bottom));
        
//         cv::vconcat(noise_filter_mask1_top, noise_filter_mask1_bottom, noise_filter_mask1);
//     }
//     else {
//         cv::Mat noise_filter_mask0_top = smallRegionHighDisparityFilter(disparity(top), 12, 1000, obstacle_mask_small);
//         cv::Mat noise_filter_mask0_bottom = smallRegionHighDisparityFilter(disparity(bottom), 12, 150, obstacle_mask_small);

//         cv::vconcat(noise_filter_mask0_top, noise_filter_mask0_bottom, noise_filter_mask0);

//         cv::Mat noise_filter_mask1_top = smallRegionHighDisparityFilter(disparity(top), 35, 250, obstacle_mask_small);
//         cv::Mat noise_filter_mask1_bottom = smallRegionHighDisparityFilter(disparity(bottom), 35, 250, obstacle_mask_small);

//         cv::vconcat(noise_filter_mask1_top, noise_filter_mask1_bottom, noise_filter_mask1);
//     }

//     // cv::imshow("noise_filter_mask0", noise_filter_mask0);
//     // cv::imshow("noise_filter_mask1", noise_filter_mask1);
//     // cv::waitKey();

//     // cv::Mat noise_filter_mask = smallRegionHighDisparityFilter(disparity, 12, 1000, obstacle_mask_small);
//     // cv::Mat noise_filter_mask2 = smallRegionHighDisparityFilter(disparity, 35, 250, obstacle_mask_small);
//     // noise_filter_mask = noise_filter_mask | noise_filter_mask2;
//     disparity.setTo(0, noise_filter_mask0);
//     disparity.setTo(0, noise_filter_mask1);
//     auto t5 = Clock::now();

//     // cv::imshow("noise_filter_mask", noise_filter_mask);
//     // cv::imshow("noise_filter_mask2", noise_filter_mask2);

//     // cv::Mat disparity_vis;
//     // cv::Mat disparity_colored;
//     // disparity.convertTo(disparity_colored, CV_8U, 255.0 / 100, 1);
//     // // cv::normalize(disparity_vis, disparity_colored, 0, 255, cv::NORM_MINMAX, CV_8U);
//     // cv::applyColorMap(disparity_colored, disparity_colored, cv::COLORMAP_VIRIDIS);

//     // cv::Mat disparity_half_vis;
//     // cv::Mat disparity_half_colored;
//     // disparity_small_32F.convertTo(disparity_half_colored, CV_8U, 255.0 / 100, 1);
//     // // cv::normalize(disparity_half_vis, disparity_half_colored, 0, 255, cv::NORM_MINMAX, CV_8U);
//     // cv::applyColorMap(disparity_half_colored, disparity_half_colored, cv::COLORMAP_VIRIDIS);

//     // cv::Mat disparity_orig_vis;
//     // cv::Mat disparity_orig_colored;
//     // input_disparity.convertTo(disparity_orig_colored, CV_8U, 255.0 / 100, 1);
//     // // cv::normalize(disparity_orig_vis, disparity_orig_colored, 0, 255, cv::NORM_MINMAX, CV_8U);
//     // cv::applyColorMap(disparity_orig_colored, disparity_orig_colored, cv::COLORMAP_VIRIDIS);

//     // cv::imshow("input_disparity", disparity_orig_colored);
//     // cv::imshow("disparity", disparity_colored);
//     // cv::imshow("disparity_small_32F", disparity_half_colored);
//     // cv::waitKey();

//     // Final resize
//     cv::resize(disparity, disparity, cv::Size(640, 480), 0, 0, cv::INTER_NEAREST);
//     disparity *= 2;


// //    std::cout << "small Disparity computation time: "
// //        << std::chrono::duration_cast<std::chrono::milliseconds>(t2 - t1).count()
// //        << " ms" << std::endl;
// //    std::cout << "orig_to_small_map computation time: "
// //        << std::chrono::duration_cast<std::chrono::milliseconds>(t3 - t2).count()
// //        << " ms" << std::endl;
// //    std::cout << "small_to_orig_map computation time: "
// //        << std::chrono::duration_cast<std::chrono::milliseconds>(t4 - t3).count()
// //        << " ms" << std::endl;
// //    std::cout << "smallRegionHighDisparityFilter computation time: "
// //        << std::chrono::duration_cast<std::chrono::milliseconds>(t5 - t4).count()
// //        << " ms" << std::endl;

//     return disparity;
// }

cv::Mat computeMultiScaleDisparity(
    cv::Ptr<cv::StereoBM> half_top_stereo_block_matcher,
    cv::Ptr<cv::StereoSGBM> half_bottom_stereo_block_matcher,
    const cv::Mat& gray_left, const cv::Mat& gray_right,
    cv::Mat& input_disparity,
    const MultiScaleFilterParams& orig_param,
    const MultiScaleFilterParams& half_param,
    cv::Mat obstacle_mask,
    double fx, double fy,
    double cx, double cy,
    double baseline,
    bool enable_height_filter) {

    cv::Mat disparity = input_disparity.clone();

    // === 1. 准备障碍物掩码 ===
    cv::Mat obstacle_mask_320;
    if (!obstacle_mask.empty() && obstacle_mask.size() != cv::Size(320, 240)) {
        cv::resize(obstacle_mask, obstacle_mask_320, cv::Size(320, 240), 0, 0, cv::INTER_NEAREST);
    } else {
        obstacle_mask_320 = obstacle_mask;
    }

    // === 2. 计算小尺度视差 (160x120) ===
    cv::Mat gray_left_half, gray_right_half;
    cv::pyrDown(gray_left, gray_left_half);
    cv::pyrDown(gray_right, gray_right_half);

    int half_width = gray_left_half.cols;
    int half_height = gray_left_half.rows;

    // 分区域计算视差
    int top_block_size = half_top_stereo_block_matcher->getBlockSize();
    int bottom_block_size = half_bottom_stereo_block_matcher->getBlockSize();

    cv::Rect half_top_with_pad(0, 0, half_width, half_height / 2 + top_block_size);
    cv::Rect half_bottom_with_pad(0, half_height / 2 - bottom_block_size, half_width, half_height / 2 + bottom_block_size);

    cv::Mat disparity_half_top, disparity_half_bottom;
    half_top_stereo_block_matcher->compute(gray_left_half(half_top_with_pad), gray_right_half(half_top_with_pad), disparity_half_top);

    // === 新方案8：底部区域分两次计算，最底部使用无SpeckleFilter版本 ===
    // 保存原始SpeckleFilter参数
    int orig_speckle_window = half_bottom_stereo_block_matcher->getSpeckleWindowSize();
    int orig_speckle_range = half_bottom_stereo_block_matcher->getSpeckleRange();

    // 第一次：使用正常参数计算整个bottom区域
    half_bottom_stereo_block_matcher->compute(gray_left_half(half_bottom_with_pad), gray_right_half(half_bottom_with_pad), disparity_half_bottom);

    // 第二次：对最底部1/3禁用SpeckleFilter重新计算
    int bottom_third_start = (half_height * 2) / 3;  // 最底部1/3的起始行
    if (bottom_third_start < half_height) {
        cv::Rect bottom_third_roi(0, bottom_third_start - bottom_block_size,
                                  half_width, half_height - bottom_third_start + bottom_block_size);

        // 临时禁用SpeckleFilter
        half_bottom_stereo_block_matcher->setSpeckleWindowSize(0);
        half_bottom_stereo_block_matcher->setSpeckleRange(0);

        cv::Mat disparity_bottom_third;
        half_bottom_stereo_block_matcher->compute(gray_left_half(bottom_third_roi),
                                                  gray_right_half(bottom_third_roi),
                                                  disparity_bottom_third);

        // 恢复SpeckleFilter参数
        half_bottom_stereo_block_matcher->setSpeckleWindowSize(orig_speckle_window);
        half_bottom_stereo_block_matcher->setSpeckleRange(orig_speckle_range);

        // 将无SpeckleFilter的结果合并到bottom区域（只覆盖原本无效的区域）
        disparity_bottom_third.convertTo(disparity_bottom_third, CV_16S);
        int merge_start = bottom_third_start - (half_height / 2 - bottom_block_size);
        for (int y = std::max(0, merge_start); y < disparity_half_bottom.rows; ++y) {
            for (int x = 0; x < disparity_half_bottom.cols; ++x) {
                int16_t orig_val = disparity_half_bottom.at<int16_t>(y, x);
                int y_third = y - merge_start + bottom_block_size;
                if (y_third >= 0 && y_third < disparity_bottom_third.rows) {
                    int16_t new_val = disparity_bottom_third.at<int16_t>(y_third, x);
                    // 只在原值无效时使用新值
                    if (orig_val <= 0 && new_val > 0) {
                        disparity_half_bottom.at<int16_t>(y, x) = new_val;
                    }
                }
            }
        }
    }

    // 转换为32F并归一化
    disparity_half_top.convertTo(disparity_half_top, CV_32F, 1.0/16.0);
    disparity_half_bottom.convertTo(disparity_half_bottom, CV_32F, 1.0/16.0);

    // 组装完整的小尺度视差
    cv::Mat disparity_small_32F(half_height, half_width, CV_32F);
    disparity_half_top(cv::Rect(0, 0, half_width, half_height/2)).copyTo(disparity_small_32F(cv::Rect(0, 0, half_width, half_height/2)));
    disparity_half_bottom(cv::Rect(0, bottom_block_size, half_width, half_height/2)).copyTo(disparity_small_32F(cv::Rect(0, half_height/2, half_width, half_height/2)));

    // === 3. 异常检测 (使用原始参数) ===
    cv::Mat input_disparity_small;
    cv::resize(input_disparity, input_disparity_small, gray_left_half.size(), 0, 0, cv::INTER_NEAREST);
    input_disparity_small.convertTo(input_disparity_small, CV_32F, 0.5f); // /= 2.0f

    cv::Mat obstacle_mask_small;
    if (!obstacle_mask_320.empty()) {
        cv::resize(obstacle_mask_320, obstacle_mask_small, gray_left_half.size(), 0, 0, cv::INTER_NEAREST);
    }

    cv::Mat orig_to_small_map = detectDisparityAnomaliesOptimized(
        disparity_small_32F, input_disparity_small, orig_param, gray_left_half, obstacle_mask_small);

    cv::Mat small_to_orig_map = detectDisparityAnomaliesOptimized(
        input_disparity_small, disparity_small_32F, half_param, gray_left_half, obstacle_mask_small);

    //imwrite("orig_to_small_map.png", orig_to_small_map);
    //imwrite("small_to_orig_map.png", small_to_orig_map);

    // === 4. 应用异常检测结果 ===
    cv::resize(orig_to_small_map, orig_to_small_map, disparity.size(), 0, 0, cv::INTER_NEAREST);
    cv::resize(small_to_orig_map, small_to_orig_map, disparity.size(), 0, 0, cv::INTER_NEAREST);

    disparity.setTo(0, orig_to_small_map);
    disparity.setTo(0, small_to_orig_map);

    // === 5. 使用小尺度视差补全缺失区域 ===
    cv::Mat disparity_small_upscaled;
    cv::resize(disparity_small_32F, disparity_small_upscaled, disparity.size(), 0, 0, cv::INTER_NEAREST);
    disparity_small_upscaled *= 2.0f;

    cv::Mat valid_for_complete = (disparity < 0) & ~(orig_to_small_map | small_to_orig_map);
    disparity_small_upscaled.copyTo(disparity, valid_for_complete);

    // === 6. 噪声过滤 (使用原始参数) ===
    cv::Rect top_roi(0, 0, disparity.cols, disparity.rows/2);
    cv::Rect bottom_roi(0, disparity.rows/2, disparity.cols, disparity.rows/2);

    cv::Mat noise_filter_mask = cv::Mat::zeros(disparity.size(), CV_8U);

    // 使用原始版本的过滤参数
    // ⚠️ 关键修改：完全禁用底部区域的小区域过滤
    // 底部区域通常是草地/道路，不应该被过滤
    cv::Mat mask_top = smallRegionHighDisparityFilter(disparity(top_roi), 12, 1000,
                     obstacle_mask_320.empty() ? cv::Mat() : obstacle_mask_320(top_roi));
    // 底部区域不再过滤，mask_bottom保持为全零
    cv::Mat mask_bottom = cv::Mat::zeros(bottom_roi.size(), CV_8U);

    mask_top.copyTo(noise_filter_mask(top_roi));
    mask_bottom.copyTo(noise_filter_mask(bottom_roi));

    noise_filter_mask(top_roi) |= mask_top;
    noise_filter_mask(bottom_roi) |= mask_bottom;

    disparity.setTo(0, noise_filter_mask);

    // === 7. 高度约束过滤 (策略一) ===
    // 只有在enable_height_filter为true时才执行
    if (enable_height_filter) {
        // std::cout << "\n========== 高度约束过滤调试信息 ==========" << std::endl;
        // 目的：过滤掉地面区域被错误映射到空中的点
        cv::Mat height_filter_mask = cv::Mat::zeros(disparity.size(), CV_8U);

        // 可调参数 - 修正：当前坐标系下Y向上为正，地面点Y为正值
        const float ground_region_y_ratio = 0.5f;  // 图像下半部分被认为是地面区域
        const float max_ground_height = -0.2f;      // 修正：Y>0表示在相机下方，允许到1.5m
        const float sky_region_y_ratio = 0.3f;     // 图像上部分被认为是天空区域
        const float sky_high_disp_threshold = 30.0f; // 天空区域的高视差阈值

        int ground_start_row = static_cast<int>(disparity.rows * ground_region_y_ratio);
        int sky_end_row = static_cast<int>(disparity.rows * sky_region_y_ratio);

        // 调试统计
        int ground_region_total = 0;
        int ground_region_filtered = 0;
        int sky_region_filtered = 0;

        for (int y = 0; y < disparity.rows; ++y) {
            for (int x = 0; x < disparity.cols; ++x) {
                float disp = disparity.at<float>(y, x);

                // 跳过无效视差
                if (disp <= 0 || std::isnan(disp)) {
                    continue;
                }

                // 计算3D点的Y坐标（相机坐标系下的高度）
                // Z = baseline * fx / disp
                // Y = (y - cy) * Z / fy = (y - cy) * baseline * fx / (disp * fy)
                float depth_Z = baseline * fx / disp;
                float point_Y = (y - cy) * depth_Z / fy;

                // 地面区域约束：如果像素在图像下半部分（可能是地面）
                // 修正逻辑：当前坐标系Y向上为正，图像底部对应正Y值（地面在相机下方）
                if (y >= ground_start_row) {
                    ground_region_total++;
                    // 地面点的Y坐标应该是小的正值（0到1.5m范围）
                    // 如果Y坐标远大于合理的地面高度，可能是错误映射
                    if (point_Y > max_ground_height) {
                        height_filter_mask.at<uchar>(y, x) = 255;
                        ground_region_filtered++;
                    }
                }

                // 天空区域约束：图像上部分出现非常近的点（高视差）通常是噪点
                if (y < sky_end_row && disp > sky_high_disp_threshold) {
                    height_filter_mask.at<uchar>(y, x) = 255;
                    sky_region_filtered++;
                }
            }
        }

        // std::cout << "地面区域约束参数:" << std::endl;
        // std::cout << "  ground_region_y_ratio: " << ground_region_y_ratio << std::endl;
        // std::cout << "  ground_start_row: " << ground_start_row << std::endl;
        // std::cout << "  max_ground_height: " << max_ground_height << " m" << std::endl;
        // std::cout << "  cy (principal point): " << cy << std::endl;
        // std::cout << "地面区域过滤统计:" << std::endl;
        // std::cout << "  地面区域总有效点数: " << ground_region_total << std::endl;
        // std::cout << "  被高度约束过滤: " << ground_region_filtered << " ("
        //           << (100.0 * ground_region_filtered / std::max(1, ground_region_total)) << "%)" << std::endl;
        // std::cout << "  天空区域被过滤: " << sky_region_filtered << std::endl;

        disparity.setTo(0, height_filter_mask);

        // 输出过滤统计信息
        // int height_filtered_count = cv::countNonZero(height_filter_mask);
        // std::cout << "[Height Filter] 总共过滤 " << height_filtered_count << " 个像素" << std::endl;
        // std::cout << "====================================\n" << std::endl;
    }

    // === 7.5. 方案4：填充草地等平面区域的视差空洞 ===
    // 暂时禁用，因为引入噪点
    // if (!obstacle_mask_320.empty()) {
    //     disparity = fillLawnDisparityHoles(disparity, obstacle_mask_320);
    //     std::cout << "[Lawn Fill] Applied lawn disparity hole filling" << std::endl;
    // }

    // === 8. 最终上采样 ===
    cv::Mat disparity_final;
    cv::resize(disparity, disparity_final, cv::Size(640, 480), 0, 0, cv::INTER_NEAREST);
    disparity_final *= 2.0f;

    // ========== 调试：检查红框区域(图像底部中央)的视差值 ==========
    // 红框大致位置：图像底部中央，假设在 y: 350-400, x: 250-400
    int red_box_valid = 0;
    int red_box_total = 0;
    float red_box_disp_sum = 0;
    for (int y = 350; y < 400 && y < disparity_final.rows; ++y) {
        for (int x = 250; x < 400 && x < disparity_final.cols; ++x) {
            red_box_total++;
            float disp = disparity_final.at<float>(y, x);
            if (disp > 0) {
                red_box_valid++;
                red_box_disp_sum += disp;
            }
        }
    }

    return disparity_final;
}
