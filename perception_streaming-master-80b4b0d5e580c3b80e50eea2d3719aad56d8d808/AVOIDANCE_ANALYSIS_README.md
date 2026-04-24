# 避障日志分析标准操作流程

## 概述

本文档提供标准化的避障日志分析流程，用于快速诊断机器人避障的真实原因。

## 快速开始

### 1. 配置机器连接信息

编辑 `config/machine_config.json`：

```json
{
  "machines": {
    "machine_1": {
      "name": "测试机1",
      "host": "120.25.121.3",
      "port": 10286,
      "ssh_key": "/home/youfeng/CLionProjects/12-evb/evb_test/ssh/bestmow_rsa_202604",
      "user": "root",
      "log_base_path": "/userdata/log_dir/ros2_log",
      "image_base_path": "/userdata/bestmow_data/image_save_path"
    }
  }
}
```

### 2. 运行分析脚本

```bash
# 分析今天的避障日志
./scripts/analyze_avoidance.sh machine_1

# 分析指定日期的避障日志
./scripts/analyze_avoidance.sh machine_1 20260414

# 分析指定时间段
./scripts/analyze_avoidance.sh machine_1 20260414 "03:14-03:36"
```

## 分析流程

### 阶段1: 数据收集

1. **连接到目标机器**
2. **列出避障图片**
   - 路径: `{image_base_path}/{date}/`
   - 文件模式: `perception_stereo_*_avoiding_*.jpg`
3. **提取时间戳**
   - 格式: `YYYYMMDD_HHMMSS_milliseconds`
4. **统计避障类型**
   - DSG (深度立体几何)
   - SUB (子站检测)

### 阶段2: 日志关联分析

#### 2.1 感知日志 (stereo_perception_multi)

**检查项**:
- `mode=100, filename=avoiding` - 避障模式触发标记
- `[Dsg]back:` - DSG背景点数量和距离
- `[Sub][seg]back:` - SUB背景点数量
- 图像同步警告: `left img has delay`, `Too large left/right diff`

**关键指标**:
- back点数 > 0 且 near_back < 5.0m 可能触发避障
- 但需要交叉验证其他日志确认是否为真实原因

#### 2.2 导航日志 (nav2_single_node_navigator)

**检查项**:
- `Goal was canceled` - 目标取消事件
- `Speed limit:` - 速度限制变化
- `obstacle:` - 障碍物计数
- `movable:` - 可移动物体点云数量
- `Control loop missed` - 控制循环延迟

**关键模式**:
```
Speed limit: 0.03  → 速度被严格限制
Goal was canceled  → 导航目标被取消
```

#### 2.3 决策日志 (robot_decision)

**检查项**:
- `Work:AVOIDING` - 避障工作状态
- `Prev work:COVERING` - 之前的工作状态
- `Can not get transform` - TF变换失败
- `Error_code:` - 错误代码

**关键状态转换**:
```
COVERING → AVOIDING → COVERING
```

#### 2.4 底盘日志 (chassis_node)

**检查项**:
- `cut motor_warning` - 刀片电机警告
- `fault_stall_flg` - 堵转标志
- `hall_uplift_*` - 底盘抬升传感器
- `cut motor current` - 刀片电机电流
- `chassis_incident_.warning_cut_motor` - 刀片电机事件

**刀片堵转特征**:
- 电流异常飙升 (正常 < 100mA, 堵转 > 1500mA)
- `fault_stall_flg > 0`
- `motor_warning = 16`

#### 2.5 覆盖导航日志 (coverage_navigator_server)

**检查项**:
- `Chassis cut motor maybe blocked` - 刀片堵转检测
- `COVER_OBSTACLE_AVOIDING` - 避障状态
- `Retry for blocked` - 堵塞重试

### 阶段3: 根因分析

#### 可能的避障原因优先级

1. **刀片电机堵转** (最常见)
   - 触发日志: `Chassis cut motor maybe blocked`
   - 底盘日志: `cut motor_warning`, 电流飙升
   - 决策日志: `Work:AVOIDING`

2. **底盘抬升传感器触发**
   - 触发日志: `hall_uplift_*` 频繁触发
   - 原因: 不平整地形、障碍物碰撞

3. **碰撞检测**
   - 触发日志: 底盘碰撞传感器
   - 需要检查物理碰撞事件

4. **地图漂移/定位失败**
   - 触发日志: `Can not get transform between base link and map`
   - 定位日志: `robot_combination_localization`

5. **虚拟边界违规**
   - 触发日志: 导航日志中的边界检查
   - 需要检查地图和路径规划

6. **感知系统检测到障碍物** (最少见)
   - 触发日志: 感知日志中的障碍物点云
   - 需要确认 `back`, `stat`, `obstacle` 等计数

### 阶段4: 生成报告

报告应包含:
1. 避障事件统计 (次数、类型、时间分布)
2. 根因分析 (主要原因、次要原因)
3. 时间线重建
4. 优化建议

## 脚本使用

### analyze_avoidance.sh

主分析脚本，自动执行完整分析流程。

```bash
#!/bin/bash
# 使用方法:
# ./scripts/analyze_avoidance.sh <machine_name> [date] [time_range]

MACHINE=$1
DATE=${2:-$(date +%Y%m%d)}
TIME_RANGE=$3

# 加载配置
source scripts/load_config.sh $MACHINE

# 执行分析
python3 scripts/analyze_avoidance.py \
  --machine $MACHINE \
  --date $DATE \
  --time-range "$TIME_RANGE"
```

