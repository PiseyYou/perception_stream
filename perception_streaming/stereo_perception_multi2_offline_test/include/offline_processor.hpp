#ifndef OFFLINE_PROCESSOR_HPP
#define OFFLINE_PROCESSOR_HPP

#include <opencv2/opencv.hpp>
#include <pcl/point_cloud.h>
#include <pcl/point_types.h>
#include <string>
#include <vector>

// 引入感知模块
#include "dsg_perception.h"
#include "multi_sub_perception.h"
#include "stereo_multi_match.h"
#include "perception_common.h"

// 离线测试专用头文件
#include "offline_config.hpp"
#include "hardware_mode.hpp"

/**
 * @brief 离线感知处理器
 *
 * 封装 DSG 感知、立体匹配、点云融合等功能
 * 支持 K100 和 bestmow 两种硬件模式
 */
class OfflineProcessor {
public:
    /**
     * @brief 构造函数
     * @param config 配置参数
     */
    explicit OfflineProcessor(const OfflineConfig& config);

    /**
     * @brief 析构函数
     */
    ~OfflineProcessor();

    /**
     * @brief 初始化处理器
     * @return true: 成功, false: 失败
     */
    bool init();

    /**
     * @brief 处理结果结构
     */
    struct ProcessResult {
        cv::Mat segmentation;                          // 分割标签图 (CV_8UC1)
        cv::Mat depth;                                 // 深度图 (CV_32FC1)
        cv::Mat cropped_img;                           // 裁剪后的图像（用于可视化）
        std::vector<Detection> detections;             // 检测框（K100 模式）
        pcl::PointCloud<pcl::PointXYZRGBL> pointcloud; // 点云
        bool success = false;                          // 处理是否成功
    };

    /**
     * @brief 处理单张图像
     * @param left_img 左图
     * @param right_img 右图（可为空）
     * @param image_name 图像名称（用于保存）
     * @return 处理结果
     */
    ProcessResult process(const cv::Mat& left_img,
                          const cv::Mat& right_img,
                          const std::string& image_name);

    /**
     * @brief 保存处理结果
     * @param result 处理结果
     * @param image_name 图像名称
     * @param original_img 原始图像（用于绘制检测框）
     */
    void saveResults(const ProcessResult& result,
                     const std::string& image_name,
                     const cv::Mat& original_img);

private:
    OfflineConfig config_;
    HardwareMode hardware_mode_;

    // 感知模块
    multi_perception mul_sub_perception_;  // Model 6
    dsg_perception dsg_perception_;        // Model 7
    StereoMultiMatch stereo_matcher_;

    // 初始化标志
    bool initialized_ = false;

    // 辅助函数
    bool initMulSubPerception();
    bool initDSGPerception();
    bool initStereoMatcher();

    // 模型处理函数
    ProcessResult processModel6(const cv::Mat& left_img,
                                const cv::Mat& right_img,
                                const std::string& image_name);
    ProcessResult processModel7(const cv::Mat& left_img,
                                const cv::Mat& right_img,
                                const std::string& image_name);
};

#endif // OFFLINE_PROCESSOR_HPP
