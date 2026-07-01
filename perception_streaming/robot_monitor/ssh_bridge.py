#!/usr/bin/env python3
from __future__ import annotations
"""
SSH Bridge Server
通过 SSH 连接机器，实时捕捉 ROS2 日志和话题数据，
通过 WebSocket 推送给前端，同时转发 MQTT 消息到机器
"""

import asyncio
import json
import os
import re
import stat as stat_mod
import time
import websockets
import paramiko
from datetime import datetime
from config_loader import get_ssh_key_path, get_ssh_host, get_ssh_user, get_default_port

# ─── 配置 ─────────────────────────────────────────────
SSH_KEY = get_ssh_key_path()
SSH_HOST = get_ssh_host()
SSH_USER = get_ssh_user()
WS_HOST = os.environ.get("BRIDGE_WS_HOST", "0.0.0.0")
WS_PORT = 8765

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# bags/ 目录：项目根目录下
BAGS_DIR = os.path.join(PROJECT_ROOT, "bags")

ROS2_ENV = (
    "export ROS_LOCALHOST_ONLY=1 && "
    "export RMW_IMPLEMENTATION=rmw_fastrtps_cpp && "
    "export FASTRTPS_DEFAULT_PROFILES_FILE=/opt/ros/fastdds.xml && "
    "export ROS_LOG_DIR=/userdata/log_dir/ros2_log && "
    "source /app/BestMow/install/setup.bash"
)

# 避障相关的日志关键词
OBSTACLE_KEYWORDS = [
    "obstacle", "avoid", "collision", "stop", "slow",
    "障碍", "避障", "碰撞", "减速", "停止",
    "perception", "stereo", "pcl",
    "WARN", "ERROR", "warn", "error"
]

# 录包配置
SCRIPT_PATH = "/app/BestMow/debug_sh/rosbag_record_perception_navigation.sh"
REMOTE_BAG_DIR = "/userdata/rosbag_record"
DISK_MIN_MB = 500          # 录包前最低剩余磁盘（MB）
RECORD_COOLDOWN = 60       # 两次录包最短间隔（秒）
RECORD_MAX_SECONDS = 30    # 录包最长时间看门狗（秒）
CONSECUTIVE_THRESHOLD = 3.0  # 连续避障触发阈值（秒）
RECOVERY_THRESHOLD = 5.0     # 连续正常恢复阈值（秒）
MANUAL_RECORD_SECONDS = 30   # 手动录包固定时长（秒）
# 本地上传目标目录：使用项目内 data/uploads
BULK_UPLOAD_DEST = os.path.join(PROJECT_ROOT, "data/uploads")


# ─── 避障行为分析 ──────────────────────────────────────

class ObstacleAnalyzer:
    def __init__(self):
        self.velocity_history = []   # [(timestamp, linear, angular)]
        self.obstacle_history = []   # [(timestamp, has_obstacle, distance)]
        self.window = 5.0            # 分析窗口（秒）

    def update_velocity(self, linear: float, angular: float):
        now = time.time()
        self.velocity_history.append((now, linear, angular))
        self._trim(self.velocity_history)

    def update_obstacle(self, has_obstacle: bool, distance: float):
        now = time.time()
        self.obstacle_history.append((now, has_obstacle, distance))
        self._trim(self.obstacle_history)

    def _trim(self, history):
        cutoff = time.time() - self.window
        while history and history[0][0] < cutoff:
            history.pop(0)

    def analyze(self) -> dict:
        if not self.velocity_history or not self.obstacle_history:
            return {"type": "unknown", "reason": "数据不足"}

        recent_vel = self.velocity_history[-5:] if len(self.velocity_history) >= 5 else self.velocity_history
        recent_obs = self.obstacle_history[-5:] if len(self.obstacle_history) >= 5 else self.obstacle_history

        avg_linear = sum(v[1] for v in recent_vel) / len(recent_vel)
        avg_angular = sum(abs(v[2]) for v in recent_vel) / len(recent_vel)
        has_obstacle = any(o[1] for o in recent_obs)
        min_dist = min((o[2] for o in recent_obs if o[1]), default=float('inf'))

        if has_obstacle and min_dist < 2.0:
            if avg_linear > 0.3:
                return {
                    "type": "miss_avoidance",
                    "reason": f"检测到障碍物({min_dist:.2f}m)，速度未降低({avg_linear:.2f}m/s)",
                    "distance": min_dist,
                    "velocity": avg_linear
                }
            else:
                return {
                    "type": "normal",
                    "reason": f"正常避障，距离{min_dist:.2f}m，速度{avg_linear:.2f}m/s",
                    "distance": min_dist,
                    "velocity": avg_linear
                }
        elif not has_obstacle and (avg_linear < 0.05 or avg_angular > 0.5):
            return {
                "type": "false_avoidance",
                "reason": f"无障碍物，但速度降至{avg_linear:.2f}m/s，角速度{avg_angular:.2f}rad/s",
                "distance": float('inf'),
                "velocity": avg_linear
            }

        return {
            "type": "normal",
            "reason": "正常行驶",
            "distance": min_dist if has_obstacle else float('inf'),
            "velocity": avg_linear
        }


# ─── SSH 连接管理 ──────────────────────────────────────

