# 点云过滤策略文档

## 概述

本文档描述了夜间立体视觉感知系统中的点云过滤策略，用于解决夜间场景下草地表面产生的背景噪点导致的误避障问题。

## 问题背景

### 问题描述
- **现象**：夜间立体视觉在草地表面产生大量近距离点云，被误分类为 label=1（背景）
- **影响**：这些背景噪点触发避障行为，导致机器人误判前方有障碍物
- **场景**：所有夜间草地场景，特别是近距离（< 2.0m）范围

### Label 定义
- **label=1**：背景点（Background），会触发避障，但夜间常被误分类
- **label=3**：道路点（Road），不触发避障
- **label=5**：真实障碍物（Obstacle），会触发避障，必须保留

## 过滤策略

### 核心原则
**只过滤 label=1（背景噪点），完全保留 label=3（道路）和 label=5（真实障碍物）**

### 过滤参数

```python
MIN_DISTANCE = 0.3      # 最小距离（米），过滤过近的噪点
MAX_DISTANCE = 10.0     # 最大距离（米），过滤过远的噪点
MIN_OBSTACLE_HEIGHT = 0.5  # 最小障碍物高度（米），过滤地面高度的点
MAX_HEIGHT = 2.0        # 最大高度（米），过滤过高的噪点
```

### 过滤规则

#### 1. 对 label=1（背景）应用过滤
- **深度过滤**：
  - 过滤 z ≤ 0（无效深度）
  - 过滤 z < 0.3m（过近噪点）
  - 过滤 z > 10.0m（过远噪点）

- **高度过滤**：
  - 过滤 y < 0.5m（地面高度，草地误分类为背景）
  - 过滤 y > 2.0m（过高噪点）

- **有效性检查**：
  - 过滤 NaN 值
  - 过滤 Inf 值（正无穷和负无穷）

#### 2. 对 label=3（道路）和 label=5（障碍物）
- **不应用任何过滤**
- **完全保留原始点云数据**

### 过滤逻辑伪代码

```python
for each point in pointcloud:
    # 基础有效性检查（所有点）
    if point has NaN or Inf:
        skip point
    
    # 只对 label=1 应用过滤
    if point.label == 1:
        if point.z <= 0 or point.z < 0.3 or point.z > 10.0:
            skip point
        if point.y < 0.5 or point.y > 2.0:
            skip point
    
    # label=3 和 label=5 直接保留
    keep point
```

## 实现位置

### 1. 实时点云流（WebSocket）
**文件**：`robot_monitor/pcl_ws_bridge.py`

**函数**：`PclBridgeNode.on_pcl()` (lines 155-204)

**应用场景**：实时订阅 `/perception_node/stereo/pcl_output` 并通过 WebSocket (port 8767) 推送到浏览器

### 2. 离线点云处理（Bag 文件提取）
**文件**：`robot_monitor/offline_server.py`

**函数**：`_decode_pointcloud2()` (lines 762-852)

**应用场景**：从 ROS bag 文件提取点云数据时应用过滤

### 3. 离线夜间 Debug（PCD 文件后处理）
**文件**：`robot_monitor/offline_server.py`

**函数**：`_filter_pcd_file()` (lines 858-930)

**应用场景**：夜间离线 debug 按钮（infer_mode=99）运行后，对生成的 PCD 文件进行后处理

**调用位置**：`run_offline_test()` (line 181)

## 过滤效果

### 测试数据
- **测试文件**：`/home/youfeng/debug/boluo/0123/20260408/perception_stereo_20260408_004855_343_auto_DSG.pcd`
- **原始点云**：3368 个点
  - label=1: 367 个点（10.9%）
  - label=3: 3001 个点（89.1%）

### 过滤结果
- **过滤后点云**：3001 个点
  - label=1: 0 个点（100% 移除）
  - label=3: 3001 个点（100% 保留）
- **移除率**：10.9%

### 预期效果
1. ✅ 移除所有地面高度的背景噪点（y < 0.5m）
2. ✅ 保留所有道路点云（label=3）
3. ✅ 保留所有真实障碍物（label=5）
4. ✅ 消除夜间草地场景的误避障行为

## 使用说明

### 实时流过滤
1. 启动 `pcl_ws_bridge.py`
2. 过滤自动应用于所有实时点云数据
3. 浏览器通过 WebSocket (port 8767) 接收过滤后的点云

### 离线夜间 Debug
1. 点击"离线夜间debug"按钮（infer_mode=99）
2. C++ 程序 `run_cdt_dsg_fusion_dir` 生成原始 PCD 文件
3. Python 自动对所有生成的 PCD 文件应用过滤
4. 浏览器显示过滤后的点云结果

### 重启服务
修改过滤参数后，需要：
1. 删除 Python 字节码缓存：`rm -rf robot_monitor/__pycache__`
2. 重启 `offline_server.py` 服务
3. 重启 `pcl_ws_bridge.py` 服务（如果修改了实时流过滤）

## 参数调优建议

### 如果仍有噪点残留
- **增大 MIN_OBSTACLE_HEIGHT**（当前 0.5m）：过滤更多地面附近的点
- **减小 MAX_DISTANCE**（当前 10.0m）：过滤更远的噪点
- **增大 MIN_DISTANCE**（当前 0.3m）：过滤更近的噪点

### 如果过滤过度（丢失真实障碍物）
- **检查是否误过滤了 label=5**：确保代码中只过滤 label=1
- **减小 MIN_OBSTACLE_HEIGHT**（当前 0.5m）：保留更低的障碍物
- **增大 MAX_DISTANCE**（当前 10.0m）：保留更远的点

### 参数修改位置
**文件**：`robot_monitor/offline_server.py` (lines 49-53)

```python
MIN_DISTANCE = 0.3
MAX_DISTANCE = 10.0
MIN_OBSTACLE_HEIGHT = 0.5
MAX_HEIGHT = 2.0
```

**文件**：`robot_monitor/pcl_ws_bridge.py` (lines 139-141)

```python
MIN_DISTANCE = 0.3
MAX_DISTANCE = 10.0
MIN_OBSTACLE_HEIGHT = 0.5
MAX_HEIGHT = 2.0
```

## 注意事项

1. **不要过滤 label=5**：这是真实障碍物，必须完整保留
2. **label=3 不触发避障**：道路点云即使保留也不会导致误避障
3. **缓存问题**：修改代码后必须清除 `__pycache__` 并重启服务
4. **坐标系定义**：
   - x: 横向（左右）
   - y: 纵向（高度）
   - z: 深度（前后距离）

## 版本历史

### v1.0 (2026-04-08)
- 初始实现：只过滤 label=1（背景噪点）
- 参数：MIN_DISTANCE=0.3m, MAX_DISTANCE=10.0m, MIN_OBSTACLE_HEIGHT=0.5m, MAX_HEIGHT=2.0m
- 应用场景：实时流、离线提取、夜间 debug

## 相关文件

- `robot_monitor/pcl_ws_bridge.py` - 实时点云流过滤
- `robot_monitor/offline_server.py` - 离线点云处理和 PCD 文件过滤
- `POINTCLOUD_FILTER.md` - 本文档
