#include "stereo_point_cloud_rgbl.h"
//#include "perception_common.h"

void stereo_point_cloud::show_xyz_rgbl_plane_point_cloud(pcl::PointCloud<pcl::PointXYZRGBL> xyz_rgbl_cloud, Mat &xyz_rgb,  Mat &xyz_l, Mat &xyz_rgbl){
    pcl::PointCloud<pcl::PointXYZRGBL>::Ptr xyz_rgbl_cloud_ptr = std::make_shared<pcl::PointCloud<pcl::PointXYZRGBL>>(xyz_rgbl_cloud);
    stereo_xyz_rgbl_plane(xyz_rgbl_cloud_ptr, xyz_rgb,  xyz_l, xyz_rgbl);
}

void stereo_point_cloud::show_xyz_rgbl_plane_point_cloud_final(pcl::PointCloud<pcl::PointXYZRGBL> xyz_rgbl_cloud, Mat &xyz_rgbl){
    pcl::PointCloud<pcl::PointXYZRGBL>::Ptr xyz_rgbl_cloud_ptr = std::make_shared<pcl::PointCloud<pcl::PointXYZRGBL>>(xyz_rgbl_cloud);
    stereo_xyz_rgbl_plane_final(xyz_rgbl_cloud_ptr, xyz_rgbl);
}

cv::Mat stereo_point_cloud::getXView_l(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud)
{
    pcl::PointCloud<pcl::PointXYZRGB>::Ptr rgb_cloud(new pcl::PointCloud<pcl::PointXYZRGB>);
    rgb_cloud->width = xyz_rgbl_cloud->width;
    rgb_cloud->height = xyz_rgbl_cloud->height;
    rgb_cloud->is_dense = xyz_rgbl_cloud->is_dense;
    rgb_cloud->points.resize(xyz_rgbl_cloud->points.size());

    int rows=480, cols=640;
//    int rows=640, cols=480;
    Mat img = Mat::zeros(rows, cols, CV_8UC3);

    pcl::PointXYZRGBL p_max, p_min;
    pcl::getMinMax3D(*xyz_rgbl_cloud, p_min, p_max);

    float zScale = round(cols/(p_max.z - p_min.z));
    float yScale = round(rows/(p_max.y - p_min.y));

    // ⚠️ 分层绘制策略：先画label==1/2/3，再画label==2，最后画其他类别
    // 第一遍：绘制 label==1, 2, 3（背景、草地、道路）
    for (std::size_t i = 0; i < xyz_rgbl_cloud->points.size(); ++i)
    {
        const pcl::PointXYZRGBL& ipoint = xyz_rgbl_cloud->points[i];
        if (ipoint.label != 1 && ipoint.label != 2 && ipoint.label != 3) continue;

        pcl::PointXYZRGB& point_rgb = rgb_cloud->points[i];
        point_rgb.y = ipoint.y;
        point_rgb.z = ipoint.z;
        int v = ipoint.label;

        int c = static_cast<int>(round(zScale*(point_rgb.z - p_min.z)));
        int r = static_cast<int>(round(yScale*(point_rgb.y - p_min.y)));

        if (r < 0 || r >= img.rows || c < 0 || c >= img.cols)
            continue;

        cv::circle(img, cv::Point(c, r), 1, colorMap[v], -1);
    }

    // 第二遍：单独绘制 label==2（草地），确保可见
    for (std::size_t i = 0; i < xyz_rgbl_cloud->points.size(); ++i)
    {
        const pcl::PointXYZRGBL& ipoint = xyz_rgbl_cloud->points[i];
        if (ipoint.label != 2) continue;

        pcl::PointXYZRGB& point_rgb = rgb_cloud->points[i];
        point_rgb.y = ipoint.y;
        point_rgb.z = ipoint.z;
        int v = ipoint.label;

        int c = static_cast<int>(round(zScale*(point_rgb.z - p_min.z)));
        int r = static_cast<int>(round(yScale*(point_rgb.y - p_min.y)));

        if (r < 0 || r >= img.rows || c < 0 || c >= img.cols)
            continue;

        cv::circle(img, cv::Point(c, r), 1, colorMap[v], -1);  // 稍大半径
    }

    // 第三遍：绘制其他所有类别（叠加在最上层）
    for (std::size_t i = 0; i < xyz_rgbl_cloud->points.size(); ++i)
    {
        const pcl::PointXYZRGBL& ipoint = xyz_rgbl_cloud->points[i];
        if (ipoint.label == 1 || ipoint.label == 2 || ipoint.label == 3) continue;

        pcl::PointXYZRGB& point_rgb = rgb_cloud->points[i];
        point_rgb.y = ipoint.y;
        point_rgb.z = ipoint.z;
        int v = ipoint.label;

        int c = static_cast<int>(round(zScale*(point_rgb.z - p_min.z)));
        int r = static_cast<int>(round(yScale*(point_rgb.y - p_min.y)));

        if (r < 0 || r >= img.rows || c < 0 || c >= img.cols)
            continue;

        cv::circle(img, cv::Point(c, r), 1, colorMap[v], -1);
    }
    return img;
};