class SSHConnection:
    def __init__(self, port: int):
        self.port = port
        self.client = None
        self.connected = False

    def connect(self) -> tuple[bool, str]:
        try:
            if self.client:
                try:
                    transport = self.client.get_transport()
                    if transport:
                        transport.close()
                except Exception:
                    pass
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            pkey = paramiko.RSAKey.from_private_key_file(SSH_KEY)
            self.client.connect(
                SSH_HOST, port=self.port,
                username=SSH_USER, pkey=pkey,
                timeout=30,
                banner_timeout=60,
                auth_timeout=30,
                look_for_keys=False,
                allow_agent=False,
            )
            # Set keepalive to prevent connection timeout
            transport = self.client.get_transport()
            if transport:
                transport.set_keepalive(10)
            self.connected = True
            print(f"SSH connected to port {self.port}")
            return True, ""
        except Exception as e:
            err_msg = str(e)
            print(f"SSH connection failed: {err_msg}")
            self.connected = False
            return False, err_msg

    def exec(self, cmd: str):
        """执行命令，返回 channel（不等待输出）"""
        if not self.connected:
            return None
        try:
            transport = self.client.get_transport()
            channel = transport.open_session()
            channel.exec_command(f"{ROS2_ENV} && {cmd}")
            return channel
        except Exception as e:
            print(f"SSH exec failed: {e}")
            self.connected = False
            return None

    def exec_output(self, cmd: str, timeout: float = 10.0) -> str:
        """执行命令并等待返回完整 stdout 字符串"""
        if not self.connected:
            return ""
        try:
            transport = self.client.get_transport()
            channel = transport.open_session()
            channel.exec_command(f"{ROS2_ENV} && {cmd}")
            deadline = time.time() + timeout
            output = ""
            while time.time() < deadline:
                if channel.recv_ready():
                    output += channel.recv(4096).decode('utf-8', errors='replace')
                if channel.exit_status_ready():
                    # 读完剩余数据
                    while channel.recv_ready():
                        output += channel.recv(4096).decode('utf-8', errors='replace')
                    break
                time.sleep(0.1)
            channel.close()
            return output
        except Exception as e:
            print(f"SSH exec_output failed: {e}")
            self.connected = False
            return ""

    def exec_output_raw(self, cmd: str, timeout: float = 10.0) -> str:
        """执行命令（不加载 ROS2 环境），返回完整 stdout 字符串"""
        if not self.connected:
            return ""
        try:
            transport = self.client.get_transport()
            channel = transport.open_session()
            channel.exec_command(cmd)
            deadline = time.time() + timeout
            output = ""
            while time.time() < deadline:
                if channel.recv_ready():
                    output += channel.recv(4096).decode('utf-8', errors='replace')
                if channel.exit_status_ready():
                    while channel.recv_ready():
                        output += channel.recv(4096).decode('utf-8', errors='replace')
                    break
                time.sleep(0.1)
            channel.close()
            return output
        except Exception as e:
            print(f"SSH exec_output_raw failed: {e}")
            self.connected = False
            return ""

    def sftp_download(self, remote_path: str, local_path: str, resumable: bool = False) -> tuple[bool, str]:
        """SFTP 下载文件或目录到本地，支持断点续传
        返回: (成功标志, 错误信息)
        """
        if not self.connected:
            return False, "SSH连接已断开"

        try:
            # 检查连接是否仍然有效
            transport = self.client.get_transport()
            if not transport or not transport.is_active():
                self.connected = False
                return False, "SSH连接已失效"

            sftp = self.client.open_sftp()
            # 设置SFTP超时
            sftp.get_channel().settimeout(30.0)

            try:
                remote_stat = sftp.stat(remote_path)
            except FileNotFoundError:
                sftp.close()
                return False, f"远程文件不存在: {remote_path}"
            except Exception as e:
                sftp.close()
                return False, f"无法访问远程文件: {str(e)}"

            if stat_mod.S_ISDIR(remote_stat.st_mode):
                os.makedirs(local_path, exist_ok=True)
                for item in sftp.listdir(remote_path):
                    remote_item = f"{remote_path}/{item}"
                    local_item = os.path.join(local_path, item)
                    item_stat = sftp.stat(remote_item)
                    if stat_mod.S_ISDIR(item_stat.st_mode):
                        os.makedirs(local_item, exist_ok=True)
                        for sub in sftp.listdir(remote_item):
                            remote_sub = f"{remote_item}/{sub}"
                            local_sub = os.path.join(local_item, sub)
                            success, err = self._sftp_get_file(sftp, remote_sub, local_sub, resumable)
                            if not success:
                                sftp.close()
                                return False, err
                    else:
                        success, err = self._sftp_get_file(sftp, remote_item, local_item, resumable)
                        if not success:
                            sftp.close()
                            return False, err
            else:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                success, err = self._sftp_get_file(sftp, remote_path, local_path, resumable)
                if not success:
                    sftp.close()
                    return False, err

            sftp.close()
            return True, ""
        except TimeoutError:
            self.connected = False
            return False, "传输超时，连接已断开"
        except EOFError:
            self.connected = False
            return False, "连接意外关闭"
        except Exception as e:
            error_msg = str(e)
            if "timed out" in error_msg.lower():
                self.connected = False
                return False, "网络超时，连接已断开"
            elif "connection" in error_msg.lower():
                self.connected = False
                return False, f"连接错误: {error_msg}"
            else:
                return False, f"下载失败: {error_msg}"

    def _sftp_get_file(self, sftp, remote_path: str, local_path: str, resumable: bool) -> tuple[bool, str]:
        """下载单个文件，支持断点续传
        返回: (成功标志, 错误信息)
        """
        try:
            if resumable and os.path.exists(local_path):
                # 检查本地文件大小
                local_size = os.path.getsize(local_path)
                remote_size = sftp.stat(remote_path).st_size

                # 如果本地文件已完整，跳过
                if local_size == remote_size:
                    print(f"File already complete, skipping: {local_path}")
                    return True, ""

                # 如果本地文件更大（异常情况），重新下载
                if local_size > remote_size:
                    print(f"Local file larger than remote, re-downloading: {local_path}")
                    os.remove(local_path)
                    sftp.get(remote_path, local_path)
                    return True, ""

                # 断点续传：从本地文件大小位置继续下载
                print(f"Resuming download from {local_size}/{remote_size} bytes: {local_path}")
                with open(local_path, 'ab') as local_file:
                    with sftp.file(remote_path, 'rb') as remote_file:
                        remote_file.seek(local_size)
                        while True:
                            chunk = remote_file.read(32768)  # 32KB chunks
                            if not chunk:
                                break
                            local_file.write(chunk)
            else:
                # 正常下载
                sftp.get(remote_path, local_path)

            return True, ""
        except TimeoutError:
            return False, f"文件传输超时: {os.path.basename(local_path)}"
        except Exception as e:
            return False, f"文件下载失败 {os.path.basename(local_path)}: {str(e)}"

    def _get_remote_dir_files(self, remote_path: str) -> dict[str, int]:
        """获取远程目录的所有文件及其大小"""
        if not self.connected:
            return {}
        try:
            sftp = self.client.open_sftp()
            files = {}

            def scan_dir(path: str, base_path: str):
                for item in sftp.listdir_attr(path):
                    item_path = f"{path}/{item.filename}"
                    if stat_mod.S_ISDIR(item.st_mode):
                        scan_dir(item_path, base_path)
                    else:
                        rel_path = item_path.replace(f"{base_path}/", "")
                        files[rel_path] = item.st_size

            scan_dir(remote_path, remote_path)
            sftp.close()
            return files
        except Exception as e:
            print(f"Error getting remote directory files: {e}")
            return {}

    def close(self):
        if self.client:
            self.client.close()
            self.connected = False


# ─── WebSocket 服务器 ──────────────────────────────────

