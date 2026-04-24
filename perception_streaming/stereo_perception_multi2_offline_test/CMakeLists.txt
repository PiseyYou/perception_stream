cmake_minimum_required(VERSION 3.22)
project(stereo_perception_offline_test)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 设置编译选项
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -O3")

# 查找依赖库
find_package(OpenCV REQUIRED)
find_package(PCL REQUIRED COMPONENTS common io filters)

# 根据硬件模式选择不同的源文件
# 默认使用 K100 模式（stereo_perception_multi2）
# 如果需要 bestmow 模式，设置 USE_BESTMOW=ON
option(USE_BESTMOW "Use bestmow mode instead of K100" OFF)

if(USE_BESTMOW)
    message(STATUS "Building with bestmow mode")
    set(PERCEPTION_SRC_DIR ../stereo_perception_multi2_bestmow)
    set(PERCEPTION_INCLUDE_DIR ${CMAKE_SOURCE_DIR}/../stereo_perception_multi2_bestmow/include)
else()
    message(STATUS "Building with K100 mode")
    set(PERCEPTION_SRC_DIR ../stereo_perception_multi2)
    set(PERCEPTION_INCLUDE_DIR ${CMAKE_SOURCE_DIR}/../stereo_perception_multi2/include)
endif()

# 包含目录（perception 头文件目录要放在最前面）
include_directories(
    ${CMAKE_SOURCE_DIR}/include
    ${PERCEPTION_INCLUDE_DIR}
    ${OpenCV_INCLUDE_DIRS}
    ${PCL_INCLUDE_DIRS}
    /usr/include
    /usr/hobot/include
    /home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/include
)

# 链接目录
link_directories(
    ${PERCEPTION_SRC_DIR}/lib
    /usr/lib
    /usr/hobot/lib
    /usr/lib/aarch64-linux-gnu
    /home/youfeng/CLionProjects/05-offline_debug_fusion/deps_gcc11.3/x86/dnn_x86/lib
)

# 源文件
set(SOURCES
    src/offline_test_main.cpp
    src/offline_processor.cpp
    src/stereo_point_cloud_rgbl.cpp
    # 从对应的 perception 模块复用源文件
    ${PERCEPTION_SRC_DIR}/src/dsg_perception.cpp
    ${PERCEPTION_SRC_DIR}/src/multi_sub_perception.cpp
    ${PERCEPTION_SRC_DIR}/src/stereo_multi_match.cpp
    ${PERCEPTION_SRC_DIR}/src/multiscale_filter.cpp
)

# 可执行文件
add_executable(offline_test_main ${SOURCES})

# 链接库
target_link_libraries(offline_test_main
    ${OpenCV_LIBS}
    ${PCL_LIBRARIES}
    dnn
    hbdk_sim_x86
    z
    dl
    rt
    pthread
)

# 安装规则
install(TARGETS offline_test_main DESTINATION bin)
