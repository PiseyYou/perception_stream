#include "semantic_depth_utils.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <map>
#include <vector>

namespace {

float percentile(std::vector<float>& values, float ratio) {
    if (values.empty()) {
        return 0.0f;
    }
    const size_t index = std::min(values.size() - 1,
                                  static_cast<size_t>(values.size() * ratio));
    std::nth_element(values.begin(), values.begin() + index, values.end());
    return values[index];
}

void collectValidDepthsInRect(const cv::Mat& depth,
                              const cv::Mat& component_labels,
                              int component_id,
                              const cv::Rect& rect,
                              bool outside_component,
                              std::vector<float>& depths) {
    const cv::Rect image_rect(0, 0, depth.cols, depth.rows);
    const cv::Rect safe_rect = rect & image_rect;
    for (int y = safe_rect.y; y < safe_rect.y + safe_rect.height; ++y) {
        const float* depth_row = depth.ptr<float>(y);
        const int* comp_row = component_labels.ptr<int>(y);
        for (int x = safe_rect.x; x < safe_rect.x + safe_rect.width; ++x) {
            const bool in_component = comp_row[x] == component_id;
            if (outside_component == in_component) {
                continue;
            }
            const float d = depth_row[x];
            if (isUsableObstacleDepth(d)) {
                depths.push_back(d);
            }
        }
    }
}

}  // namespace

bool isSemanticObstacleLabel(uchar label) {
    return label == 4 || label == 5 || label == 6 || label == 7 || label >= 100;
}

bool isUsableObstacleDepth(float depth) {
    return std::isfinite(depth) && depth > 0.25f && depth < 5.5f;
}

bool isBottomSemanticRepairRegion(int cols, int rows, int x, int y) {
    if (cols <= 0 || rows <= 0) {
        return false;
    }
    return x >= cols / 5 && y >= rows * 3 / 5 && x < cols && y < rows;
}

bool shouldSampleSemanticPointPixel(int cols,
                                    int rows,
                                    int x,
                                    int y,
                                    uchar label,
                                    int base_step,
                                    int dense_step) {
    if (base_step <= 0 || dense_step <= 0 || x < 0 || y < 0 ||
        x >= cols || y >= rows) {
        return false;
    }

    const int tile_size = 16;
    const int tile_x = x / tile_size;
    const int tile_y = y / tile_size;
    const unsigned int hash = (tile_x * 73 + tile_y * 179) % 256;
    const int offset_x = (hash % 3) - 1;
    const int offset_y = ((hash / 3) % 3) - 1;
    const int jittered_x = x + offset_x;
    const int jittered_y = y + offset_y;

    if (isSemanticObstacleLabel(label) &&
        isBottomSemanticRepairRegion(cols, rows, x, y)) {
        return jittered_y % dense_step == 0;
    }

    return jittered_x % base_step == 0 && jittered_y % base_step == 0;
}

bool shouldSampleBottomSemanticContactPointPixel(int cols,
                                                 int rows,
                                                 int x,
                                                 int y,
                                                 uchar label) {
    if (cols <= 0 || rows <= 0 || x < 0 || y < 0 ||
        x >= cols || y >= rows) {
        return false;
    }
    if (!isSemanticObstacleLabel(label)) {
        return false;
    }
    if (!isBottomSemanticRepairRegion(cols, rows, x, y)) {
        return false;
    }
    return y >= rows * 4 / 5;
}

bool shouldRepairLabel6GrassBoundaryPointPixel(const cv::Mat& label, int x, int y) {
    if (label.empty() || label.type() != CV_8UC1 ||
        x < 0 || y < 0 || x >= label.cols || y >= label.rows) {
        return false;
    }
    if (label.at<uchar>(y, x) != 6 || y < label.rows * 3 / 5) {
        return false;
    }

    const int y0 = std::max(0, y - 2);
    const int y1 = std::min(label.rows - 1, y + 2);
    const int x0 = std::max(0, x - 2);
    const int x1 = std::min(label.cols - 1, x + 2);
    for (int yy = y0; yy <= y1; ++yy) {
        const uchar* row = label.ptr<uchar>(yy);
        for (int xx = x0; xx <= x1; ++xx) {
            if (row[xx] == 2 || row[xx] == 3) {
                return true;
            }
        }
    }
    return false;
}

