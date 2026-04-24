#!/bin/bash
# 快速测试脚本：验证机器连接和ROS2环境

ROBOT_PORT=${1:-10015}
ROBOT_HOST="120.25.121.3"
SSH_KEY="/home/youfeng/CLionProjects/12-evb/evb_test/ssh/bestmow_rsa_202603"

echo "=========================================="
echo "测试机器连接: 端口 $ROBOT_PORT"
echo "=========================================="

# 测试1: SSH连接
echo -e "\n[1/5] 测试SSH连接..."
if ssh -i $SSH_KEY root@$ROBOT_HOST -p $ROBOT_PORT -o ConnectTimeout=5 "echo 'SSH连接成功'" 2>/dev/null; then
    echo "✓ SSH连接正常"
else
    echo "✗ SSH连接失败"
    exit 1
fi

# 测试2: ROS2环境
echo -e "\n[2/5] 检查ROS2环境..."
ssh -i $SSH_KEY root@$ROBOT_HOST -p $ROBOT_PORT 'export ROS_LOCALHOST_ONLY=1 && export RMW_IMPLEMENTATION=rmw_fastrtps_cpp && export FASTRTPS_DEFAULT_PROFILES_FILE=/opt/ros/fastdds.xml && export ROS_LOG_DIR=/userdata/log_dir/ros2_log && source /app/BestMow/install/setup.bash && ros2 node list' 2>/dev/null

if [ $? -eq 0 ]; then
    echo "✓ ROS2环境正常"
else
    echo "✗ ROS2环境异常"
fi

# 测试3: 检查关键话题
echo -e "\n[3/5] 检查关键话题..."
ssh -i $SSH_KEY root@$ROBOT_HOST -p $ROBOT_PORT 'export ROS_LOCALHOST_ONLY=1 && export RMW_IMPLEMENTATION=rmw_fastrtps_cpp && export FASTRTPS_DEFAULT_PROFILES_FILE=/opt/ros/fastdds.xml && export ROS_LOG_DIR=/userdata/log_dir/ros2_log && source /app/BestMow/install/setup.bash && ros2 topic list | grep -E "(perception|chassis|camera)"' 2>/dev/null

# 测试4: 检查MQTT
echo -e "\n[4/5] 检查MQTT服务..."
ssh -i $SSH_KEY root@$ROBOT_HOST -p $ROBOT_PORT "ps aux | grep mosquitto | grep -v grep" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✓ MQTT服务运行中"
else
    echo "⚠ MQTT服务未运行，需要安装"
fi

# 测试5: 检查Python环境
echo -e "\n[5/5] 检查Python环境..."
ssh -i $SSH_KEY root@$ROBOT_HOST -p $ROBOT_PORT "python3 --version && python3 -c 'import rclpy; import paho.mqtt.client'" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✓ Python环境正常"
else
    echo "⚠ 需要安装依赖: pip3 install paho-mqtt"
fi

echo -e "\n=========================================="
echo "测试完成"
echo "=========================================="
