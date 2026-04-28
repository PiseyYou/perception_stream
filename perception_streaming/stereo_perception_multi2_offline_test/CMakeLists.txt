cmake_minimum_required(VERSION 3.22)
project(stereo_perception_offline_test)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 设置编译选项
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -O3")
add_definitions(-DPCL_NO_PRECOMPILE)
# 禁用 PCL 的 FLANN 支持以避免与 OpenCV 的 FLANN 命名空间冲突
add_definitions(-DPCL_NO_FLANN)
add_definitions(-DFLANN_USE_BOOST)

# 查找依赖库
find_package(OpenCV REQUIRED)
# 只使用 PCL 的基础组件，避免引入 kdtree 和 search（它们依赖 FLANN）
find_package(PCL REQUIRED COMPONENTS common io)

# 手动添加 PCL filters 库（不通过 find_package 以避免自动引入 FLANN 依赖）
set(PCL_FILTERS_LIB "/usr/lib/x86_64-linux-gnu/libpcl_filters.so")

# 根据硬件模式选择不同的源文件
# 默认使用 K100 模式（offline_perception_debug_src）
# 如果需要 bestmow 模式，设置 USE_BESTMOW=ON
option(USE_BESTMOW "Use bestmow mode instead of K100" OFF)

if(USE_BESTMOW)
    message(STATUS "Building with bestmow mode")
    set(PERCEPTION_SRC_DIR ../offline_perception_debug_src)
    set(PERCEPTION_INCLUDE_DIR ${CMAKE_SOURCE_DIR}/../offline_perception_debug_src/include)
else()
    message(STATUS "Building with K100 mode")
    set(PERCEPTION_SRC_DIR ../offline_perception_debug_src)
    set(PERCEPTION_INCLUDE_DIR ${CMAKE_SOURCE_DIR}/../offline_perception_debug_src/include)
endif()

# 包含目录（perception 头文件目录要放在最前面）
include_directories(
    ${CMAKE_SOURCE_DIR}/include
    ${PERCEPTION_INCLUDE_DIR}
    ${OpenCV_INCLUDE_DIRS}
    ${PCL_INCLUDE_DIRS}
    /usr/include
    /usr/hobot/include
    ${CMAKE_SOURCE_DIR}/../lib/dnn_x86/include
)

# 链接目录
link_directories(
    ${PERCEPTION_SRC_DIR}/lib
    /usr/lib
    /usr/hobot/lib
    /usr/lib/aarch64-linux-gnu
    ${CMAKE_SOURCE_DIR}/../lib/dnn_x86/lib
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
    ${PCL_FILTERS_LIB}
    dnn
    hbdk_sim_x86
    z
    dl
    rt
    pthread
)

# 安装规则
install(TARGETS offline_test_main DESTINATION bin)
