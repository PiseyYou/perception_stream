#!/usr/bin/env python3
"""
自动录包模块
监听 MQTT 录包指令，自动触发 rosbag 录制
"""

import paho.mqtt.client as mqtt
import subprocess
import json
import time
import os
from datetime import datetime


class AutoRecorder:
    def __init__(self):
        self.recording_process = None
        self.is_recording = False
        self.record_dir = "/userdata/bestmow_data/rosbags"

        # 确保录包目录存在
        os.makedirs(self.record_dir, exist_ok=True)

        # MQTT 客户端
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message

        self.mqtt_client.connect("localhost", 1883, 60)
        self.mqtt_client.loop_forever()

    def on_connect(self, client, userdata, flags, rc):
        print(f"MQTT Connected: {rc}")
        # 订阅录包指令
        client.subscribe("robot/record_command")

    def on_message(self, client, userdata, msg):
        """处理录包指令"""
        try:
            cmd = json.loads(msg.payload.decode())

            if cmd['action'] == 'start_recording':
                self.start_recording(cmd)
            elif cmd['action'] == 'stop_recording':
                self.stop_recording()

        except Exception as e:
            print(f"Error processing message: {e}")

    def start_recording(self, cmd):
        """开始录包"""
        if self.is_recording:
            print("Already recording, skipping...")
            return

        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        reason = cmd.get('reason', 'unknown')
        bag_name = f"{reason}_{timestamp}"
        bag_path = os.path.join(self.record_dir, bag_name)

        # 录制的话题列表
        topics = [
            "/perception_node/stereo/pcl_output",
            "/perception_node/obstacles",
            "/chassis/cmd_vel",
            "/chassis/odom",
            "/camera_sensors/rotation/sc132gs/left/image_rect/compressed",
            "/camera_sensors/rotation/sc132gs/right/image_rect/compressed",
            "/robot_decision/robot_status"
        ]

        duration = cmd.get('duration', 30)

        # 构建录包命令
        record_cmd = [
            "ros2", "bag", "record",
            "-o", bag_path,
            "--duration", str(duration)
        ] + topics

        print(f"Starting recording: {bag_name}")
        print(f"Command: {' '.join(record_cmd)}")

        # 启动录包进程
        self.recording_process = subprocess.Popen(
            record_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        self.is_recording = True

        # 发布录包状态
        status = {
            'status': 'recording',
            'bag_name': bag_name,
            'bag_path': bag_path,
            'start_time': time.time()
        }
        self.mqtt_client.publish('robot/record_status', json.dumps(status))

        # 等待录包完成
        self.recording_process.wait()
        self.is_recording = False

        print(f"Recording completed: {bag_name}")

        # 发布完成状态
        status['status'] = 'completed'
        status['end_time'] = time.time()
        self.mqtt_client.publish('robot/record_status', json.dumps(status))

        # 触发上传
        self.upload_bag(bag_path)

    def stop_recording(self):
        """停止录包"""
        if self.recording_process and self.is_recording:
            self.recording_process.terminate()
            self.recording_process.wait()
            self.is_recording = False
            print("Recording stopped")

    def upload_bag(self, bag_path):
        """上传录包文件"""
        print(f"Uploading bag: {bag_path}")

        # 这里可以实现上传逻辑
        # 例如：scp 到服务器，或者调用云存储 API

        # 示例：压缩后上传
        tar_path = f"{bag_path}.tar.gz"
        subprocess.run([
            "tar", "-czf", tar_path, "-C", self.record_dir, os.path.basename(bag_path)
        ])

        print(f"Bag compressed: {tar_path}")

        # TODO: 实现实际的上传逻辑
        # upload_to_cloud(tar_path)


if __name__ == '__main__':
    recorder = AutoRecorder()
