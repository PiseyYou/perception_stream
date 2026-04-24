#include "opencv2/opencv.hpp"
#include <string>
#include <deque>
//#include "det_perception.h"
//#include "seg_perception.h"
//#include "stereo_match.h"
//#include <pcl_conversions/pcl_conversions.h>
//#include <pcl/point_types.h>
//#include <pcl/point_cloud.h>

#include "perception_common.h"

using namespace cv;
using namespace std;

class PerceptionNode {
public:
    PerceptionNode();
//    ~PerceptionNode();

//    StereoMatch stereo_match;

private:
    int count_stereo = 0;
    // bool enable_height_filter_=false;

//    std::string m_det_model_name;               //检测模型名称
//    std::string m_seg_model_name;               //检测模型名称
//    double m_detection_threshold;
//    int m_fusion_model;
//    string m_model_infer_class_file;
//    bool m_enable_debug_show;
//    bool m_enable_side_debug_show;
//    double m_timer_rate_;

//    seg_perception _segPerception;  //推理类
//    det_perception _detPerception; //检测类
//    Mat in_bgr_mat, out_bgr_mat;
//    std::vector<Detection> dect_src;
//    Mat seg_lab;
//    bool _do_detection;

    struct stereoImg {
        Mat stereo_left;
        Mat stereo_right;
//        rclcpp::Time currentTime;
    } stereo_img_;

    void node_param_init();
    void stereoImgInfer(cv::Mat& input_img);

};