bool shouldFilterBottomGroundEdge(int cols, int rows, int x, int y, uchar label) {
    if (cols <= 0 || rows <= 0 || x < 0 || y < 0 || x >= cols || y >= rows) {
        return false;
    }
    if (label != 2 && label != 3) {
        return false;
    }
    if (isBottomSemanticRepairRegion(cols, rows, x, y)) {
        return false;
    }
    if (y <= rows * 3 / 5) {
        return false;
    }
    const int edge_w = 48 + (y - rows * 3 / 5) * 120 / (rows * 2 / 5);
    return x < edge_w || x > cols - edge_w;
}

float findNaturalSameLabelRepairDepth(const cv::Mat& depth,
                                      const cv::Mat& label,
                                      int x,
                                      int y,
                                      uchar target_label,
                                      int max_radius) {
    if (depth.empty() || label.empty() || depth.size() != label.size() ||
        depth.type() != CV_32FC1 || label.type() != CV_8UC1 ||
        x < 0 || y < 0 || x >= depth.cols || y >= depth.rows ||
        max_radius <= 0 || !isSemanticObstacleLabel(target_label)) {
        return 0.0f;
    }
    if (label.at<uchar>(y, x) != target_label ||
        !isBottomSemanticRepairRegion(depth.cols, depth.rows, x, y)) {
        return 0.0f;
    }

    constexpr int kMinSupport = 4;
    constexpr float kMaxDepthSpread = 0.7f;
    for (int radius = 4; radius <= max_radius; radius += 2) {
        float weighted_sum = 0.0f;
        float weight_sum = 0.0f;
        float min_depth = std::numeric_limits<float>::max();
        float max_depth = 0.0f;
        int support = 0;
        int min_x = depth.cols;
        int max_x = -1;
        int min_y = depth.rows;
        int max_y = -1;

        const int y0 = std::max(0, y - radius);
        const int y1 = std::min(depth.rows - 1, y + radius);
        const int x0 = std::max(0, x - radius);
        const int x1 = std::min(depth.cols - 1, x + radius);
        for (int yy = y0; yy <= y1; ++yy) {
            const float* depth_row = depth.ptr<float>(yy);
            const uchar* label_row = label.ptr<uchar>(yy);
            for (int xx = x0; xx <= x1; ++xx) {
                if (xx == x && yy == y) {
                    continue;
                }
                if (label_row[xx] != target_label) {
                    continue;
                }
                const float candidate = depth_row[xx];
                if (!isUsableObstacleDepth(candidate)) {
                    continue;
                }
                const int dx = xx - x;
                const int dy = yy - y;
                const int dist2 = dx * dx + dy * dy;
                if (dist2 > radius * radius) {
                    continue;
                }
                const float weight = 1.0f / static_cast<float>(dist2 + 1);
                weighted_sum += candidate * weight;
                weight_sum += weight;
                min_depth = std::min(min_depth, candidate);
                max_depth = std::max(max_depth, candidate);
                min_x = std::min(min_x, xx);
                max_x = std::max(max_x, xx);
                min_y = std::min(min_y, yy);
                max_y = std::max(max_y, yy);
                ++support;
            }
        }

        const bool has_area_support = (max_x - min_x) >= 2 && (max_y - min_y) >= 2;
        if (support >= kMinSupport && has_area_support &&
            max_depth - min_depth <= kMaxDepthSpread && weight_sum > 0.0f) {
            return weighted_sum / weight_sum;
        }
    }
    return 0.0f;
}

float findSemanticNeighborDepth(const cv::Mat& depth,
                                const cv::Mat& label,
                                int x,
                                int y,
                                int radius);