cv::Mat stereo_point_cloud::getXView_rgb(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud)
{
    pcl::PointCloud<pcl::PointXYZRGB>::Ptr rgb_cloud(new pcl::PointCloud<pcl::PointXYZRGB>);
    rgb_cloud->width = xyz_rgbl_cloud->width;
    rgb_cloud->height = xyz_rgbl_cloud->height;
    rgb_cloud->is_dense = xyz_rgbl_cloud->is_dense;
    rgb_cloud->points.resize(xyz_rgbl_cloud->points.size());

    int rows=480, cols=640;
//    int rows=640, cols=480;
    Mat img = Mat::zeros(rows, cols, CV_8UC3);

    pcl::PointXYZRGBL p_max, p_min;
    pcl::getMinMax3D(*xyz_rgbl_cloud, p_min, p_max);

    float zScale = round(cols/(p_max.z - p_min.z));
    float yScale = round(rows/(p_max.y - p_min.y));

    for (std::size_t i = 0; i < xyz_rgbl_cloud->points.size(); ++i)
    {
        pcl::PointXYZRGB& point_rgb = rgb_cloud->points[i];
        const pcl::PointXYZRGBL& ipoint = xyz_rgbl_cloud->points[i];

        union {
            float rgb_float;
            uint32_t rgb_packed;
        } converter;

        point_rgb.x = ipoint.x;
        point_rgb.y = ipoint.y;
        point_rgb.z = ipoint.z;

        //point_rgb.rgb = ipoint.rgb;

        converter.rgb_float = ipoint.rgb;
        uint32_t rgb_packed = converter.rgb_packed;
        uint8_t red = (rgb_packed >> 16) & 0xFF;
        uint8_t green = (rgb_packed >> 8) & 0xFF;
        uint8_t blue = rgb_packed & 0xFF;

        // 设置图像像素颜色
        //output_image.at<cv::Vec3b>(v, u) = cv::Vec3b(b, g, r);

        //point_rgb.g = ipoint.g;
        //point_rgb.b = ipoint.b;
        int v = ipoint.label;

        // 修复：Z映射到列(c)，Y映射到行(r)
        // ⚠️ Y轴正值映射：Y小(地面)在图像底部(r大)，直接映射Y->r
        int c = static_cast<int>(round(zScale*(point_rgb.z - p_min.z)));  // Z正常映射
        int r = static_cast<int>(round(yScale*(point_rgb.y - p_min.y)));  // Y正常映射

        if (r < 0 || r >= img.rows || c < 0 || c >= img.cols)
            continue;

        cv::circle(img, cv::Point(c, r), 1, cv::Vec3b(blue, green, red), -1);  // 增大半径到2
    }
    return img;
};

