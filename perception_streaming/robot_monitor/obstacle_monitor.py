#!/usr/bin/env python3
"""
避障行为监控节点
实时监控机器的感知、决策和运动状态，判断避障行为是否正常
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import PointCloud2
import json
import time
from collections import deque
import paho.mqtt.client as mqtt


class ObstacleMonitor(Node):
    def __init__(self):
        super().__init__('obstacle_monitor')

        # 订阅关键话题
        self.pcl_sub = self.create_subscription(
            PointCloud2,
            '/perception_node/stereo/pcl_output',
            self.pcl_callback,
            10
        )

        self.cmd_vel_sub = self.create_subscription(
            Twist,
            '/chassis/cmd_vel',
            self.cmd_vel_callback,
            10
        )

        self.odom_sub = self.create_subscription(
            Odometry,
            '/chassis/odom',
            self.odom_callback,
            10
        )

        # 数据缓存（最近5秒）
        self.velocity_history = deque(maxlen=50)  # 10Hz * 5s
        self.obstacle_history = deque(maxlen=50)

        # 当前状态
        self.current_velocity = 0.0
        self.current_angular = 0.0
        self.has_obstacle = False
        self.obstacle_distance = float('inf')

        # MQTT 客户端
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.connect("localhost", 1883, 60)
        self.mqtt_client.loop_start()

        # 定时器：每秒分析一次
        self.timer = self.create_timer(1.0, self.analyze_behavior)

        self.get_logger().info('Obstacle Monitor Started')

    def on_mqtt_connect(self, client, userdata, flags, rc):
        self.get_logger().info(f'MQTT Connected: {rc}')

    def pcl_callback(self, msg):
        """点云回调：检测是否有障碍物"""
        # 简化逻辑：根据点云数量判断
        # 实际应该解析点云数据，计算最近障碍物距离
        point_count = msg.width * msg.height

        # 假设点云数量 > 1000 表示有障碍物
        self.has_obstacle = point_count > 1000

        # 这里需要实际计算障碍物距离
        # 暂时用点云数量反推距离（示例）
        if self.has_obstacle:
            self.obstacle_distance = max(0.5, 5.0 - point_count / 1000)
        else:
            self.obstacle_distance = float('inf')

        self.obstacle_history.append({
            'timestamp': time.time(),
            'has_obstacle': self.has_obstacle,
            'distance': self.obstacle_distance
        })

    def cmd_vel_callback(self, msg):
        """速度指令回调"""
        self.current_velocity = msg.linear.x
        self.current_angular = msg.angular.z

        self.velocity_history.append({
            'timestamp': time.time(),
            'linear': self.current_velocity,
            'angular': self.current_angular
        })

    def odom_callback(self, msg):
        """里程计回调（可选）"""
        pass

    def analyze_behavior(self):
        """分析避障行为"""
        if len(self.velocity_history) < 10 or len(self.obstacle_history) < 10:
            return

        # 获取最近1秒的数据
        recent_velocities = list(self.velocity_history)[-10:]
        recent_obstacles = list(self.obstacle_history)[-10:]

        # 计算平均速度
        avg_velocity = sum(v['linear'] for v in recent_velocities) / len(recent_velocities)

        # 检测是否有障碍物
        has_recent_obstacle = any(o['has_obstacle'] for o in recent_obstacles)
        min_distance = min(o['distance'] for o in recent_obstacles)

        # 判断逻辑
        behavior_status = self.judge_behavior(
            has_recent_obstacle,
            min_distance,
            avg_velocity,
            self.current_angular
        )

        # 发布到 MQTT
        self.publish_status(behavior_status)

        # 如果异常，触发录包
        if behavior_status['type'] in ['miss_avoidance', 'false_avoidance']:
            self.trigger_recording(behavior_status)

    def judge_behavior(self, has_obstacle, distance, velocity, angular):
        """
        避障行为判断逻辑

        返回：
        - normal: 正常
        - miss_avoidance: 不避障（应该避但没避）
        - false_avoidance: 误避障（不应该避但避了）
        """
        result = {
            'timestamp': time.time(),
            'has_obstacle': has_obstacle,
            'distance': distance,
            'velocity': velocity,
            'angular': angular,
            'type': 'normal',
            'reason': ''
        }

        # 规则1：检测到近距离障碍物，但速度未降低
        if has_obstacle and distance < 2.0 and velocity > 0.3:
            result['type'] = 'miss_avoidance'
            result['reason'] = f'检测到{distance:.2f}m障碍物，但速度仍为{velocity:.2f}m/s'

        # 规则2：未检测到障碍物，但突然减速或转向
        elif not has_obstacle and (velocity < 0.1 or abs(angular) > 0.5):
            result['type'] = 'false_avoidance'
            result['reason'] = f'未检测到障碍物，但速度降至{velocity:.2f}m/s或转向{angular:.2f}rad/s'

        # 规则3：正常避障
        elif has_obstacle and distance < 2.0 and (velocity < 0.3 or abs(angular) > 0.3):
            result['type'] = 'normal'
            result['reason'] = f'检测到{distance:.2f}m障碍物，正常减速/转向'

        return result

    def publish_status(self, status):
        """发布状态到 MQTT"""
        topic = 'robot/obstacle_monitor'
        payload = json.dumps(status)
        self.mqtt_client.publish(topic, payload)

        if status['type'] != 'normal':
            self.get_logger().warn(f"异常行为: {status['type']} - {status['reason']}")

    def trigger_recording(self, status):
        """触发录包"""
        self.get_logger().error(f"触发录包: {status['type']}")

        # 发送录包指令到 MQTT
        record_cmd = {
            'action': 'start_recording',
            'reason': status['type'],
            'timestamp': status['timestamp'],
            'duration': 30  # 录制30秒
        }
        self.mqtt_client.publish('robot/record_command', json.dumps(record_cmd))


def main(args=None):
    rclpy.init(args=args)
    node = ObstacleMonitor()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
