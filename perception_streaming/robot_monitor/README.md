# 避障行为监控系统 - 部署指南

## 系统架构

```
PC端 (localhost:5173)          机器端 (端口10015)
┌─────────────────┐           ┌─────────────────┐
│  Web界面        │           │  ROS2监控节点   │
│  - 视频流       │◄─MQTT────►│  - 日志分析     │
│  - 避障监控面板 │           │  - 自动录包     │
└─────────────────┘           └─────────────────┘
```

## 快速开始

### 1. 测试机器连接

```bash
cd /home/youfeng/CLionProjects/07_openclaw_auto/project/perception_streaming-master-80b4b0d5e580c3b80e50eea2d3719aad56d8d808/robot_monitor

# 测试10015端口的机器
./test_connection.sh 10015
```

### 2. 部署监控系统到机器

```bash
# 部署到指定端口的机器
./deploy_to_robot.sh 10015
```

部署内容：
- `obstacle_monitor.py` - ROS2监控节点
- `auto_recorder.py` - 自动录包模块
- `start_monitor.sh` - 启动脚本

### 3. 启动机器端监控

```bash
# SSH连接到机器
ssh -i /home/youfeng/CLionProjects/12-evb/evb_test/ssh/bestmow_rsa_202603 root@120.25.121.3 -p 10015

# 启动监控系统
cd /app/BestMow/monitor
./start_monitor.sh
```

### 4. 启动PC端Web界面

```bash
cd /home/youfeng/CLionProjects/07_openclaw_auto/project/perception_streaming-master-80b4b0d5e580c3b80e50eea2d3719aad56d8d808

# 安装依赖（首次）
npm install

# 启动开发服务器
npm run dev
```

访问: http://localhost:5173

## 功能说明

### 避障行为判断逻辑

监控系统会实时分析以下数据：
- 点云数据 (`/perception_node/stereo/pcl_output`)
- 速度指令 (`/chassis/cmd_vel`)
- 里程计 (`/chassis/odom`)

**判断规则：**

1. **正常避障**
   - 检测到障碍物 (距离 < 2m)
   - 速度降低 (< 0.3 m/s) 或转向 (角速度 > 0.3 rad/s)

2. **不避障异常**
   - 检测到障碍物 (距离 < 2m)
   - 速度未降低 (> 0.3 m/s)
   - 触发自动录包

3. **误避障异常**
   - 未检测到障碍物
   - 突然减速 (< 0.1 m/s) 或急转向 (> 0.5 rad/s)
   - 触发自动录包

### 自动录包

当检测到异常时，系统会自动：
1. 录制30秒的rosbag（前后各15秒）
2. 包含以下话题：
   - 点云数据
   - 图像数据（左右目）
   - 速度指令
   - 里程计
   - 机器状态
3. 压缩并保存到 `/userdata/bestmow_data/rosbags/`
4. 通过MQTT通知PC端

### Web界面功能

- **实时状态显示**
  - 障碍物检测状态
  - 距离、速度、角速度
  - 行为判断结果

- **异常事件列表**
  - 时间戳
  - 异常类型（不避障/误避障）
  - 原因描述
  - 录包文件路径

- **视频流同步**
  - 结合摄像头画面
  - 人工复核避障行为

## 数据流

```
机器端 ROS2话题
    ↓
obstacle_monitor.py (分析)
    ↓
MQTT发布 (robot/obstacle_monitor)
    ↓
Web界面实时显示
```

## 调试命令

### 查看监控节点状态
```bash
ssh -i /home/youfeng/CLionProjects/12-evb/evb_test/ssh/bestmow_rsa_202603 root@120.25.121.3 -p 10015 'ps aux | grep obstacle_monitor'
```

### 查看MQTT消息
```bash
# 在PC端订阅
mosquitto_sub -h localhost -t 'robot/#' -v
```

### 手动触发录包
```bash
# 发布MQTT消息
mosquitto_pub -h localhost -t 'robot/record_command' -m '{"action":"start_recording","reason":"manual_test","duration":30}'
```

### 查看录包文件
```bash
ssh -i /home/youfeng/CLionProjects/12-evb/evb_test/ssh/bestmow_rsa_202603 root@120.25.121.3 -p 10015 'ls -lh /userdata/bestmow_data/rosbags/'
```

## 依赖安装

### 机器端
```bash
# Python依赖
pip3 install paho-mqtt

# MQTT Broker (如果没有)
apt-get install mosquitto mosquitto-clients
systemctl start mosquitto
```

### PC端
```bash
# Node.js依赖
cd perception_streaming-master-*
npm install
```

## 配置调整

### 修改判断阈值

编辑 `obstacle_monitor.py` 中的 `judge_behavior` 函数：

```python
# 不避障阈值
if has_obstacle and distance < 2.0 and velocity > 0.3:
    # 调整 distance 和 velocity 阈值

# 误避障阈值
elif not has_obstacle and (velocity < 0.1 or abs(angular) > 0.5):
    # 调整 velocity 和 angular 阈值
```

### 修改录包话题

编辑 `auto_recorder.py` 中的 `topics` 列表：

```python
topics = [
    "/perception_node/stereo/pcl_output",
    # 添加或删除话题
]
```

## 故障排查

### 问题1: MQTT连接失败
- 检查mosquitto服务: `systemctl status mosquitto`
- 检查端口: `netstat -tlnp | grep 1883`
- 检查防火墙: `ufw status`

### 问题2: ROS2话题无数据
- 检查节点: `ros2 node list`
- 检查话题: `ros2 topic list`
- 检查频率: `ros2 topic hz /perception_node/stereo/pcl_output`

### 问题3: 录包失败
- 检查磁盘空间: `df -h /userdata`
- 检查权限: `ls -ld /userdata/bestmow_data/rosbags`
- 查看日志: `tail -f /userdata/log_dir/ros2_log/*`

## 下一步优化

1. **接入第三方摄像头**
   - 添加RTSP流订阅
   - 同步显示在Web界面

2. **AI辅助分析**
   - 接入Claude API
   - 自动生成异常分析报告

3. **历史数据分析**
   - 建立数据库
   - 统计误报率
   - 优化判断阈值

4. **远程控制**
   - Web界面直接控制机器
   - 远程查看录包
   - 一键下载日志

## 联系方式

如有问题，请查看日志：
- 机器端: `/userdata/log_dir/ros2_log/`
- PC端: 浏览器控制台