cv::Mat stereo_point_cloud::getYView_l(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud)
{
    pcl::PointCloud<pcl::PointXYZRGB>::Ptr rgb_cloud(new pcl::PointCloud<pcl::PointXYZRGB>);
    rgb_cloud->width = xyz_rgbl_cloud->width;
    rgb_cloud->height = xyz_rgbl_cloud->height;
    rgb_cloud->is_dense = xyz_rgbl_cloud->is_dense;
    rgb_cloud->points.resize(xyz_rgbl_cloud->points.size());

    int rows=480, cols=640;
    Mat img = Mat::zeros(rows, cols, CV_8UC3);

    pcl::PointXYZRGBL p_max, p_min;
    pcl::getMinMax3D(*xyz_rgbl_cloud, p_min, p_max);

    float zScale = round(rows/(p_max.z - p_min.z));  // Z映射到行
    float xScale = round(cols/(p_max.x - p_min.x));  // X映射到列

    // ⚠️ 修复：分两次绘制，先绘制非label==2的点，再绘制label==2确保草地可见
    // 第一遍：绘制所有非label==2的点
    for (std::size_t i = 0; i < xyz_rgbl_cloud->points.size(); ++i)
    {
        const pcl::PointXYZRGBL& ipoint = xyz_rgbl_cloud->points[i];
        if (ipoint.label == 2) continue;  // 跳过草地，稍后绘制

        pcl::PointXYZRGB& point_rgb = rgb_cloud->points[i];
        point_rgb.x = ipoint.x;
        point_rgb.y = ipoint.y;
        point_rgb.z = ipoint.z;
        int v = ipoint.label;

        // 修复：Z映射到行(r)，X映射到列(c)
        // ⚠️ 翻转Z轴：让近处(Z小)显示在图像底部(r大)
        int r = static_cast<int>(round(zScale*(p_max.z - point_rgb.z)));  // 翻转
        int c = static_cast<int>(round(xScale*(point_rgb.x - p_min.x)));

        if (r < 0 || r >= img.rows || c < 0 || c >= img.cols)
            continue;

        cv::circle(img, cv::Point(c, r), 1, colorMap[v], -1);
    }

    // 第二遍：绘制label==2的草地点，确保在最上层
    for (std::size_t i = 0; i < xyz_rgbl_cloud->points.size(); ++i)
    {
        const pcl::PointXYZRGBL& ipoint = xyz_rgbl_cloud->points[i];
        if (ipoint.label != 2) continue;  // 只绘制草地

        pcl::PointXYZRGB& point_rgb = rgb_cloud->points[i];
        point_rgb.x = ipoint.x;
        point_rgb.y = ipoint.y;
        point_rgb.z = ipoint.z;
        int v = ipoint.label;

        // 修复：Z映射到行(r)，X映射到列(c)
        // ⚠️ 翻转Z轴：让近处(Z小)显示在图像底部(r大)
        int r = static_cast<int>(round(zScale*(p_max.z - point_rgb.z)));  // 翻转
        int c = static_cast<int>(round(xScale*(point_rgb.x - p_min.x)));

        if (r < 0 || r >= img.rows || c < 0 || c >= img.cols)
            continue;

        // 草地使用稍大的半径确保可见
        cv::circle(img, cv::Point(c, r), 1, colorMap[v], -1);
    }

    // ✅ 修复：移除所有变换，直接返回俯视图
    // YView是俯视图(从上往下看)，不需要flip/rotate变换
    // Z轴(深度) -> 行, X轴(水平) -> 列
    // ⚠️ Z轴翻转：近处(Z小)在图像底部，远处(Z大)在图像顶部

    cv::Scalar white(255, 255, 255);
    cv::line(img, cv::Point(0, 0), cv::Point(0, img.rows), white, 2);
    cv::line(img, cv::Point(img.cols - 1, 0), cv::Point(img.cols - 1, img.rows), white, 2);
    return img;
};

