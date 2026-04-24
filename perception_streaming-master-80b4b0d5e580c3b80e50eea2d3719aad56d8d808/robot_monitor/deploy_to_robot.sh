#!/bin/bash
# 部署监控脚本到机器端

ROBOT_PORT=${1:-10015}
ROBOT_HOST="120.25.121.3"
SSH_KEY="/home/youfeng/CLionProjects/12-evb/evb_test/ssh/bestmow_rsa_202603"
REMOTE_DIR="/app/BestMow/monitor"

echo "部署到端口: $ROBOT_PORT"

# 创建远程目录
ssh -i $SSH_KEY root@$ROBOT_HOST -p $ROBOT_PORT "mkdir -p $REMOTE_DIR"

# 上传监控脚本
scp -i $SSH_KEY -P $ROBOT_PORT \
    obstacle_monitor.py \
    auto_recorder.py \
    root@$ROBOT_HOST:$REMOTE_DIR/

# 上传启动脚本
cat > /tmp/start_monitor.sh << 'EOF'
#!/bin/bash
export ROS_LOCALHOST_ONLY=1
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE=/opt/ros/fastdds.xml
export ROS_LOG_DIR=/userdata/log_dir/ros2_log
source /app/BestMow/install/setup.bash

cd /app/BestMow/monitor

# 启动监控节点
python3 obstacle_monitor.py &

# 启动录包模块
python3 auto_recorder.py &

echo "监控系统已启动"
EOF

scp -i $SSH_KEY -P $ROBOT_PORT /tmp/start_monitor.sh root@$ROBOT_HOST:$REMOTE_DIR/
ssh -i $SSH_KEY root@$ROBOT_HOST -p $ROBOT_PORT "chmod +x $REMOTE_DIR/start_monitor.sh"

echo "部署完成！"
echo "启动命令: ssh -i $SSH_KEY root@$ROBOT_HOST -p $ROBOT_PORT '$REMOTE_DIR/start_monitor.sh'"
