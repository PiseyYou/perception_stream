#include "label_postprocess.hpp"

#include <opencv2/opencv.hpp>

#include <iostream>

namespace {

bool expectEqual(int actual, int expected, const char* message) {
    if (actual == expected) {
        return true;
    }
    std::cerr << message << ": expected " << expected << ", got " << actual << '\n';
    return false;
}

}  // namespace

int main() {
    cv::Mat label(384, 640, CV_8UC1, cv::Scalar(1));
    label.at<uchar>(372, 10) = 0;
    label.at<uchar>(372, 20) = 2;
    label.at<uchar>(372, 30) = 3;
    label.at<uchar>(372, 40) = 4;
    label.at<uchar>(372, 50) = 5;
    label.at<uchar>(372, 60) = 6;
    label.at<uchar>(372, 70) = 7;
    label.at<uchar>(372, 80) = 104;
    label.at<uchar>(369, 70) = 0;

    applyBottomGrassOverridePreservingObstacles(label, 370);

    bool ok = true;
    ok &= expectEqual(label.at<uchar>(372, 10), 0, "bottom label 0 is preserved");
    ok &= expectEqual(label.at<uchar>(372, 20), 2, "bottom grass remains grass");
    ok &= expectEqual(label.at<uchar>(372, 30), 3, "bottom road is preserved");
    ok &= expectEqual(label.at<uchar>(372, 40), 4, "bottom label 4 is preserved");
    ok &= expectEqual(label.at<uchar>(372, 50), 5, "bottom label 5 is preserved");
    ok &= expectEqual(label.at<uchar>(372, 60), 6, "bottom label 6 is preserved");
    ok &= expectEqual(label.at<uchar>(372, 70), 7, "bottom label 7 is preserved");
    ok &= expectEqual(label.at<uchar>(372, 80), 104, "bottom mapped obstacle is preserved");
    ok &= expectEqual(label.at<uchar>(369, 70), 0, "row above forced region is untouched");

    return ok ? 0 : 1;
}