cv::Mat stereo_point_cloud::getYView_rgb(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud)
{
    pcl::PointCloud<pcl::PointXYZRGB>::Ptr rgb_cloud(new pcl::PointCloud<pcl::PointXYZRGB>);
    rgb_cloud->width = xyz_rgbl_cloud->width;
    rgb_cloud->height = xyz_rgbl_cloud->height;
    rgb_cloud->is_dense = xyz_rgbl_cloud->is_dense;
    rgb_cloud->points.resize(xyz_rgbl_cloud->points.size());

    int rows=480, cols=640;
    Mat img = Mat::zeros(rows, cols, CV_8UC3);

    pcl::PointXYZRGBL p_max, p_min;
    pcl::getMinMax3D(*xyz_rgbl_cloud, p_min, p_max);

    float zScale = round(rows/(p_max.z - p_min.z));  // Z映射到行
    float xScale = round(cols/(p_max.x - p_min.x));  // X映射到列

    // ⚠️ 修复：分两次绘制，先绘制非label==2的点，再绘制label==2确保草地可见
    // 第一遍：绘制所有非label==2的点
    for (std::size_t i = 0; i < xyz_rgbl_cloud->points.size(); ++i)
    {
        const pcl::PointXYZRGBL& ipoint = xyz_rgbl_cloud->points[i];
        if (ipoint.label == 2) continue;  // 跳过草地，稍后绘制

        pcl::PointXYZRGB& point_rgb = rgb_cloud->points[i];

        union {
            float rgb_float;
            uint32_t rgb_packed;
        } converter;

        point_rgb.x = ipoint.x;
        point_rgb.y = ipoint.y;
        point_rgb.z = ipoint.z;

        converter.rgb_float = ipoint.rgb;
        uint32_t rgb_packed = converter.rgb_packed;
        uint8_t red = (rgb_packed >> 16) & 0xFF;
        uint8_t green = (rgb_packed >> 8) & 0xFF;
        uint8_t blue = rgb_packed & 0xFF;

        int v = ipoint.label;

        // 修复：Z映射到行(r)，X映射到列(c)
        // ⚠️ 翻转Z轴：让近处(Z小)显示在图像底部(r大)
        int r = static_cast<int>(round(zScale*(p_max.z - point_rgb.z)));  // 翻转
        int c = static_cast<int>(round(xScale*(point_rgb.x - p_min.x)));

        if (r < 0 || r >= img.rows || c < 0 || c >= img.cols)
            continue;

        cv::circle(img, cv::Point(c, r), 1, cv::Vec3b(blue, green, red), -1);
    }

    // 第二遍：绘制label==2的草地点，确保在最上层
    for (std::size_t i = 0; i < xyz_rgbl_cloud->points.size(); ++i)
    {
        const pcl::PointXYZRGBL& ipoint = xyz_rgbl_cloud->points[i];
        if (ipoint.label != 2) continue;  // 只绘制草地

        pcl::PointXYZRGB& point_rgb = rgb_cloud->points[i];

        union {
            float rgb_float;
            uint32_t rgb_packed;
        } converter;

        point_rgb.x = ipoint.x;
        point_rgb.y = ipoint.y;
        point_rgb.z = ipoint.z;

        converter.rgb_float = ipoint.rgb;
        uint32_t rgb_packed = converter.rgb_packed;
        uint8_t red = (rgb_packed >> 16) & 0xFF;
        uint8_t green = (rgb_packed >> 8) & 0xFF;
        uint8_t blue = rgb_packed & 0xFF;

        int v = ipoint.label;

        // 修复：Z映射到行(r)，X映射到列(c)
        // ⚠️ 翻转Z轴：让近处(Z小)显示在图像底部(r大)
        int r = static_cast<int>(round(zScale*(p_max.z - point_rgb.z)));  // 翻转
        int c = static_cast<int>(round(xScale*(point_rgb.x - p_min.x)));

        if (r < 0 || r >= img.rows || c < 0 || c >= img.cols)
            continue;

        // 草地使用稍大的半径确保可见
        cv::circle(img, cv::Point(c, r), 1, cv::Vec3b(blue, green, red), -1);
    }

    // ✅ 修复：移除所有变换，直接返回俯视图
    // YView是俯视图(从上往下看)，不需要flip/rotate变换
    // Z轴(深度) -> 行, X轴(水平) -> 列
    // ⚠️ Z轴翻转：近处(Z小)在图像底部，远处(Z大)在图像顶部

    cv::Scalar white(255, 255, 255);
    cv::line(img, cv::Point(0, 0), cv::Point(0, img.rows), white, 2);
    cv::line(img, cv::Point(img.cols - 1, 0), cv::Point(img.cols - 1, img.rows), white, 2);
    return img;
};

