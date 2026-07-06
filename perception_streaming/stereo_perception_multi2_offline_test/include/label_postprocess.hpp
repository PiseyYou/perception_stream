#ifndef LABEL_POSTPROCESS_HPP
#define LABEL_POSTPROCESS_HPP

#include <opencv2/opencv.hpp>

void applyBottomGrassOverridePreservingObstacles(cv::Mat& label, int shift_high);

#endif // LABEL_POSTPROCESS_HPP
