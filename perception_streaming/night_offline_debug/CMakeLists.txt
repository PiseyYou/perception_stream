cmake_minimum_required(VERSION 3.22)
project(fusion_cdt_dsg)

set(CMAKE_CXX_STANDARD 17)

# x86 DNN simulation dependencies (Horizon BPU SDK for x86)
set(DEPS_ROOT /home/youfeng/CLionProjects/04-offline_debug_seperate/model_test/deps_gcc11.3/x86/)

message(STATUS "DEPS_ROOT: ${DEPS_ROOT}")
message(STATUS "PROJECT_SOURCE_DIR: ${PROJECT_SOURCE_DIR}")

set(CMAKE_CXX_FLAGS_DEBUG   "-g -O0")
set(CMAKE_C_FLAGS_DEBUG     "-g -O0")
set(CMAKE_CXX_FLAGS_RELEASE "-O3")
set(CMAKE_C_FLAGS_RELEASE   "-O3")

find_package(OpenCV REQUIRED)
find_package(PCL    REQUIRED)

message(STATUS "PCL_INCLUDE_DIRS: ${PCL_INCLUDE_DIRS}")
message(STATUS "OpenCV_INCLUDE_DIRS: ${OpenCV_INCLUDE_DIRS}")

include_directories(
        ${CMAKE_CURRENT_SOURCE_DIR}/include
        ${DEPS_ROOT}/dnn_x86/include
        /usr/include/eigen3/
        /usr/include/vtk-9.1/
        /usr/include/jsoncpp
        ${PCL_INCLUDE_DIRS}
        ${OpenCV_INCLUDE_DIRS})

link_directories(
        ${DEPS_ROOT}/dnn_x86/lib)

SET(LINK_libs dnn hbdk_sim_x86 z dl rt pthread)

# Single-image runner
add_executable(run_cdt_dsg_fusion
        src/run_cdt_dsg_fusion.cpp
        src/multiscale_filter.cpp
        src/stereo_multi_match.cpp
        src/stereo_point_cloud_rgbl.cpp
        src/dsg_perception.cpp
        src/cdt_perception.cpp)
target_link_libraries(run_cdt_dsg_fusion ${OpenCV_LIBS} ${PCL_LIBRARIES} ${LINK_libs})

# Directory-batch runner
add_executable(run_cdt_dsg_fusion_dir
        src/run_cdt_dsg_fusion_dir.cpp
        src/multiscale_filter.cpp
        src/stereo_multi_match.cpp
        src/stereo_point_cloud_rgbl.cpp
        src/dsg_perception.cpp
        src/cdt_perception.cpp)
target_link_libraries(run_cdt_dsg_fusion_dir ${OpenCV_LIBS} ${PCL_LIBRARIES} ${LINK_libs} jsoncpp)