cv::Mat stereo_point_cloud::getZView_l(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud)
{
    pcl::PointCloud<pcl::PointXYZRGB>::Ptr rgb_cloud(new pcl::PointCloud<pcl::PointXYZRGB>);
    rgb_cloud->width = xyz_rgbl_cloud->width;
    rgb_cloud->height = xyz_rgbl_cloud->height;
    rgb_cloud->is_dense = xyz_rgbl_cloud->is_dense;
    rgb_cloud->points.resize(xyz_rgbl_cloud->points.size());

    int rows=480, cols=640;
    Mat img = Mat::zeros(rows, cols, CV_8UC3);

    pcl::PointXYZRGBL p_max, p_min;
    pcl::getMinMax3D(*xyz_rgbl_cloud, p_min, p_max);

    // 修复：调整缩放比例，Y映射到行（垂直），X映射到列（水平）
    float xScale = round(cols/(p_max.x - p_min.x));
    float yScale = round(rows/(p_max.y - p_min.y));

    int points_drawn = 0;
    int points_out_of_bounds = 0;

    // ⚠️ 分层绘制策略：先画label==1/2/3，再画label==2，最后画其他类别
    // 第一遍：绘制 label==1, 2, 3（背景、草地、道路）
    for (std::size_t i = 0; i < xyz_rgbl_cloud->points.size(); ++i)
    {
        const pcl::PointXYZRGBL& ipoint = xyz_rgbl_cloud->points[i];
        if (ipoint.label != 1 && ipoint.label != 2 && ipoint.label != 3) continue;

        pcl::PointXYZRGB& point_rgb = rgb_cloud->points[i];
        point_rgb.x = ipoint.x;
        point_rgb.y = ipoint.y;
        int v = ipoint.label;

        int c = static_cast<int>(round(xScale*(point_rgb.x - p_min.x)));
        int r = static_cast<int>(round(yScale*(point_rgb.y - p_min.y)));

        if (r < 0 || r >= img.rows || c < 0 || c >= img.cols) {
            points_out_of_bounds++;
            continue;
        }
        cv::circle(img, cv::Point(c, r), 1, colorMap[v], -1);
        points_drawn++;
    }

    // 第二遍：单独绘制 label==2（草地），确保可见
    for (std::size_t i = 0; i < xyz_rgbl_cloud->points.size(); ++i)
    {
        const pcl::PointXYZRGBL& ipoint = xyz_rgbl_cloud->points[i];
        if (ipoint.label != 2) continue;

        pcl::PointXYZRGB& point_rgb = rgb_cloud->points[i];
        point_rgb.x = ipoint.x;
        point_rgb.y = ipoint.y;
        int v = ipoint.label;

        int c = static_cast<int>(round(xScale*(point_rgb.x - p_min.x)));
        int r = static_cast<int>(round(yScale*(point_rgb.y - p_min.y)));

        if (r < 0 || r >= img.rows || c < 0 || c >= img.cols) {
            points_out_of_bounds++;
            continue;
        }
        cv::circle(img, cv::Point(c, r), 1, colorMap[v], -1);  // 稍大半径
        points_drawn++;
    }

    // 第三遍：绘制其他所有类别（叠加在最上层）
    for (std::size_t i = 0; i < xyz_rgbl_cloud->points.size(); ++i)
    {
        const pcl::PointXYZRGBL& ipoint = xyz_rgbl_cloud->points[i];
        if (ipoint.label == 1 || ipoint.label == 2 || ipoint.label == 3) continue;

        pcl::PointXYZRGB& point_rgb = rgb_cloud->points[i];
        point_rgb.x = ipoint.x;
        point_rgb.y = ipoint.y;
        int v = ipoint.label;

        int c = static_cast<int>(round(xScale*(point_rgb.x - p_min.x)));
        int r = static_cast<int>(round(yScale*(point_rgb.y - p_min.y)));

        if (r < 0 || r >= img.rows || c < 0 || c >= img.cols) {
            points_out_of_bounds++;
            continue;
        }
        cv::circle(img, cv::Point(c, r), 1, colorMap[v], -1);
        points_drawn++;
    }

    return img;
};