### 配置文件模板

`config/machine_config.json`:
```json
{
  "machines": {
    "machine_name": {
      "name": "显示名称",
      "host": "IP地址",
      "port": SSH端口,
      "ssh_key": "SSH密钥路径",
      "user": "用户名",
      "log_base_path": "/userdata/log_dir/ros2_log",
      "image_base_path": "/userdata/bestmow_data/image_save_path"
    }
  },
  "analysis": {
    "blade_current_threshold": 1500,
    "uplift_count_threshold": 50,
    "perception_distance_threshold": 5.0
  }
}
```

## 输出示例

### 终端输出

```
=== 避障日志分析报告 ===
机器: 测试机1 (120.25.121.3:10286)
日期: 2026-04-14
时间段: 03:14-03:36

[1/4] 数据收集...
  ✓ 找到 129 张避障图片
  ✓ DSG避障: 93次
  ✓ SUB避障: 36次

[2/4] 日志关联分析...
  ✓ 感知日志: 已分析
  ✓ 导航日志: 已分析
  ✓ 决策日志: 已分析
  ✓ 底盘日志: 已分析
  ✓ 覆盖导航日志: 已分析

[3/4] 根因分析...
  主要原因: 刀片电机堵转 (93次, 72%)
  次要原因: 底盘抬升传感器 (36次, 28%)
  感知触发: 0次 (0%)

[4/4] 生成报告...
  ✓ 报告已保存: reports/avoidance_20260414_031436.md
  ✓ 时间线已保存: reports/timeline_20260414_031436.json
```

### 报告文件

`reports/avoidance_20260414_031436.md`:

```markdown
# 避障分析报告

**机器**: 测试机1  
**日期**: 2026-04-14  
**时间段**: 03:14-03:36  
**分析时间**: 2026-04-14 10:30:00

## 执行摘要

- 总避障次数: 129次
- 主要原因: 刀片电机堵转 (72%)
- 次要原因: 底盘抬升传感器触发 (28%)
- 感知误触发: 0次

## 详细分析

### 1. 刀片电机堵转 (93次)

**时间分布**:
- 03:14:33 - 首次堵转
- 03:15:28 - Error 160 报告
- 持续时间: 22分钟

**特征**:
- 电流飙升: -30mA → 2100mA
- 堵转标志: fault_stall_flg=4
- 警告代码: motor_warning=16

**触发链**:
```
底盘检测堵转 → 覆盖导航进入AVOIDING → 决策层切换状态 → 
导航取消目标 → 感知保存现场图片
```

### 2. 底盘抬升传感器 (36次)

**触发次数**: 1028次传感器事件
**主要时段**: 03:14-03:36

**模式**:
- hall_uplift_left_1/2 频繁触发
- hall_uplift_right_1/2 频繁触发
- 可能原因: 不平整地形

## 优化建议

1. **刀片高度调整**: 提高刀片离地高度 2-3cm
2. **草密度检测**: 在高密度区域降低速度至 0.2m/s
3. **地形适应**: 改进抬升传感器阈值
4. **错误处理**: 刀片堵转后立即停止，避免重复尝试
5. **日志优化**: 区分避障原因标签

## 时间线

| 时间 | 事件 | 来源 |
|------|------|------|
| 03:14:33 | 刀片电机堵转，电流飙升 | chassis_node |
| 03:14:34 | 导航取消目标 | nav2 |
| 03:14:53 | 进入AVOIDING状态 | coverage_navigator |
| 03:14:57 | 保存第一张避障图片 | stereo_perception |
| 03:15:28 | Error 160: 刀片过载 | robot_decision |

## 附件

- 避障图片: 129张
- 日志片段: logs/excerpts_20260414.tar.gz
- 时间线JSON: timeline_20260414_031436.json
```

## 常见问题

### Q1: 如何添加新机器？

编辑 `config/machine_config.json`，添加新的机器配置。

### Q2: 如何自定义分析阈值？

修改 `config/machine_config.json` 中的 `analysis` 部分。

### Q3: 如何导出避障图片？

```bash
./scripts/export_images.sh machine_1 20260414 /path/to/export
```

### Q4: 如何对比多天的避障数据？

```bash
./scripts/compare_days.sh machine_1 20260413 20260414
```

### Q5: 分析脚本运行失败怎么办？

检查:
1. SSH连接是否正常
2. 日志路径是否正确
3. 日期格式是否正确 (YYYYMMDD)
4. Python依赖是否安装完整

## 依赖安装

```bash
# Python依赖
pip3 install -r requirements.txt

# 系统依赖
sudo apt-get install jq ssh
```

## 目录结构

```
.
├── AVOIDANCE_ANALYSIS_README.md    # 本文档
├── config/
│   └── machine_config.json         # 机器配置
├── scripts/
│   ├── analyze_avoidance.sh        # 主分析脚本
│   ├── analyze_avoidance.py        # Python分析脚本
│   ├── load_config.sh              # 配置加载
│   ├── export_images.sh            # 图片导出
│   └── compare_days.sh             # 多日对比
├── reports/                        # 分析报告输出
├── logs/                           # 日志片段缓存
└── requirements.txt                # Python依赖
```

## 维护

- 定期清理 `reports/` 和 `logs/` 目录
- 更新机器配置信息
- 根据新的避障模式更新分析逻辑

## 联系

如有问题或建议，请联系开发团队。