class BridgeServer:
    def __init__(self):
        self.clients: set = set()
        self.ssh: SSHConnection | None = None
        self.analyzer = ObstacleAnalyzer()
        self.log_task = None
        self.topic_task = None

        # 避障监控任务
        self.obs_monitor_task = None

        # 录包状态
        self.recording = False
        self.record_task = None
        self.current_bag_name: str = ""
        self.last_record_end_time: float = 0.0

        # 避障检测防抖
        self.consecutive_avoidance_start: float | None = None
        self.consecutive_normal_start: float | None = None

    async def broadcast(self, msg: dict):
        if not self.clients:
            return
        data = json.dumps(msg)
        await asyncio.gather(
            *[ws.send(data) for ws in self.clients],
            return_exceptions=True
        )

    async def handle_client(self, websocket):
        self.clients.add(websocket)
        print(f"Client connected. Total: {len(self.clients)}")

        await websocket.send(json.dumps({
            "type": "bridge_status",
            "ssh_connected": self.ssh is not None and self.ssh.connected
        }))

        try:
            async for message in websocket:
                await self.handle_message(json.loads(message))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.discard(websocket)
            print(f"Client disconnected. Total: {len(self.clients)}")

    async def handle_message(self, msg: dict):
        action = msg.get("action")

        if action == "connect_ssh":
            port = msg.get("port", 10015)
            await self.connect_ssh(port)
        elif action == "disconnect_ssh":
            await self.disconnect_ssh()
        elif action in ("trigger_recording", "start_recording"):
            await self.trigger_recording(msg.get("reason", "manual"))
        elif action == "ros2_command":
            await self.exec_ros2_command(msg.get("command", ""))
        elif action == "bulk_upload_bags":
            asyncio.create_task(self._bulk_upload_bags())
        elif action == "start_obstacle_monitor":
            asyncio.create_task(self._start_obstacle_monitor())
        elif action == "stop_obstacle_monitor":
            await self._stop_obstacle_monitor()
        elif action == "check_and_start_monitor_service":
            asyncio.create_task(self._check_and_start_monitor_service())
        elif action == "stop_monitor_service":
            asyncio.create_task(self._stop_monitor_service())
        elif action == "upload_monitor_images":
            asyncio.create_task(self._upload_monitor_images(msg.get("date", "")))

    # ─── SSH 连接 / 断开 ───────────────────────────────

    async def connect_ssh(self, port: int):
        if self.ssh:
            self.ssh.close()

        self.ssh = SSHConnection(port)
        success, error_msg = await asyncio.get_event_loop().run_in_executor(
            None, self.ssh.connect
        )

        await self.broadcast({
            "type": "bridge_status",
            "ssh_connected": success,
            "port": port,
            "error": error_msg if not success else None
        })

        if success:
            await self._start_stream_tasks()

    async def _start_stream_tasks(self):
        """启动/重启日志和话题流任务"""
        if self.log_task and not self.log_task.done():
            self.log_task.cancel()
        if self.topic_task and not self.topic_task.done():
            self.topic_task.cancel()
        self.log_task = asyncio.create_task(self._stream_logs_with_recovery())
        self.topic_task = asyncio.create_task(self._stream_topics_with_recovery())

    async def disconnect_ssh(self):
        if self.log_task:
            self.log_task.cancel()
        if self.topic_task:
            self.topic_task.cancel()
        if self.record_task:
            self.record_task.cancel()
            self.record_task = None
        if self.obs_monitor_task and not self.obs_monitor_task.done():
            self.obs_monitor_task.cancel()
            self.obs_monitor_task = None
        self.recording = False
        self.consecutive_avoidance_start = None
        self.consecutive_normal_start = None
        if self.ssh:
            self.ssh.close()
            self.ssh = None

        await self.broadcast({"type": "bridge_status", "ssh_connected": False})

    # ─── 日志流（带自动重连）─────────────────────────────

    async def _stream_logs_with_recovery(self):
        """外层循环：stream_logs 异常退出后自动重连"""
        while True:
            try:
                await self.stream_logs()
            except asyncio.CancelledError:
                return
            except Exception as e:
                print(f"stream_logs crashed: {e}")

            # 只有 SSH 确实断开时才触发重连广播
            if not self.ssh or not self.ssh.connected:
                if not await self._try_reconnect_ssh():
                    return
            await asyncio.sleep(2)

    async def _stream_topics_with_recovery(self):
        """外层循环：stream_topics 异常退出后自动重连（带退避，避免频繁重试）"""
        fail_count = 0
        while True:
            try:
                await self.stream_topics()
                fail_count = 0
            except asyncio.CancelledError:
                return
            except Exception as e:
                fail_count += 1
                print(f"stream_topics crashed ({fail_count}): {e}")

            # 连续失败超过5次，停止话题流（话题可能不存在），不影响日志流
            if fail_count >= 5:
                print("stream_topics: too many failures, giving up topic streaming")
                return

            # 只有 SSH 确实断开时才触发重连广播
            if not self.ssh or not self.ssh.connected:
                if not await self._try_reconnect_ssh():
                    return
            # 退避延迟，避免疯狂重试
            await asyncio.sleep(min(5 * fail_count, 30))

    async def _try_reconnect_ssh(self) -> bool:
        """尝试重新建立 SSH 连接，最多重试3次"""
        if not self.ssh:
            return False
        port = self.ssh.port
        for attempt in range(1, 4):
            print(f"SSH reconnect attempt {attempt}/3 (port {port})")
            await self.broadcast({
                "type": "bridge_status",
                "ssh_connected": False,
                "reconnecting": True,
                "attempt": attempt
            })
            await asyncio.sleep(3 * attempt)
            success = await asyncio.get_event_loop().run_in_executor(
                None, self.ssh.connect
            )
            if success:
                await self.broadcast({
                    "type": "bridge_status",
                    "ssh_connected": True,
                    "port": port
                })
                print(f"SSH reconnected on attempt {attempt}")
                return True

        await self.broadcast({
            "type": "bridge_status",
            "ssh_connected": False,
            "reconnecting": False,
            "reason": "重连失败，请手动重连"
        })
        return False

    async def stream_logs(self):
        """实时流式读取 robot_decision 最新日志"""
        if not self.ssh:
            return

        # 找到最新的 robot_decision_*.log 文件
        find_cmd = "ls -t /userdata/log_dir/ros2_log/robot_decision_*.log 2>/dev/null | head -1"
        latest_log = await asyncio.get_event_loop().run_in_executor(
            None, self.ssh.exec_output, find_cmd
        )
        latest_log = (latest_log or "").strip()
        if not latest_log:
            # fallback to all logs
            cmd = "tail -f /userdata/log_dir/ros2_log/*.log 2>/dev/null"
        else:
            cmd = f"tail -f {latest_log}"

        channel = await asyncio.get_event_loop().run_in_executor(
            None, self.ssh.exec, cmd
        )
        if not channel:
            raise ConnectionError("SSH exec returned None for stream_logs")

        print("Log streaming started")
        try:
            while True:
                if channel.recv_ready():
                    data = channel.recv(4096).decode('utf-8', errors='replace')
                    for line in data.splitlines():
                        if line.strip():
                            await self.process_log_line(line)
                elif channel.exit_status_ready():
                    raise ConnectionError("Log channel closed by remote")
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            channel.close()
            raise

    async def process_log_line(self, line: str):
        is_avoiding = 'AVOIDING' in line
        is_relevant = is_avoiding or any(kw.lower() in line.lower() for kw in OBSTACLE_KEYWORDS)

        msg = {
            "type": "log",
            "timestamp": time.time(),
            "text": line,
            "relevant": is_relevant,
            "avoiding": is_avoiding
        }

        # Parse velocity/angular from decision log: e.g. "linear=0.5 angular=0.1" or "v=0.5 w=0.1"
        vel_match = re.search(r'(?:linear[=:\s]+|v[=:\s]+)([0-9.-]+).*?(?:angular[=:\s]+|w[=:\s]+)([0-9.-]+)', line, re.I)
        if vel_match:
            linear = float(vel_match.group(1))
            angular = float(vel_match.group(2))
            self.analyzer.update_velocity(linear, angular)
            await self.broadcast({
                "type": "cmd_vel",
                "timestamp": time.time(),
                "linear": linear,
                "angular": angular
            })

        # Detect obstacle distance
        dist_match = re.search(r'dist(?:ance)?[=:\s]+([0-9.]+)', line, re.I)
        if dist_match:
            distance = float(dist_match.group(1))
            self.analyzer.update_obstacle(True, distance)
            msg["obstacle"] = {"detected": True, "distance": distance}

        # AVOIDING field triggers obstacle status
        if is_avoiding:
            self.analyzer.update_obstacle(True, 0.0)
            await self.broadcast_analysis()

        await self.broadcast(msg)

        if is_relevant and not is_avoiding:
            await self.broadcast_analysis()
    async def stream_topics(self):
        """订阅关键 ROS2 话题"""
        if not self.ssh:
            return

        cmd = "ros2 topic echo /chassis/cmd_vel --no-arr 2>/dev/null"
        channel = await asyncio.get_event_loop().run_in_executor(
            None, self.ssh.exec, cmd
        )
        if not channel:
            raise ConnectionError("SSH exec returned None for stream_topics")

        print("Topic streaming started")
        buffer = ""
        try:
            while True:
                if channel.recv_ready():
                    data = channel.recv(4096).decode('utf-8', errors='replace')
                    buffer += data
                    if "---" in buffer:
                        parts = buffer.split("---")
                        for part in parts[:-1]:
                            await self.parse_cmd_vel(part.strip())
                        buffer = parts[-1]
                elif channel.exit_status_ready():
                    raise ConnectionError("Topic channel closed by remote")
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            channel.close()
            raise

    async def parse_cmd_vel(self, yaml_text: str):
        linear_match = re.search(r'x:\s*([0-9.-]+)', yaml_text)
        angular_match = re.search(r'z:\s*([0-9.-]+)', yaml_text)

        if linear_match and angular_match:
            linear = float(linear_match.group(1))
            angular = float(angular_match.group(1))
            self.analyzer.update_velocity(linear, angular)

            await self.broadcast({
                "type": "cmd_vel",
                "timestamp": time.time(),
                "linear": linear,
                "angular": angular
            })

            await self.broadcast_analysis()

    # ─── 避障分析 + 防抖 ──────────────────────────────────

    async def broadcast_analysis(self):
        result = self.analyzer.analyze()
        result["type_label"] = result["type"]
        result["timestamp"] = time.time()

        await self.broadcast({
            "type": "obstacle_analysis",
            **result
        })

        is_abnormal = result["type_label"] in ("miss_avoidance", "false_avoidance")

        if is_abnormal:
            # 重置恢复计时
            self.consecutive_normal_start = None
            # 累计触发计时
            if self.consecutive_avoidance_start is None:
                self.consecutive_avoidance_start = time.time()
            elapsed = time.time() - self.consecutive_avoidance_start
            if elapsed >= CONSECUTIVE_THRESHOLD and not self.recording:
                await self.trigger_recording(result["type_label"])
        else:
            # 重置触发计时
            self.consecutive_avoidance_start = None
            if self.recording:
                # 需要连续 RECOVERY_THRESHOLD 秒正常才停录
                if self.consecutive_normal_start is None:
                    self.consecutive_normal_start = time.time()
                if time.time() - self.consecutive_normal_start >= RECOVERY_THRESHOLD:
                    self.consecutive_normal_start = None
                    await self.stop_recording()
            else:
                self.consecutive_normal_start = None

    # ─── 录包触发（带前置检查）────────────────────────────

    async def trigger_recording(self, reason: str = "manual"):
        if not self.ssh or not self.ssh.connected:
            return
        if self.recording:
            return

        # Pause log/topic streaming to free SSH channels during recording
        await self._pause_streams()

        # 冷却检查
        cooldown_remaining = RECORD_COOLDOWN - (time.time() - self.last_record_end_time)
        if cooldown_remaining > 0:
            await self.broadcast({
                "type": "record_status",
                "status": "cooldown",
                "cooldown_seconds": int(cooldown_remaining),
                "reason": f"冷却中，还需等待 {cooldown_remaining:.0f}s"
            })
            await self._resume_streams()
            return

        loop = asyncio.get_event_loop()

        # 检查脚本是否存在
        check_out = await loop.run_in_executor(
            None, self.ssh.exec_output, f"test -f {SCRIPT_PATH} && echo OK"
        )
        if "OK" not in check_out:
            await self.broadcast({
                "type": "record_status",
                "status": "error",
                "reason": f"录包脚本不存在: {SCRIPT_PATH}"
            })
            await self._resume_streams()
            return

        # 检查磁盘空间
        df_out = await loop.run_in_executor(
            None, self.ssh.exec_output,
            "df /userdata --output=avail -BM 2>/dev/null | tail -1"
        )
        try:
            avail_mb = int(df_out.strip().replace('M', '').strip())
        except ValueError:
            avail_mb = 0
        if avail_mb < DISK_MIN_MB:
            await self.broadcast({
                "type": "record_status",
                "status": "error",
                "reason": f"磁盘空间不足（剩余 {avail_mb}MB，需要 {DISK_MIN_MB}MB）"
            })
            await self._resume_streams()
            return

        # 执行录包脚本（后台），固定录制 MANUAL_RECORD_SECONDS 秒后自动 kill
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bag_name = f"{reason}_{timestamp}"
        # 完整 source 环境后进入脚本目录执行，后台运行，30s 后自动 kill
        cmd = (
            "source /opt/ros/humble/setup.bash && "
            "source ~/.bashrc 2>/dev/null; "
            "source /app/BestMow/install/setup.bash && "
            f"cd /app/BestMow/debug_sh && "
            f"bash rosbag_record_perception_navigation.sh > /tmp/bag_record.log 2>&1 & "
            f"BGPID=$! && "
            f"sleep {MANUAL_RECORD_SECONDS} && "
            f"pkill -f 'ros2 bag record' 2>/dev/null; "
            f"pkill -f 'rosbag_record_perception' 2>/dev/null &"
        )
        await loop.run_in_executor(None, self.ssh.exec, cmd)

        # 等待 5s 后确认进程存在（ros2 bag record 启动较慢）
        await asyncio.sleep(5)
        pid_out = await loop.run_in_executor(
            None, self.ssh.exec_output, "pgrep -f 'ros2 bag record'"
        )
        if not pid_out.strip():
            await self.broadcast({
                "type": "record_status",
                "status": "error",
                "reason": "录包进程未启动，请检查 /tmp/bag_record.log"
            })
            await self._resume_streams()
            return

        # 确认成功后才设置状态
        self.recording = True
        self.current_bag_name = bag_name

        await self.broadcast({
            "type": "record_status",
            "status": "recording",
            "bag_name": bag_name,
            "reason": reason,
            "duration": MANUAL_RECORD_SECONDS,
            "timestamp": time.time()
        })
        print(f"Recording started: {bag_name}, will stop in {MANUAL_RECORD_SECONDS}s")

        # 录包脚本已在机器后台运行，立即恢复日志/话题流
        await self._resume_streams()

        if self.record_task:
            self.record_task.cancel()
        # 手动录包：固定时长后自动停止
        duration = MANUAL_RECORD_SECONDS if reason == "manual" else RECORD_MAX_SECONDS
        self.record_task = asyncio.create_task(self._record_watchdog(duration))

    async def _pause_streams(self):
        """Cancel log/topic streaming tasks to free SSH channels during recording."""
        if self.log_task and not self.log_task.done():
            self.log_task.cancel()
            self.log_task = None
        if self.topic_task and not self.topic_task.done():
            self.topic_task.cancel()
            self.topic_task = None
        print("Log/topic streaming paused for recording")

    async def _resume_streams(self):
        """Restart log/topic streaming after recording completes."""
        if self.ssh and self.ssh.connected:
            await self._start_stream_tasks()
            print("Log/topic streaming resumed")

    async def stop_recording(self):
        if not self.recording:
            return
        if self.record_task:
            self.record_task.cancel()
            self.record_task = None

        if self.ssh and self.ssh.connected:
            await asyncio.get_event_loop().run_in_executor(
                None, self.ssh.exec_output,
                "pkill -f 'ros2 bag record' 2>/dev/null; pkill -f 'rosbag_record' 2>/dev/null"
            )

        self.recording = False
        self.last_record_end_time = time.time()
        bag_name = self.current_bag_name

        await self.broadcast({
            "type": "record_status",
            "status": "completed",
            "bag_name": bag_name,
            "timestamp": time.time()
        })
        print(f"Recording stopped: {bag_name}")

        # Resume log/topic streaming
        asyncio.create_task(self._resume_streams())

    async def _record_watchdog(self, max_seconds: int):
        """录包最长时间看门狗"""
        await asyncio.sleep(max_seconds)
        if self.recording:
            print(f"Recording watchdog: reached {max_seconds}s, stopping")
            self.record_task = None  # 先清空自身引用，避免 stop_recording 取消自身
            await self.stop_recording()

    # ─── SFTP 下载 ────────────────────────────────────────

    async def _download_bag(self, bag_name: str):
        """用 paramiko SFTP 把录包从机器拉到 PC 的 bags/ 目录"""
        if not self.ssh or not self.ssh.connected:
            await self.broadcast({
                "type": "upload_status",
                "status": "error",
                "bag_name": bag_name,
                "reason": "SSH 未连接，无法下载"
            })
            return

        await self.broadcast({
            "type": "upload_status",
            "status": "downloading",
            "bag_name": bag_name
        })

        loop = asyncio.get_event_loop()

        # 找到机器端最新的 bag（按时间排序，匹配 reason 前缀）
        ls_out = await loop.run_in_executor(
            None, self.ssh.exec_output,
            f"ls -1t {REMOTE_BAG_DIR} 2>/dev/null | head -10"
        )
        candidates = [
            f.strip() for f in ls_out.splitlines()
            if f.strip() and bag_name.split('_')[0] in f
        ]

        if not candidates:
            # 退而求其次：取最新的一个
            all_files = [f.strip() for f in ls_out.splitlines() if f.strip()]
            if all_files:
                candidates = [all_files[0]]
            else:
                await self.broadcast({
                    "type": "upload_status",
                    "status": "error",
                    "bag_name": bag_name,
                    "reason": f"在 {REMOTE_BAG_DIR} 找不到录包文件"
                })
                return

        remote_bag = candidates[0]
        remote_path = f"{REMOTE_BAG_DIR}/{remote_bag}"
        os.makedirs(BAGS_DIR, exist_ok=True)
        local_path = os.path.join(BAGS_DIR, remote_bag)

        print(f"Downloading bag: {remote_path} -> {local_path}")

        success, error_msg = await loop.run_in_executor(
            None, self.ssh.sftp_download, remote_path, local_path, False
        )

        if success:
            await self.broadcast({
                "type": "upload_status",
                "status": "done",
                "bag_name": remote_bag,
                "local_path": local_path
            })
            print(f"Bag downloaded: {local_path}")
        else:
            await self.broadcast({
                "type": "upload_status",
                "status": "error",
                "bag_name": bag_name,
                "reason": error_msg or "SFTP 下载失败，请检查网络或权限"
            })

    # ─── 批量上传：从机器 /userdata/rosbag_record 下载到 PC ─────────────────────────────────

    async def _bulk_upload_bags(self):
        """通过 SFTP 将机器端 /userdata/rosbag_record 下所有录包下载到 PC，根据端口号确定上传路径"""
        if not self.ssh or not self.ssh.connected:
            await self.broadcast({
                "type": "bulk_upload_status",
                "status": "error",
                "reason": "SSH 未连接，无法上传"
            })
            return

        # 根据端口号确定上传路径：取末四位作为子目录，使用项目内 data/uploads
        port = self.ssh.port
        port_suffix = str(port)[-4:]  # 取末四位，如 10123 -> 0123, 10113 -> 0113
        upload_dest = os.path.join(PROJECT_ROOT, f"data/uploads/{port_suffix}/rosbag")

        loop = asyncio.get_event_loop()
        await self.broadcast({"type": "bulk_upload_status", "status": "progress", "current": "扫描机器录包目录..."})

        # 列出机器端录包目录（不加载 ROS2 环境，避免 source 输出污染结果）
        ls_out = await loop.run_in_executor(
            None, self.ssh.exec_output_raw,
            f"ls -1 {REMOTE_BAG_DIR} 2>/dev/null"
        )
        entries = [e.strip() for e in ls_out.splitlines() if e.strip() and not e.startswith('/')]
        if not entries:
            await self.broadcast({
                "type": "bulk_upload_status",
                "status": "error",
                "reason": f"机器端 {REMOTE_BAG_DIR} 目录为空或不存在"
            })
            return

        os.makedirs(upload_dest, exist_ok=True)
        copied = 0
        skipped = 0
        resumed = 0

        # 只上传当天的录包（名称中含今日日期 YYYYMMDD）
        today = datetime.now().strftime("%Y%m%d")
        today_entries = [e for e in entries if today[2:] in e or today in e]  # 支持 260325 或 20260325
        if not today_entries:
            await self.broadcast({
                "type": "bulk_upload_status",
                "status": "error",
                "reason": f"今天({today})没有录包文件"
            })
            return
        entries = today_entries

        for name in entries:
            remote_path = f"{REMOTE_BAG_DIR}/{name}"
            local_path = os.path.join(upload_dest, name)

            # 检查是否需要下载或续传
            is_resume = False
            should_skip = False

            if os.path.exists(local_path):
                if os.path.isdir(local_path):
                    # 对于目录（rosbag），需要验证完整性
                    try:
                        # 获取远程目录的文件列表和大小
                        loop_ref = asyncio.get_event_loop()
                        remote_files = await loop_ref.run_in_executor(
                            None, self._get_remote_dir_files, remote_path
                        )

                        # 检查本地目录的文件
                        local_files = {}
                        if os.path.isdir(local_path):
                            for root, dirs, files in os.walk(local_path):
                                for f in files:
                                    full_path = os.path.join(root, f)
                                    rel_path = os.path.relpath(full_path, local_path)
                                    local_files[rel_path] = os.path.getsize(full_path)

                        # 比较文件完整性
                        is_complete = True
                        missing_files = []
                        incomplete_files = []
                        for remote_file, remote_size in remote_files.items():
                            if remote_file not in local_files:
                                is_complete = False
                                is_resume = True
                                missing_files.append(remote_file)
                            elif local_files[remote_file] != remote_size:
                                is_complete = False
                                is_resume = True
                                incomplete_files.append(f"{remote_file} ({local_files[remote_file]}/{remote_size})")

                        if is_complete and len(local_files) == len(remote_files):
                            should_skip = True
                            skipped += 1
                            print(f"Skipping complete directory: {name}")
                            await self.broadcast({
                                "type": "bulk_upload_status",
                                "status": "progress",
                                "current": f"✓ 已完整: {name} ({copied + resumed + skipped}/{len(entries)})"
                            })
                            continue
                        else:
                            # 目录不完整，需要续传
                            print(f"Resuming incomplete directory: {name}")
                            print(f"  Missing files: {len(missing_files)}")
                            print(f"  Incomplete files: {len(incomplete_files)}")
                    except Exception as e:
                        print(f"Error checking directory completeness: {e}")
                        # 如果检查失败，重新下载
                        is_resume = False
                else:
                    # 单个文件的断点续传
                    is_resume = True

            await self.broadcast({
                "type": "bulk_upload_status",
                "status": "progress",
                "current": f"{'续传' if is_resume else '下载'}: {name} ({copied + resumed + 1}/{len(entries)})"
            })

            # 检查SSH连接状态
            if not self.ssh or not self.ssh.connected:
                await self.broadcast({
                    "type": "bulk_upload_status",
                    "status": "error",
                    "reason": "SSH连接已断开，上传中止"
                })
                return

            success, error_msg = await loop.run_in_executor(
                None, self.ssh.sftp_download, remote_path, local_path, True  # 启用断点续传
            )

            if success:
                if is_resume:
                    resumed += 1
                else:
                    copied += 1
                print(f"bulk_upload {'resumed' if is_resume else 'downloaded'}: {remote_path} -> {local_path}")
            else:
                print(f"bulk_upload failed: {remote_path}, error: {error_msg}")
                await self.broadcast({
                    "type": "bulk_upload_status",
                    "status": "error",
                    "reason": f"下载失败: {name} - {error_msg}"
                })
                # 如果是连接问题，立即中止
                if "连接" in error_msg or "超时" in error_msg or "断开" in error_msg:
                    return

        summary_parts = []
        if copied > 0:
            summary_parts.append(f"新下载 {copied} 个")
        if resumed > 0:
            summary_parts.append(f"续传 {resumed} 个")
        if skipped > 0:
            summary_parts.append(f"跳过 {skipped} 个")

        summary = "、".join(summary_parts) if summary_parts else "无文件处理"

        await self.broadcast({
            "type": "bulk_upload_status",
            "status": "done",
            "copied": copied,
            "resumed": resumed,
            "skipped": skipped,
            "dest": upload_dest,
            "summary": summary
        })

    # ─── 避障日志监控 ─────────────────────────────────────

    async def _start_obstacle_monitor(self):
        await self._stop_obstacle_monitor()
        if not self.ssh or not self.ssh.connected:
            await self.broadcast({"type": "obstacle_monitor_status", "status": "error", "reason": "SSH 未连接"})
            return
        self.obs_monitor_task = asyncio.create_task(self._stream_obstacle_monitor())

    async def _stop_obstacle_monitor(self):
        if self.obs_monitor_task and not self.obs_monitor_task.done():
            self.obs_monitor_task.cancel()
            self.obs_monitor_task = None
        await self.broadcast({"type": "obstacle_monitor_status", "status": "stopped"})

    async def _stream_obstacle_monitor(self):
        if not self.ssh:
            return
        loop = asyncio.get_event_loop()

        # Find the latest stereo_perception_multi*.log (raw, no ROS2 env)
        find_cmd = "ls -t /userdata/log_dir/ros2_log/stereo_perception_multi*.log 2>/dev/null | head -1"
        latest_log = await loop.run_in_executor(None, self.ssh.exec_output_raw, find_cmd)
        latest_log = (latest_log or "").strip()
        if not latest_log:
            # fallback to any stereo_perception log
            find_cmd2 = "ls -t /userdata/log_dir/ros2_log/stereo_perception*.log 2>/dev/null | head -1"
            latest_log = await loop.run_in_executor(None, self.ssh.exec_output_raw, find_cmd2)
            latest_log = (latest_log or "").strip()
        if not latest_log:
            await self.broadcast({"type": "obstacle_monitor_status", "status": "error", "reason": "未找到 stereo_perception*.log 文件"})
            return

        # Open raw channel (no ROS2 env sourcing) so tail -f output is not delayed
        def _open_tail_channel(path: str):
            try:
                transport = self.ssh.client.get_transport()
                channel = transport.open_session()
                channel.exec_command(f"tail -n 0 -f {path}")
                return channel
            except Exception as e:
                print(f"obs monitor tail channel failed: {e}")
                return None

        channel = await loop.run_in_executor(None, _open_tail_channel, latest_log)
        if not channel:
            await self.broadcast({"type": "obstacle_monitor_status", "status": "error", "reason": "无法启动日志监控"})
            return

        await self.broadcast({"type": "obstacle_monitor_status", "status": "started"})
        print(f"Obstacle monitor streaming: {latest_log}")
        try:
            while True:
                if channel.recv_ready():
                    data = channel.recv(4096).decode('utf-8', errors='replace')
                    for line in data.splitlines():
                        if line.strip():
                            await self.broadcast({"type": "obstacle_monitor_log", "line": line})
                elif channel.exit_status_ready():
                    await self.broadcast({"type": "obstacle_monitor_status", "status": "error", "reason": "日志通道已关闭"})
                    return
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            channel.close()
            raise
        except Exception as e:
            await self.broadcast({"type": "obstacle_monitor_status", "status": "error", "reason": str(e)})

    # ─── 监控拍照服务管理 ──────────────────────────────────

    async def _check_and_start_monitor_service(self):
        """停止旧服务，部署并启动 monitor_mow_obstacle.service"""
        if not self.ssh or not self.ssh.connected:
            await self.broadcast({"type": "monitor_service_status", "status": "error", "reason": "SSH 未连接"})
            return

        loop = asyncio.get_event_loop()
        old_service = "monitor_daytime_falseblock.service"
        new_service = "monitor_mow_obstacle.service"
        # 本地脚本和服务文件路径：使用项目内 script 目录
        local_script = os.path.join(PROJECT_ROOT, "script/monitor_mow_obstacle.sh")
        local_service = os.path.join(PROJECT_ROOT, "script/monitor_mow_obstacle.service")
        remote_script = "/userdata/bestmow_data/image_perception_debug/monitor_mow_obstacle.sh"
        remote_service = f"/etc/systemd/system/{new_service}"

        # 停止并禁用旧服务和同名服务，避免覆盖运行中的 unit/script
        await loop.run_in_executor(
            None, self.ssh.exec_output_raw,
            f"systemctl stop {old_service} 2>/dev/null; systemctl disable {old_service} 2>/dev/null"
        )
        await loop.run_in_executor(
            None, self.ssh.exec_output_raw,
            f"systemctl stop {new_service} 2>/dev/null; systemctl disable {new_service} 2>/dev/null"
        )

        # 确保远端目录存在（先单独执行，不与 SFTP 混用）
        await loop.run_in_executor(
            None, self.ssh.exec_output_raw,
            "mkdir -p /userdata/bestmow_data/image_perception_debug"
        )
        cleanup_out = await loop.run_in_executor(
            None, self.ssh.exec_output_raw,
            f"[ -f {remote_service} ] && rm -f {remote_service}; [ -f {remote_script} ] && rm -f {remote_script}"
        )
        if cleanup_out and cleanup_out.strip():
            await self.broadcast({"type": "monitor_service_status", "status": "error", "reason": f"清理旧服务文件失败: {cleanup_out.strip()}"})
            return

        # 上传脚本和服务文件（独立连接，避免复用 transport 导致 EOF）
        upload_error = [None]
        port = self.ssh.port

        def _upload_files():
            """使用 SCP 上传文件，因为远程 SFTP 子系统不可用"""
            max_retries = 3
            retry_delay = 2

            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        print(f"SCP upload retry {attempt}/{max_retries}")
                        import time
                        time.sleep(retry_delay)

                    # 使用 subprocess 调用 scp 命令
                    import subprocess

                    # 确保远端目录存在
                    mkdir_cmd = [
                        "ssh", "-i", SSH_KEY,
                        "-o", "StrictHostKeyChecking=no",
                        "-o", "ConnectTimeout=30",
                        "-o", "ServerAliveInterval=10",
                        "-o", "ServerAliveCountMax=3",
                        "-p", str(port),
                        f"{SSH_USER}@{SSH_HOST}",
                        "mkdir -p /userdata/bestmow_data/image_perception_debug /etc/systemd/system"
                    ]
                    subprocess.run(mkdir_cmd, capture_output=True, timeout=30, check=False)

                    # 上传脚本文件
                    scp_script_cmd = [
                        "scp", "-i", SSH_KEY,
                        "-o", "StrictHostKeyChecking=no",
                        "-o", "ConnectTimeout=30",
                        "-o", "ServerAliveInterval=10",
                        "-o", "ServerAliveCountMax=3",
                        "-P", str(port),
                        local_script,
                        f"{SSH_USER}@{SSH_HOST}:{remote_script}"
                    ]
                    result = subprocess.run(scp_script_cmd, capture_output=True, text=True, timeout=60)
                    if result.returncode != 0:
                        raise Exception(f"SCP script upload failed: {result.stderr}")

                    # 设置脚本可执行权限
                    chmod_cmd = [
                        "ssh", "-i", SSH_KEY,
                        "-o", "StrictHostKeyChecking=no",
                        "-o", "ConnectTimeout=30",
                        "-p", str(port),
                        f"{SSH_USER}@{SSH_HOST}",
                        f"chmod 755 {remote_script}"
                    ]
                    subprocess.run(chmod_cmd, capture_output=True, timeout=30, check=False)

                    # 上传服务文件
                    scp_service_cmd = [
                        "scp", "-i", SSH_KEY,
                        "-o", "StrictHostKeyChecking=no",
                        "-o", "ConnectTimeout=30",
                        "-o", "ServerAliveInterval=10",
                        "-o", "ServerAliveCountMax=3",
                        "-P", str(port),
                        local_service,
                        f"{SSH_USER}@{SSH_HOST}:{remote_service}"
                    ]
                    result = subprocess.run(scp_service_cmd, capture_output=True, text=True, timeout=60)
                    if result.returncode != 0:
                        raise Exception(f"SCP service upload failed: {result.stderr}")

                    print(f"SCP upload successful on attempt {attempt + 1}")
                    return True

                except Exception as e:
                    error_msg = str(e)
                    upload_error[0] = error_msg
                    print(f"SCP upload failed (attempt {attempt + 1}/{max_retries}): {error_msg}")

                    # Check if it's a transient error worth retrying
                    is_transient = any(err in error_msg for err in [
                        "Connection reset",
                        "Connection timed out",
                        "Timeout",
                        "Connection refused",
                    ])

                    if not is_transient or attempt >= max_retries - 1:
                        return False

            return False

        upload_ok = await loop.run_in_executor(None, _upload_files)
        if not upload_ok:
            reason = f"脚本/服务文件上传失败: {upload_error[0]}" if upload_error[0] else "脚本/服务文件上传失败"
            await self.broadcast({"type": "monitor_service_status", "status": "error", "reason": reason})
            return

        # daemon-reload
        await loop.run_in_executor(
            None, self.ssh.exec_output_raw,
            "systemctl daemon-reload 2>/dev/null"
        )

        # 检查 enabled 状态
        enabled_out = await loop.run_in_executor(
            None, self.ssh.exec_output_raw,
            f"systemctl is-enabled {new_service} 2>/dev/null"
        )
        enabled = enabled_out.strip() == "enabled"

        if not enabled:
            await loop.run_in_executor(
                None, self.ssh.exec_output_raw,
                f"systemctl enable {new_service} 2>/dev/null"
            )

        # 检查 active 状态
        active_out = await loop.run_in_executor(
            None, self.ssh.exec_output_raw,
            f"systemctl is-active {new_service} 2>/dev/null"
        )
        is_active = active_out.strip() == "active"

        if not is_active:
            await loop.run_in_executor(
                None, self.ssh.exec_output_raw,
                f"systemctl start {new_service} 2>/dev/null"
            )
            active_out2 = await loop.run_in_executor(
                None, self.ssh.exec_output_raw,
                f"systemctl is-active {new_service} 2>/dev/null"
            )
            is_active = active_out2.strip() == "active"
            if is_active:
                await self.broadcast({"type": "monitor_service_status", "status": "started", "enabled": True})
            else:
                await self.broadcast({"type": "monitor_service_status", "status": "error", "reason": "启动失败，请检查服务日志"})
        else:
            await self.broadcast({"type": "monitor_service_status", "status": "running", "enabled": enabled})

    async def _stop_monitor_service(self):
        """停止 monitor_mow_obstacle.service"""
        if not self.ssh or not self.ssh.connected:
            await self.broadcast({"type": "monitor_service_status", "status": "error", "reason": "SSH 未连接"})
            return

        loop = asyncio.get_event_loop()
        service = "monitor_mow_obstacle.service"

        await loop.run_in_executor(
            None, self.ssh.exec_output_raw,
            f"systemctl stop {service} 2>/dev/null"
        )
        await loop.run_in_executor(
            None, self.ssh.exec_output_raw,
            f"systemctl disable {service} 2>/dev/null"
        )
        active_out = await loop.run_in_executor(
            None, self.ssh.exec_output_raw,
            f"systemctl is-active {service} 2>/dev/null"
        )
        is_active = active_out.strip() == "active"
        if not is_active:
            await self.broadcast({"type": "monitor_service_status", "status": "stopped"})
        else:
            await self.broadcast({"type": "monitor_service_status", "status": "error", "reason": "停止失败"})

    async def _upload_monitor_images(self, date: str):
        """将指定日期目录的图片从端口10123机器下载到本地 data/uploads/<date>"""
        IMAGE_PORT = get_default_port("stereo_analysis")
        remote_dir = f"/userdata/bestmow_data/image_perception_debug/{date}"
        local_dest = os.path.join(PROJECT_ROOT, f"data/uploads/{date}")
        loop = asyncio.get_event_loop()

        await self.broadcast({"type": "image_upload_status", "status": "progress", "current": f"连接端口 {IMAGE_PORT} 机器..."})

        ssh = SSHConnection(IMAGE_PORT)
        ok = await loop.run_in_executor(None, ssh.connect)
        if not ok:
            await self.broadcast({"type": "image_upload_status", "status": "error", "reason": f"连接端口 {IMAGE_PORT} 失败"})
            return

        try:
            ls_out = await loop.run_in_executor(
                None, ssh.exec_output_raw,
                f"ls -1 {remote_dir} 2>/dev/null"
            )
            files = [f.strip() for f in ls_out.splitlines() if f.strip()]
            if not files:
                await self.broadcast({"type": "image_upload_status", "status": "error", "reason": f"远程目录 {remote_dir} 为空或不存在"})
                return

            os.makedirs(local_dest, exist_ok=True)
            copied = 0

            def _download_files():
                nonlocal copied
                try:
                    sftp = ssh.client.open_sftp()
                    for fname in files:
                        try:
                            sftp.get(f"{remote_dir}/{fname}", os.path.join(local_dest, fname))
                            copied += 1
                        except Exception as e:
                            print(f"download failed {fname}: {e}")
                    sftp.close()
                    return True
                except Exception as e:
                    print(f"SFTP session failed: {e}")
                    return False

            await self.broadcast({"type": "image_upload_status", "status": "progress", "current": f"下载 {len(files)} 张图片中..."})
            ok = await loop.run_in_executor(None, _download_files)
            if ok:
                await self.broadcast({"type": "image_upload_status", "status": "done", "copied": copied, "dest": local_dest})
            else:
                await self.broadcast({"type": "image_upload_status", "status": "error", "reason": "SFTP 下载失败"})
        finally:
            ssh.close()

    # ─── 任意 ROS2 命令 ───────────────────────────────────

    async def exec_ros2_command(self, cmd: str):
        if not self.ssh or not self.ssh.connected:
            await self.broadcast({"type": "command_result", "error": "SSH not connected"})
            return

        output = await asyncio.get_event_loop().run_in_executor(
            None, self.ssh.exec_output, cmd
        )
        await self.broadcast({
            "type": "command_result",
            "command": cmd,
            "output": output,
            "timestamp": time.time()
        })


# ─── 入口 ──────────────────────────────────────────────

async def main():
    server = BridgeServer()
    print(f"SSH Bridge WebSocket server starting on ws://{WS_HOST}:{WS_PORT}")

    async with websockets.serve(server.handle_client, WS_HOST, WS_PORT):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