cv::Mat stereo_point_cloud::getZView_rgb(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr &xyz_rgbl_cloud)
{
    pcl::PointCloud<pcl::PointXYZRGB>::Ptr rgb_cloud(new pcl::PointCloud<pcl::PointXYZRGB>);
    rgb_cloud->width = xyz_rgbl_cloud->width;
    rgb_cloud->height = xyz_rgbl_cloud->height;
    rgb_cloud->is_dense = xyz_rgbl_cloud->is_dense;
    rgb_cloud->points.resize(xyz_rgbl_cloud->points.size());

    int rows=480, cols=640;
    Mat img = Mat::zeros(rows, cols, CV_8UC3);

    pcl::PointXYZRGBL p_max, p_min;
    pcl::getMinMax3D(*xyz_rgbl_cloud, p_min, p_max);

    float xScale = round(cols/(p_max.x - p_min.x));
    float yScale = round(rows/(p_max.y - p_min.y));

    for (std::size_t i = 0; i < xyz_rgbl_cloud->points.size(); ++i)
    {
        pcl::PointXYZRGB& point_rgb = rgb_cloud->points[i];
        const pcl::PointXYZRGBL& ipoint = xyz_rgbl_cloud->points[i];

        union {
            float rgb_float;
            uint32_t rgb_packed;
        } converter;

        point_rgb.x = ipoint.x;
        point_rgb.y = ipoint.y;
//        point_rgb.z = ipoint.z;

        converter.rgb_float = ipoint.rgb;
        uint32_t rgb_packed = converter.rgb_packed;
        uint8_t red = (rgb_packed >> 16) & 0xFF;
        uint8_t green = (rgb_packed >> 8) & 0xFF;
        uint8_t blue = rgb_packed & 0xFF;

        int v = ipoint.label;

        // 修复：X映射到列(c)，Y映射到行(r)
        // ⚠️ Y轴正值映射：Y小在图像底部(r大)，直接映射Y->r
        int c = static_cast<int>(round(xScale*(point_rgb.x - p_min.x)));  // X正常映射
        int r = static_cast<int>(round(yScale*(point_rgb.y - p_min.y)));  // Y正常映射

        if (r < 0 || r >= img.rows || c < 0 || c >= img.cols)
            continue;

        cv::circle(img, cv::Point(c, r), 1, cv::Vec3b(blue, green, red), -1);  // 增大半径到2
    }
    return img;
};

