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

# 添加编译器选项,忽略 FLANN 相关的错误
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wno-error -fpermissive")

# 选择使用真实 DNN 库还是 mock 库
option(USE_REAL_DNN "Use real DNN libraries instead of mock" ON)

if(USE_REAL_DNN)
    set(DNN_LIB dnn)
    set(HBDK_LIB hbdk_sim_x86)
    message(STATUS "Using real DNN libraries (requires GLIBCXX_3.4.29+)")
else()
    set(DNN_LIB dnn_mock)
    set(HBDK_LIB hbdk_sim_x86_mock)
    message(STATUS "Using mock DNN libraries")
endif()

# 检查是否设置了 CONDA_PREFIX 环境变量（使用 conda 环境）
if(DEFINED ENV{CONDA_PREFIX})
    message(STATUS "Using conda environment: $ENV{CONDA_PREFIX}")
    # 添加 conda 环境的库路径到链接目录
    link_directories($ENV{CONDA_PREFIX}/lib)
    # 设置 RPATH 以便运行时能找到 conda 的 libstdc++
    set(CMAKE_INSTALL_RPATH "$ENV{CONDA_PREFIX}/lib")
    set(CMAKE_BUILD_WITH_INSTALL_RPATH TRUE)
    set(CMAKE_SKIP_BUILD_RPATH FALSE)
    message(STATUS "Will use conda libstdc++ at runtime")
endif()

# 查找依赖库（使用系统的 OpenCV 和 PCL）
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
    ${CMAKE_SOURCE_DIR}/../lib/dnn_x86
)

# 如果使用 conda 环境，添加 conda 库路径（已在前面处理）

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

# 如果使用真实 DNN 库，需要链接 conda 的 libstdc++
if(USE_REAL_DNN)
    # 查找 conda 环境的 libstdc++
    set(CONDA_LIBSTDCXX "/home/server/miniconda/envs/gcc11/lib/libstdc++.so.6")
    if(EXISTS ${CONDA_LIBSTDCXX})
        message(STATUS "Using conda libstdc++: ${CONDA_LIBSTDCXX}")
        # 明确链接 conda 的 libstdc++
        target_link_libraries(offline_test_main ${CONDA_LIBSTDCXX})
    else()
        message(WARNING "Conda libstdc++ not found at ${CONDA_LIBSTDCXX}")
        message(WARNING "Linking may fail due to GLIBCXX version mismatch")
    endif()
endif()

# 链接库
target_link_libraries(offline_test_main
    ${OpenCV_LIBS}
    ${PCL_LIBRARIES}
    ${PCL_FILTERS_LIB}
    ${DNN_LIB}
    -Wl,--no-as-needed
    ${HBDK_LIB}
    -Wl,--as-needed
    z
    dl
    rt
    pthread
)

# Embed runtime library paths so the binary can run from both:
#   stereo_perception_multi2_offline_test/build/offline_test_main
#   perception_streaming/bin/offline_test_main
set(OFFLINE_RUNTIME_RPATH
    "/home/server/miniconda/envs/gcc11/lib"
    "\$ORIGIN/../../lib/dnn_x86"
    "\$ORIGIN/../lib/dnn_x86"
)
set_target_properties(offline_test_main PROPERTIES
    BUILD_RPATH "${OFFLINE_RUNTIME_RPATH}"
    INSTALL_RPATH "${OFFLINE_RUNTIME_RPATH}"
)

# 安装规则
install(TARGETS offline_test_main DESTINATION bin)
