#ifndef SEMANTIC_DEPTH_UTILS_HPP
#define SEMANTIC_DEPTH_UTILS_HPP

#include <opencv2/opencv.hpp>

bool isSemanticObstacleLabel(uchar label);
bool isUsableObstacleDepth(float depth);
bool isBottomSemanticRepairRegion(int cols, int rows, int x, int y);
bool shouldSampleSemanticPointPixel(int cols,
                                    int rows,
                                    int x,
                                    int y,
                                    uchar label,
                                    int base_step = 4,
                                    int dense_step = 2);
bool shouldSampleBottomSemanticContactPointPixel(int cols,
                                                 int rows,
                                                 int x,
                                                 int y,
                                                 uchar label);
bool shouldRepairLabel6GrassBoundaryPointPixel(const cv::Mat& label, int x, int y);
bool shouldFilterBottomGroundEdge(int cols, int rows, int x, int y, uchar label);
float findNaturalSameLabelRepairDepth(const cv::Mat& depth,
                                      const cv::Mat& label,
                                      int x,
                                      int y,
                                      uchar target_label,
                                      int max_radius = 18);
float findSemanticNeighborDepth(const cv::Mat& depth,
                                const cv::Mat& label,
                                int x,
                                int y,
                                int radius);
bool findNearbyConsistentSemanticObstacle(const cv::Mat& depth,
                                          const cv::Mat& label,
                                          int x,
                                          int y,
                                          int radius,
                                          int min_support,
                                          float depth_tolerance,
                                          uchar& obstacle_label,
                                          float& obstacle_depth);
cv::Mat inpaintSemanticObstacleDepth(const cv::Mat& depth, const cv::Mat& label);

#endif // SEMANTIC_DEPTH_UTILS_HPP