void stereo_point_cloud::stereo_xyz_rgbl_plane(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr& xyz_rgbl_cloud, Mat &xyz_rgb,  Mat &xyz_l, Mat &xyz_rgbl){
//    // 示例类别与颜色映射
//    colorMap[1] = cv::Scalar(200, 0, 0);  //BGR background blue
//    colorMap[2] = cv::Scalar(102, 255, 102);  //BGR grass green
//    colorMap[3] = cv::Scalar(0, 89, 118);        //BGR road brown
//    colorMap[4] = cv::Scalar(0, 255, 255);      //BGR dynamic yellow
//    colorMap[5] = cv::Scalar(0, 0, 255);    //BGR obstacle red
//
//    colorMap[100] = cv::Scalar(136, 17, 255);   //pole
//    colorMap[101] = cv::Scalar(17, 214, 228);   //car
//    colorMap[102] = cv::Scalar(136, 17, 255);   //tree
//    colorMap[103] = cv::Scalar(136, 17, 255); //fixo
//    colorMap[104] = cv::Scalar(136, 17, 255); //stac
//    colorMap[105] = cv::Scalar(17, 214, 228); //dyna

    // 初始化颜色映射 (BGR格式)
    colorMap[0] = cv::Scalar(119, 119, 119);  // 灰色
    colorMap[1] = cv::Scalar(200, 0, 0);      // 类别 1: background 蓝色
    colorMap[2] = cv::Scalar(102, 255, 100);  // 类别 2: grass 绿色
    colorMap[3] = cv::Scalar(0, 89, 118);     // 类别 3: road 褐色
    colorMap[4] = cv::Scalar(0, 255, 255);    // 类别 4: dynamic 黄色
    colorMap[5] = cv::Scalar(0, 0, 255);      // 类别 5: static_obstacle 红色
    colorMap[6] = cv::Scalar(0, 165, 255);    // 类别 6: wall obstacle 墙面类障碍物（亮橙色）
    colorMap[7] = cv::Scalar(147, 20, 255);   // 类别 7: vehicle obstacle 车辆类障碍物（洋红）
    colorMap[8] = cv::Scalar(255, 255, 0);    // 类别 8: pole 杆子类障碍物（青色）
    colorMap[9] = cv::Scalar(48, 130, 245);   // 类别 9: impassable obstacle 不可通行类障碍物（深天蓝）
    colorMap[10] = cv::Scalar(128, 64, 0);    // 类别 10: depression obstacle 凹陷类障碍物（棕色）
    colorMap[11] = cv::Scalar(34, 139, 34);   // 类别 11: grass_bush 草类灌木（森林绿）
    colorMap[12] = cv::Scalar(203, 192, 255); // 类别 12: limb_bush 枝干结构灌木（浅紫）
    colorMap[13] = cv::Scalar(226, 43, 138); // 类别 13: grass_ground 枝干结构灌木（浅紫）

    colorMap[100] = cv::Scalar(255, 255, 0);
    colorMap[101] = cv::Scalar(0, 0, 255);
    colorMap[102] = cv::Scalar(0, 0, 255);
    colorMap[103] = cv::Scalar(255, 255, 0);
    colorMap[104] = cv::Scalar(0, 0, 255);
    colorMap[105] = cv::Scalar(0, 255, 255);
    colorMap[106] = cv::Scalar(0, 0, 255);
    colorMap[107] = cv::Scalar(0, 255, 255);

    cv::Mat x_Image_l = getXView_l(xyz_rgbl_cloud);
    cv::Mat y_Image_l = getYView_l(xyz_rgbl_cloud);  // 旋转后是640x480
    cv::Mat z_Image_l = getZView_l(xyz_rgbl_cloud);

    // YView旋转后尺寸变化，需要resize回480x640以匹配其他视图
    cv::resize(y_Image_l, y_Image_l, cv::Size(640, 480));

//    imwrite("x_Image_l.jpg", x_Image_l);
//    imwrite("y_Image_l.jpg", y_Image_l);
//    imwrite("z_Image_l.jpg", z_Image_l);

    cv::hconcat(x_Image_l, y_Image_l, xyz_l);  // 拼接图片1和图片2
    cv::hconcat(xyz_l, z_Image_l, xyz_l); // 再将图片3拼接到结果中

//    imwrite("xyz_l.jpg", xyz_l);

    cv::Mat x_Image_rgb = getXView_rgb(xyz_rgbl_cloud);
    cv::Mat y_Image_rgb = getYView_rgb(xyz_rgbl_cloud);  // 旋转后是640x480
    cv::Mat z_Image_rgb = getZView_rgb(xyz_rgbl_cloud);

    // YView RGB版本也需要resize
    cv::resize(y_Image_rgb, y_Image_rgb, cv::Size(640, 480));

//    imwrite("x_Image_l.jpg", x_Image_l);
//    imwrite("y_Image_l.jpg", y_Image_l);
//    imwrite("z_Image_l.jpg", z_Image_l);

    cv::hconcat(x_Image_rgb, y_Image_rgb, xyz_rgb);  // 拼接图片1和图片2
    cv::hconcat(xyz_rgb, z_Image_rgb, xyz_rgb); // 再将图片3拼接到结果中

//    imwrite("xyz_rgb.jpg", xyz_rgb);

    cv::vconcat(xyz_l, xyz_rgb, xyz_rgbl); // 再将图片3拼接到结果中
    cv::line(xyz_rgbl, cv::Point(0, 480), cv::Point(1920, 480), Scalar(255, 255, 255), 2);
//    cv::line(img, cv::Point(640 - 1, 0), cv::Point(640 - 1, 480), white, 2);

//    imwrite("xyz_rgbl.jpg", xyz_rgbl);
}