namespace {

float findLocalSemanticDepth(const cv::Mat& depth,
                             const cv::Mat& label,
                             int x,
                             int y,
                             int max_radius) {
    for (int radius = 2; radius <= max_radius; radius += 2) {
        const float local_depth = findSemanticNeighborDepth(depth, label, x, y, radius);
        if (isUsableObstacleDepth(local_depth)) {
            return local_depth;
        }
    }
    return 0.0f;
}

float findLocalSameLabelDepth(const cv::Mat& depth,
                              const cv::Mat& label,
                              int x,
                              int y,
                              uchar target_label,
                              int max_radius) {
    constexpr int kMinSupport = 3;
    constexpr float kMaxDepthSpread = 0.7f;

    for (int radius = 2; radius <= max_radius; radius += 2) {
        std::vector<float> values;
        values.reserve((2 * radius + 1) * (2 * radius + 1));

        const int y0 = std::max(0, y - radius);
        const int y1 = std::min(depth.rows - 1, y + radius);
        const int x0 = std::max(0, x - radius);
        const int x1 = std::min(depth.cols - 1, x + radius);
        for (int yy = y0; yy <= y1; ++yy) {
            const float* depth_row = depth.ptr<float>(yy);
            const uchar* label_row = label.ptr<uchar>(yy);
            for (int xx = x0; xx <= x1; ++xx) {
                if (xx == x && yy == y) {
                    continue;
                }
                if (label_row[xx] != target_label) {
                    continue;
                }
                const float d = depth_row[xx];
                if (isUsableObstacleDepth(d)) {
                    values.push_back(d);
                }
            }
        }

        if (static_cast<int>(values.size()) < kMinSupport) {
            continue;
        }
        std::vector<float> sorted_values = values;
        const float low = percentile(sorted_values, 0.1f);
        sorted_values = values;
        const float high = percentile(sorted_values, 0.9f);
        if (high - low > kMaxDepthSpread) {
            continue;
        }
        return percentile(values, 0.5f);
    }
    return 0.0f;
}

bool findDirectionalSupport(const cv::Mat& depth,
                            const cv::Mat& label,
                            int x,
                            int y,
                            uchar target_label,
                            int dx,
                            int dy,
                            int max_distance,
                            float& support_depth,
                            int& support_distance) {
    for (int distance = 1; distance <= max_distance; ++distance) {
        const int xx = x + dx * distance;
        const int yy = y + dy * distance;
        if (xx < 0 || yy < 0 || xx >= depth.cols || yy >= depth.rows) {
            break;
        }
        if (label.at<uchar>(yy, xx) != target_label) {
            break;
        }
        const float candidate_depth = depth.at<float>(yy, xx);
        if (isUsableObstacleDepth(candidate_depth)) {
            support_depth = candidate_depth;
            support_distance = distance;
            return true;
        }
    }
    return false;
}

float findDirectionalSemanticDepth(const cv::Mat& depth,
                                   const cv::Mat& label,
                                   int x,
                                   int y,
                                   uchar target_label,
                                   int max_distance,
                                   bool require_bidirectional) {
    const int directions[2][2][2] = {
        {{-1, 0}, {1, 0}},
        {{0, -1}, {0, 1}},
    };

    for (const auto& axis : directions) {
        float first_depth = 0.0f;
        float second_depth = 0.0f;
        int first_distance = 0;
        int second_distance = 0;
        const bool has_first = findDirectionalSupport(depth, label, x, y,
                                                      target_label,
                                                      axis[0][0], axis[0][1],
                                                      max_distance,
                                                      first_depth, first_distance);
        const bool has_second = findDirectionalSupport(depth, label, x, y,
                                                       target_label,
                                                       axis[1][0], axis[1][1],
                                                       max_distance,
                                                       second_depth, second_distance);
        if (has_first && has_second) {
            const int total_distance = first_distance + second_distance;
            if (total_distance <= 0) {
                return 0.0f;
            }
            return (first_depth * second_distance + second_depth * first_distance) /
                   static_cast<float>(total_distance);
        }
        if (!require_bidirectional && has_first) {
            return first_depth;
        }
        if (!require_bidirectional && has_second) {
            return second_depth;
        }
    }

    return 0.0f;
}

}  // namespace

