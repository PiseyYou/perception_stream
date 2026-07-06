#include "semantic_depth_utils.hpp"

#include <opencv2/opencv.hpp>

#include <cmath>
#include <iostream>

namespace {

bool expectNear(float actual, float expected, float eps, const char* message) {
    if (std::fabs(actual - expected) <= eps) {
        return true;
    }
    std::cerr << message << ": expected " << expected << ", got " << actual << '\n';
    return false;
}

bool expectEqual(float actual, float expected, const char* message) {
    if (actual == expected) {
        return true;
    }
    std::cerr << message << ": expected " << expected << ", got " << actual << '\n';
    return false;
}

}  // namespace

int main() {
    bool ok = true;

    ok &= expectEqual(isBottomSemanticRepairRegion(640, 432, 260, 300),
                      true,
                      "bottom-center obstacle repair region is enabled for match_0264-style gaps");
    ok &= expectEqual(isBottomSemanticRepairRegion(640, 432, 520, 360),
                      true,
                      "right-bottom obstacle repair region remains enabled");
    ok &= expectEqual(isBottomSemanticRepairRegion(640, 432, 260, 200),
                      false,
                      "upper image region is not included in bottom repair");
    ok &= expectEqual(isBottomSemanticRepairRegion(640, 432, 40, 360),
                      false,
                      "far-left bottom edge is not included in widened repair");
    ok &= expectEqual(shouldSampleSemanticPointPixel(640, 432, 260, 301, 6),
                      true,
                      "semantic point sampling keeps expected bottom obstacle coverage");
    ok &= expectEqual(shouldSampleSemanticPointPixel(640, 432, 260, 301, 2),
                      false,
                      "bottom grass pixels should not inherit obstacle dense sampling");
    ok &= expectEqual(shouldSampleSemanticPointPixel(640, 432, 520, 360, 6),
                      true,
                      "bottom-right obstacle pixels remain eligible for dense sampling");
    ok &= expectEqual(shouldSampleBottomSemanticContactPointPixel(640, 432, 260, 380, 6),
                      true,
                      "bottom contact band obstacle pixels are sampled densely");
    ok &= expectEqual(shouldSampleBottomSemanticContactPointPixel(640, 432, 260, 380, 2),
                      false,
                      "bottom grass pixels are not promoted into the contact-band sampler");
    ok &= expectEqual(shouldSampleBottomSemanticContactPointPixel(640, 432, 260, 300, 6),
                      false,
                      "upper obstacle pixels do not enter the contact-band sampler");
    ok &= expectEqual(shouldSampleBottomSemanticContactPointPixel(640, 432, 40, 380, 6),
                      false,
                      "far-left bottom pixels remain excluded from contact-band sampling");
    ok &= expectEqual(shouldFilterBottomGroundEdge(640, 432, 40, 360, 2),
                      true,
                      "far-left bottom ground edge can still be filtered");
    ok &= expectEqual(shouldFilterBottomGroundEdge(640, 432, 600, 360, 6),
                      false,
                      "bottom obstacle labels are never removed by ground edge filtering");

    cv::Mat boundary_label(432, 640, CV_8UC1, cv::Scalar(2));
    for (int y = 300; y < 340; ++y) {
        for (int x = 460; x < 620; ++x) {
            boundary_label.at<uchar>(y, x) = 6;
        }
    }
    ok &= expectEqual(shouldRepairLabel6GrassBoundaryPointPixel(boundary_label, 510, 339),
                      true,
                      "label 6 fence pixels adjacent to grass are repaired at the semantic boundary");
    ok &= expectEqual(shouldRepairLabel6GrassBoundaryPointPixel(boundary_label, 510, 320),
                      false,
                      "interior label 6 pixels are not artificially filled by a preset grid");

    cv::Mat natural_depth(432, 640, CV_32FC1, cv::Scalar(100.0f));
    cv::Mat natural_label(432, 640, CV_8UC1, cv::Scalar(2));
    for (int y = 300; y < 360; ++y) {
        for (int x = 460; x < 560; ++x) {
            natural_label.at<uchar>(y, x) = 6;
        }
    }
    natural_depth.at<float>(328, 498) = 1.00f;
    natural_depth.at<float>(329, 501) = 1.05f;
    natural_depth.at<float>(331, 497) = 1.10f;
    natural_depth.at<float>(332, 502) = 1.15f;
    ok &= expectNear(findNaturalSameLabelRepairDepth(natural_depth, natural_label, 500, 330, 6),
                     1.08f, 0.12f,
                     "natural repair interpolates only from local same-label point support");

    cv::Mat depth(20, 20, CV_32FC1, cv::Scalar(100.0f));
    cv::Mat label(20, 20, CV_8UC1, cv::Scalar(2));

    for (int y = 6; y < 14; ++y) {
        for (int x = 6; x < 14; ++x) {
            label.at<uchar>(y, x) = 6;
        }
    }
    depth.at<float>(7, 7) = 1.0f;
    depth.at<float>(7, 8) = 1.1f;
    depth.at<float>(8, 7) = 1.2f;
    depth.at<float>(8, 8) = 1.3f;
    depth.at<float>(9, 9) = 1.4f;
    depth.at<float>(9, 10) = 1.5f;
    depth.at<float>(10, 9) = 1.6f;
    depth.at<float>(10, 10) = 1.7f;

    cv::Mat filled = inpaintSemanticObstacleDepth(depth, label);

    ok &= expectNear(filled.at<float>(12, 12), 1.5f, 0.31f,
                     "label 6 hole is filled from local semantic depth support");
    ok &= expectEqual(filled.at<float>(2, 2), 100.0f,
                      "non-obstacle depth is unchanged");

    cv::Mat gradient_depth(16, 16, CV_32FC1, cv::Scalar(100.0f));
    cv::Mat gradient_label(16, 16, CV_8UC1, cv::Scalar(2));
    for (int y = 4; y < 12; ++y) {
        for (int x = 3; x < 13; ++x) {
            gradient_label.at<uchar>(y, x) = 6;
        }
    }
    for (int y = 4; y < 12; ++y) {
        gradient_depth.at<float>(y, 3) = 0.8f;
        gradient_depth.at<float>(y, 4) = 0.9f;
        gradient_depth.at<float>(y, 11) = 1.5f;
        gradient_depth.at<float>(y, 12) = 1.6f;
    }

    cv::Mat gradient_filled = inpaintSemanticObstacleDepth(gradient_depth, gradient_label);
    ok &= expectNear(gradient_filled.at<float>(8, 5), 0.9f, 0.21f,
                     "left side invalid obstacle depth follows local support");
    ok &= expectNear(gradient_filled.at<float>(8, 10), 1.5f, 0.21f,
                     "right side invalid obstacle depth follows local support");
    ok &= expectEqual(std::fabs(gradient_filled.at<float>(8, 5) -
                                gradient_filled.at<float>(8, 10)) > 0.3f,
                      true,
                      "semantic inpainting should not flatten a wide obstacle component to one depth");

    cv::Mat wide_depth(16, 40, CV_32FC1, cv::Scalar(100.0f));
    cv::Mat wide_label(16, 40, CV_8UC1, cv::Scalar(2));
    for (int y = 4; y < 12; ++y) {
        for (int x = 3; x < 36; ++x) {
            wide_label.at<uchar>(y, x) = 6;
        }
        wide_depth.at<float>(y, 3) = 0.8f;
        wide_depth.at<float>(y, 4) = 0.9f;
        wide_depth.at<float>(y, 34) = 1.5f;
        wide_depth.at<float>(y, 35) = 1.6f;
    }

    cv::Mat wide_filled = inpaintSemanticObstacleDepth(wide_depth, wide_label);
    ok &= expectNear(wide_filled.at<float>(8, 19), 1.2f, 0.31f,
                     "wide obstacle gap is filled by directional local interpolation");
    ok &= expectEqual(wide_filled.at<float>(8, 19) != wide_filled.at<float>(8, 5),
                      true,
                      "directional interpolation should not reuse one constant depth across the component");

    cv::Mat long_gap_depth(20, 96, CV_32FC1, cv::Scalar(100.0f));
    cv::Mat long_gap_label(20, 96, CV_8UC1, cv::Scalar(2));
    for (int y = 8; y < 18; ++y) {
        for (int x = 20; x < 92; ++x) {
            long_gap_label.at<uchar>(y, x) = 6;
        }
        long_gap_depth.at<float>(y, 20) = 0.8f;
        long_gap_depth.at<float>(y, 21) = 0.9f;
        long_gap_depth.at<float>(y, 90) = 1.5f;
        long_gap_depth.at<float>(y, 91) = 1.6f;
    }

    cv::Mat long_gap_filled = inpaintSemanticObstacleDepth(long_gap_depth, long_gap_label);
    ok &= expectNear(long_gap_filled.at<float>(14, 55), 1.2f, 0.31f,
                     "bottom-right obstacle gap with distant semantic support is filled");
    ok &= expectEqual(long_gap_filled.at<float>(14, 55) != long_gap_filled.at<float>(14, 25),
                      true,
                      "long bottom-right fill keeps directional depth variation");

    cv::Mat one_sided_depth(40, 120, CV_32FC1, cv::Scalar(100.0f));
    cv::Mat one_sided_label(40, 120, CV_8UC1, cv::Scalar(2));
    for (int y = 16; y < 36; ++y) {
        for (int x = 30; x < 110; ++x) {
            one_sided_label.at<uchar>(y, x) = 6;
        }
        one_sided_depth.at<float>(y, 30) = 0.8f;
        one_sided_depth.at<float>(y, 31) = 0.9f;
    }

    cv::Mat one_sided_filled = inpaintSemanticObstacleDepth(one_sided_depth, one_sided_label);
    ok &= expectEqual(one_sided_filled.at<float>(26, 90), 100.0f,
                      "wide one-sided semantic gaps are not filled from distant support");
    ok &= expectNear(one_sided_filled.at<float>(26, 34), 0.9f, 0.21f,
                     "nearby same-label support still repairs local obstacle holes");

    cv::Mat sparse_depth(9, 9, CV_32FC1, cv::Scalar(100.0f));
    cv::Mat sparse_label(9, 9, CV_8UC1, cv::Scalar(2));
    for (int y = 3; y < 6; ++y) {
        for (int x = 3; x < 6; ++x) {
            sparse_label.at<uchar>(y, x) = 6;
        }
    }
    sparse_depth.at<float>(4, 3) = 0.9f;
    sparse_depth.at<float>(4, 5) = 1.1f;

    float neighbor = findSemanticNeighborDepth(sparse_depth, sparse_label, 4, 4, 1);
    ok &= expectNear(neighbor, 1.1f, 0.21f,
                     "semantic neighbor depth uses nearby obstacle depths");

    cv::Mat fusion_depth(9, 9, CV_32FC1, cv::Scalar(0.0f));
    cv::Mat fusion_label(9, 9, CV_8UC1, cv::Scalar(2));
    fusion_label.at<uchar>(4, 5) = 6;
    fusion_label.at<uchar>(4, 6) = 6;
    fusion_label.at<uchar>(5, 5) = 6;
    fusion_depth.at<float>(4, 5) = 1.0f;
    fusion_depth.at<float>(4, 6) = 1.1f;
    fusion_depth.at<float>(5, 5) = 1.2f;

    uchar promoted_label = 0;
    float promoted_depth = 0.0f;
    ok &= expectEqual(findNearbyConsistentSemanticObstacle(fusion_depth, fusion_label,
                                                           4, 4, 2, 3, 0.25f,
                                                           promoted_label, promoted_depth),
                      true,
                      "invalid grass near stable obstacle support is promoted");
    ok &= expectEqual(promoted_label, 6, "promoted label comes from semantic obstacle support");
    ok &= expectNear(promoted_depth, 1.1f, 0.11f,
                     "promoted depth comes from nearby obstacle support");

    fusion_depth.at<float>(4, 4) = 0.35f;
    promoted_label = 0;
    promoted_depth = 0.0f;
    ok &= expectEqual(findNearbyConsistentSemanticObstacle(fusion_depth, fusion_label,
                                                           4, 4, 2, 3, 0.25f,
                                                           promoted_label, promoted_depth),
                      false,
                      "valid ground depth far from obstacle support is not promoted");

    cv::Mat noisy_depth(5, 5, CV_32FC1, cv::Scalar(0.0f));
    cv::Mat noisy_label(5, 5, CV_8UC1, cv::Scalar(2));
    noisy_label.at<uchar>(2, 3) = 6;
    noisy_depth.at<float>(2, 3) = 1.0f;
    ok &= expectEqual(findNearbyConsistentSemanticObstacle(noisy_depth, noisy_label,
                                                           2, 2, 1, 3, 0.25f,
                                                           promoted_label, promoted_depth),
                      false,
                      "single obstacle pixel is not enough support");

    return ok ? 0 : 1;
}