void stereo_point_cloud::stereo_xyz_rgbl_plane_final(pcl::PointCloud<pcl::PointXYZRGBL>::Ptr& xyz_rgbl_cloud, Mat &xyz_rgbl){
    // 示例类别与颜色映射
    colorMap[0] = cv::Scalar(119, 119, 119);  // 灰色
    colorMap[1] = cv::Scalar(200, 0, 0);      // 类别 1: background 蓝色
    colorMap[2] = cv::Scalar(102, 255, 100);  // 类别 2: grass 绿色
    colorMap[3] = cv::Scalar(0, 89, 118);     // 类别 3: road 褐色
    colorMap[4] = cv::Scalar(0, 255, 255);    // 类别 4: dynamic 黄色
    colorMap[5] = cv::Scalar(0, 0, 255);      // 类别 5: static_obstacle 红色
    colorMap[6] = cv::Scalar(0, 165, 255);    // 类别 6: wall obstacle 墙面类障碍物（亮橙色）
    colorMap[7] = cv::Scalar(147, 20, 255);   // 类别 7: vehicle obstacle 车辆类障碍物（洋红）
    colorMap[8] = cv::Scalar(255, 255, 0);    // 类别 8: pole 杆子类障碍物（青色）
    colorMap[9] = cv::Scalar(48, 130, 245);   // 类别 9: impassable obstacle 不可通行类障碍物（深天蓝）
    colorMap[10] = cv::Scalar(128, 64, 0);    // 类别 10: depression obstacle 凹陷类障碍物（棕色）
    colorMap[11] = cv::Scalar(34, 139, 34);   // 类别 11: grass_bush 草类灌木（森林绿）
    colorMap[12] = cv::Scalar(203, 192, 255); // 类别 12: limb_bush 枝干结构灌木（浅紫）
    colorMap[13] = cv::Scalar(226, 43, 138); // 类别 13: grass_ground 枝干结构灌木（浅紫）

    colorMap[100] = cv::Scalar(255, 255, 0);
    colorMap[101] = cv::Scalar(0, 0, 255);
    colorMap[102] = cv::Scalar(0, 0, 255);
    colorMap[103] = cv::Scalar(255, 255, 0);
    colorMap[104] = cv::Scalar(0, 0, 255);
    colorMap[105] = cv::Scalar(0, 255, 255);
    colorMap[106] = cv::Scalar(0, 0, 255);
    colorMap[107] = cv::Scalar(0, 255, 255);

    cv::Mat x_Image_l = getXView_l(xyz_rgbl_cloud);
    cv::Mat y_Image_l = getYView_l(xyz_rgbl_cloud);  // 旋转后是640x480
    cv::Mat z_Image_l = getZView_l(xyz_rgbl_cloud);

    // YView旋转后尺寸变化，需要resize回480x640
    cv::resize(y_Image_l, y_Image_l, cv::Size(640, 480));

    Mat xyz_l;
    cv::hconcat(x_Image_l, y_Image_l, xyz_l);  // 拼接图片1和图片2
    cv::hconcat(xyz_l, z_Image_l, xyz_l); // 再将图片3拼接到结果中

    cv::Mat x_Image_rgb = getXView_rgb(xyz_rgbl_cloud);
    cv::Mat y_Image_rgb = getYView_rgb(xyz_rgbl_cloud);  // 旋转后是640x480
    cv::Mat z_Image_rgb = getZView_rgb(xyz_rgbl_cloud);

    // YView RGB版本也需要resize
    cv::resize(y_Image_rgb, y_Image_rgb, cv::Size(640, 480));

    Mat xyz_rgb;
    cv::hconcat(x_Image_rgb, y_Image_rgb, xyz_rgb);  // 拼接图片1和图片2
    cv::hconcat(xyz_rgb, z_Image_rgb, xyz_rgb); // 再将图片3拼接到结果中

    cv::vconcat(xyz_l, xyz_rgb, xyz_rgbl); // 再将图片3拼接到结果中
    cv::line(xyz_rgbl, cv::Point(0, 480), cv::Point(1920, 480), Scalar(255, 255, 255), 2);
}