float findSemanticNeighborDepth(const cv::Mat& depth,
                                const cv::Mat& label,
                                int x,
                                int y,
                                int radius) {
    if (depth.empty() || label.empty() || depth.size() != label.size() ||
        depth.type() != CV_32FC1 || label.type() != CV_8UC1) {
        return 0.0f;
    }

    std::vector<float> values;
    values.reserve((2 * radius + 1) * (2 * radius + 1));

    const int y0 = std::max(0, y - radius);
    const int y1 = std::min(depth.rows - 1, y + radius);
    const int x0 = std::max(0, x - radius);
    const int x1 = std::min(depth.cols - 1, x + radius);

    for (int yy = y0; yy <= y1; ++yy) {
        const float* depth_row = depth.ptr<float>(yy);
        const uchar* label_row = label.ptr<uchar>(yy);
        for (int xx = x0; xx <= x1; ++xx) {
            if (!isSemanticObstacleLabel(label_row[xx])) {
                continue;
            }
            const float d = depth_row[xx];
            if (isUsableObstacleDepth(d)) {
                values.push_back(d);
            }
        }
    }

    if (values.size() < 2) {
        return 0.0f;
    }
    return percentile(values, 0.5f);
}

bool findNearbyConsistentSemanticObstacle(const cv::Mat& depth,
                                          const cv::Mat& label,
                                          int x,
                                          int y,
                                          int radius,
                                          int min_support,
                                          float depth_tolerance,
                                          uchar& obstacle_label,
                                          float& obstacle_depth) {
    obstacle_label = 0;
    obstacle_depth = 0.0f;

    if (depth.empty() || label.empty() || depth.size() != label.size() ||
        depth.type() != CV_32FC1 || label.type() != CV_8UC1 ||
        min_support <= 0 || radius <= 0) {
        return false;
    }

    std::vector<float> values;
    values.reserve((2 * radius + 1) * (2 * radius + 1));
    std::map<uchar, int> label_counts;

    const int y0 = std::max(0, y - radius);
    const int y1 = std::min(depth.rows - 1, y + radius);
    const int x0 = std::max(0, x - radius);
    const int x1 = std::min(depth.cols - 1, x + radius);

    for (int yy = y0; yy <= y1; ++yy) {
        const float* depth_row = depth.ptr<float>(yy);
        const uchar* label_row = label.ptr<uchar>(yy);
        for (int xx = x0; xx <= x1; ++xx) {
            const uchar candidate_label = label_row[xx];
            if (!isSemanticObstacleLabel(candidate_label)) {
                continue;
            }
            const float candidate_depth = depth_row[xx];
            if (!isUsableObstacleDepth(candidate_depth)) {
                continue;
            }
            values.push_back(candidate_depth);
            label_counts[candidate_label]++;
        }
    }

    if (static_cast<int>(values.size()) < min_support) {
        return false;
    }

    std::vector<float> depth_candidates = values;
    const float candidate_depth = percentile(depth_candidates, 0.5f);
    if (!isUsableObstacleDepth(candidate_depth)) {
        return false;
    }

    const float current_depth = depth.at<float>(y, x);
    if (isUsableObstacleDepth(current_depth) &&
        std::fabs(current_depth - candidate_depth) > depth_tolerance) {
        return false;
    }

    auto best_label = label_counts.begin();
    for (auto it = label_counts.begin(); it != label_counts.end(); ++it) {
        if (it->second > best_label->second) {
            best_label = it;
        }
    }

    obstacle_label = best_label->first;
    obstacle_depth = isUsableObstacleDepth(current_depth) ? current_depth : candidate_depth;
    return true;
}

cv::Mat inpaintSemanticObstacleDepth(const cv::Mat& depth, const cv::Mat& label) {
    if (depth.empty() || label.empty() || depth.size() != label.size() ||
        depth.type() != CV_32FC1 || label.type() != CV_8UC1) {
        return depth.clone();
    }

    cv::Mat obstacle_mask = cv::Mat::zeros(label.size(), CV_8UC1);
    for (int y = 0; y < label.rows; ++y) {
        const uchar* label_row = label.ptr<uchar>(y);
        uchar* mask_row = obstacle_mask.ptr<uchar>(y);
        for (int x = 0; x < label.cols; ++x) {
            if (isSemanticObstacleLabel(label_row[x])) {
                mask_row[x] = 255;
            }
        }
    }

    cv::Mat output = depth.clone();
    if (cv::countNonZero(obstacle_mask) == 0) {
        return output;
    }

    cv::Mat components;
    cv::Mat stats;
    cv::Mat centroids;
    const int component_count =
        cv::connectedComponentsWithStats(obstacle_mask, components, stats, centroids, 8);

    for (int component_id = 1; component_id < component_count; ++component_id) {
        const int area = stats.at<int>(component_id, cv::CC_STAT_AREA);
        if (area < 40) {
            continue;
        }

        const int left = stats.at<int>(component_id, cv::CC_STAT_LEFT);
        const int top = stats.at<int>(component_id, cv::CC_STAT_TOP);
        const int width = stats.at<int>(component_id, cv::CC_STAT_WIDTH);
        const int height = stats.at<int>(component_id, cv::CC_STAT_HEIGHT);
        const cv::Rect component_rect(left, top, width, height);

        std::vector<float> component_depths;
        component_depths.reserve(area);
        int invalid_count = 0;

        for (int y = component_rect.y; y < component_rect.y + component_rect.height; ++y) {
            const float* depth_row = depth.ptr<float>(y);
            const int* comp_row = components.ptr<int>(y);
            for (int x = component_rect.x; x < component_rect.x + component_rect.width; ++x) {
                if (comp_row[x] != component_id) {
                    continue;
                }
                const float d = depth_row[x];
                if (isUsableObstacleDepth(d)) {
                    component_depths.push_back(d);
                } else {
                    invalid_count++;
                }
            }
        }

        const int valid_count = static_cast<int>(component_depths.size());
        const int total_count = valid_count + invalid_count;
        if (total_count == 0 || invalid_count <= total_count / 5) {
            continue;
        }

        std::vector<float> fill_candidates = component_depths;
        float fill_depth = 0.0f;
        if (fill_candidates.size() >= 8) {
            fill_depth = percentile(fill_candidates, 0.25f);
        } else {
            std::vector<float> boundary_depths;
            boundary_depths.reserve(256);
            collectValidDepthsInRect(depth, components, component_id,
                                     component_rect + cv::Size(20, 20) - cv::Point(10, 10),
                                     true, boundary_depths);
            if (boundary_depths.size() >= 20) {
                fill_depth = percentile(boundary_depths, 0.5f);
            } else if (!component_depths.empty()) {
                fill_depth = percentile(component_depths, 0.5f);
            }
        }

        if (!isUsableObstacleDepth(fill_depth)) {
            continue;
        }

        const bool narrow_component = width <= 96 && height <= 64;
        const bool compact_component = area <= 80;

        for (int y = component_rect.y; y < component_rect.y + component_rect.height; ++y) {
            const int* comp_row = components.ptr<int>(y);
            float* out_row = output.ptr<float>(y);
            for (int x = component_rect.x; x < component_rect.x + component_rect.width; ++x) {
                if (comp_row[x] != component_id) {
                    continue;
                }
                if (!isUsableObstacleDepth(out_row[x])) {
                    const uchar target_label = label.at<uchar>(y, x);
                    const float same_label_depth =
                        findLocalSameLabelDepth(depth, label, x, y, target_label, 12);
                    if (isUsableObstacleDepth(same_label_depth)) {
                        out_row[x] = same_label_depth;
                        continue;
                    }

                    const float natural_depth =
                        findNaturalSameLabelRepairDepth(depth, label, x, y,
                                                        target_label, 18);
                    if (isUsableObstacleDepth(natural_depth)) {
                        out_row[x] = natural_depth;
                        continue;
                    }

                    const bool require_bidirectional = !narrow_component;
                    const int directional_distance = narrow_component ? 48 : 64;
                    const float directional_depth =
                        findDirectionalSemanticDepth(depth, label, x, y,
                                                     target_label,
                                                     directional_distance,
                                                     require_bidirectional);
                    if (isUsableObstacleDepth(directional_depth)) {
                        out_row[x] = directional_depth;
                    } else {
                        const float local_depth =
                            findLocalSemanticDepth(depth, label, x, y, 6);
                        if (isUsableObstacleDepth(local_depth) && compact_component) {
                            out_row[x] = local_depth;
                        } else if (compact_component) {
                            out_row[x] = fill_depth;
                        }
                    }
                }
            }
        }
    }

    return output;
}
