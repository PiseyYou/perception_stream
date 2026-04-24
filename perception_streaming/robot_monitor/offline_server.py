#!/usr/bin/env python3
from __future__ import annotations
"""
Offline Perception Test Server
提供 HTTP API 用于配置和执行离线感知测试，通过 SSE 推送进度
端口: 8769
"""

import glob
import json
import os
import re
import shutil
import sqlite3
import struct
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from threading import Thread
from urllib.parse import urlparse, parse_qs
from config_loader import get_ssh_key_path, get_ssh_host, get_ssh_user, get_default_port

try:
    from PIL import Image
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("WARNING: PIL not available, stereo image concatenation will be disabled")

OFFLINE_SERVER_PORT = 8769
# Get the project root directory (parent of robot_monitor)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Use relative paths from project root, convert to absolute paths
OFFLINE_EXE = os.path.abspath(os.path.join(PROJECT_ROOT, "bin/offline_perception_debug_432"))
NIGHT_EXE = os.path.abspath(os.path.join(PROJECT_ROOT, "night_offline_debug/build/run_cdt_dsg_fusion_dir"))
OFFLINE_LIB = os.path.abspath(os.path.join(PROJECT_ROOT, "lib/dnn_x86"))
MONO_EXE = os.path.abspath(os.path.join(PROJECT_ROOT, "bin/dsg_mono_perception"))
MONO_MODEL = os.path.abspath(os.path.join(PROJECT_ROOT, "models/dsg_multi_20260407_640x384.bin"))
DSG_MODEL = os.path.abspath(os.path.join(PROJECT_ROOT, "models/dsg_multi_20260407_640x384.bin"))
CDT_MODEL = os.path.abspath(os.path.join(PROJECT_ROOT, "models/cdt_20251125_640x384.bin"))

# BAG_DATA_DIR is set by vite.config.ts via env var, fallback to default
BAG_DATA_DIR = os.environ.get(
    "BAG_DATA_DIR",
    "/home/youfeng/debug/03/19/rosbag_LK-MR6P1US000111_camera_202603190309/stereo_output_rosbag_LK-MR6P1US000111_camera_202603190309_0"
)

INFER_MODES = {
    0: "Disable",
    1: "Depth Only",
    2: "Detection",
    3: "Segmentation",
    4: "CS/QR",
    5: "Multi-task",
    6: "Sub-perception",
    7: "DSG Nighttime",
}

# Point cloud filtering parameters for offline debug
# Only label=1 (background) causes false obstacle avoidance and should be filtered
# label=5 is real obstacle and should be kept
MIN_DISTANCE = 0.3  # meters, filter out close-range noise
MAX_DISTANCE = 10.0  # meters, filter out far-range noise
MIN_OBSTACLE_HEIGHT = 0.5  # meters, filter ground-level points (grass misclassified as background)
MAX_HEIGHT = 2.0  # meters, filter out points too high (likely noise)

_current_proc: subprocess.Popen | None = None
_sse_clients: list = []
_last_result: dict = {}
_running = False
_docker_sessions: dict = {}  # holds current docker PTY session

_ANSI_RE = re.compile(r'\x1b(?:\[[\d;]*[a-zA-Z]|\][^\x07]*\x07|[()][AB012]|[=>])')

def _strip_ansi(s: str) -> str:
    s = _ANSI_RE.sub('', s)
    # Remove remaining non-printable control chars except tab
    s = re.sub(r'[\x00-\x08\x0e-\x1f\x7f]', '', s)
    return s.strip()


def broadcast(msg: dict):
    data = "data: " + json.dumps(msg, ensure_ascii=False) + "\n\n"
    dead = []
    for wfile in list(_sse_clients):
        try:
            wfile.write(data.encode())
            wfile.flush()
        except Exception:
            dead.append(wfile)
    for d in dead:
        if d in _sse_clients:
            _sse_clients.remove(d)


def scan_input_dirs(base: str) -> list:
    results = []
    if not os.path.isdir(base):
        return results
    for root, dirs, files in os.walk(base):
        imgs = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp'))]
        if imgs:
            results.append(root)
    results.sort()
    return results


def build_output_dir(input_dir: str, infer_mode: int, erode_pixel: int = 205) -> str:
    mode_suffix = f"{infer_mode}_{erode_pixel}"
    if infer_mode == 99: # Special mode for Night Offline Debug
        return os.path.join(input_dir, "dsg_multi_debug")
    if infer_mode == 5:
        return os.path.join(input_dir, f"cdt_mul_{mode_suffix}_0303_update_432")
    elif infer_mode == 6:
        return os.path.join(input_dir, f"cdt_sub_{mode_suffix}_0319_det_0.2_pc_432")
    elif infer_mode == 7:
        return os.path.join(input_dir, f"dsg_7_205_432")
    else:
        return os.path.join(input_dir, f"output_{mode_suffix}")


def run_offline_test(input_dir: str, infer_mode: int, erode_pixel: int, is_export_run: bool = False, resume: bool = False):
    """
    使用 Docker 容器运行离线感知程序
    """
    global _last_result, _running
    _running = True
    final_pic_dir = build_output_dir(input_dir, infer_mode, erode_pixel)

    broadcast({"type": "start", "input_dir": input_dir, "infer_mode": infer_mode,
               "output_dir": final_pic_dir, "resume": resume})

    # Docker 配置
    DOCKER_IMAGE = "perception-runtime:latest"
    CONTAINER_NAME = "perception_offline_runner"

    # 本地项目根目录
    LOCAL_PROJECT_DIR = PROJECT_ROOT
    local_data_abs = os.path.abspath(os.path.join(LOCAL_PROJECT_DIR, input_dir))

    try:
        broadcast({"type": "log", "text": f"[Docker] 检查镜像 {DOCKER_IMAGE}..."})

        # 检查 Docker 镜像是否存在
        check_img = subprocess.run(
            ["docker", "images", "-q", DOCKER_IMAGE],
            capture_output=True, text=True
        )
        if not check_img.stdout.strip():
            broadcast({"type": "error", "text": f"Docker 镜像 {DOCKER_IMAGE} 不存在，请先构建镜像"})
            _running = False
            return

        broadcast({"type": "log", "text": "[Docker] 准备数据目录..."})

        # 创建临时容器并复制数据进去
        broadcast({"type": "log", "text": f"[Docker] 运行程序: mode={infer_mode}, erode={erode_pixel}"})

        # 构建 Docker 命令
        if infer_mode == 99:
            exe_cmd = f"/app/bin/run_cdt_dsg_fusion_dir"
            env_vars = [
                f"NIGHT_INPUT_DIR=/app/input",
                f"DSG_MODEL_PATH=/app/model/dsg_multi_20260407_640x384.bin",
                f"CDT_MODEL_PATH=/app/models/cdt_20251125_640x384.bin",
            ]
        else:
            exe_cmd = f"/app/bin/offline_perception_debug_432"
            env_vars = [
                f"OFFLINE_INPUT_DIR=/app/input",
                f"OFFLINE_INFER_MODE={infer_mode}",
                f"OFFLINE_ERODE_PIXEL={erode_pixel}",
                f"DSG_MODEL_PATH=/app/models/dsg_multi_20260407_640x384.bin",
                f"CDT_MODEL_PATH=/app/models/cdt_20251125_640x384.bin",
            ]
        if resume:
            env_vars.append("RESUME_OFFLINE=1")

        # 构建 docker run 命令
        docker_cmd = [
            "docker", "run", "--rm",
            "--name", CONTAINER_NAME,
            "-v", f"{local_data_abs}:/app/input",
            "-v", f"{os.path.join(LOCAL_PROJECT_DIR, 'data', 'stereo_debug')}:/app/output",
            "-w", "/app",
            DOCKER_IMAGE,
            "bash", "-c",
            f"mkdir -p /app/input && ln -sf /app/models /models && " + " && ".join(env_vars) + f" {exe_cmd}"
        ]

        broadcast({"type": "log", "text": f"[Docker] 启动命令: {' '.join(docker_cmd[:10])}..."})

        # 运行 Docker 容器
        proc = subprocess.Popen(docker_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        # 实时获取输出
        for line in proc.stdout:
            broadcast({"type": "log", "text": line.rstrip()})

        proc.wait()
        exit_status = proc.returncode

        broadcast({"type": "log", "text": f"[Docker] 程序结束，退出码: {exit_status}"})

        # 获取输出文件列表
        # 图片输出到 dsg_* 目录，点云输出到 pcd_* 目录
        dsg_dir = os.path.join(os.path.dirname(local_data_abs), f"dsg_{infer_mode}_{erode_pixel}_432")
        pcd_dir = os.path.join(os.path.dirname(local_data_abs), f"pcd_{infer_mode}_{erode_pixel}_432")
        output_images = []
        output_pcds = []
        if os.path.isdir(dsg_dir):
            output_images = sorted(
                glob.glob(os.path.join(dsg_dir, "*.jpg")) +
                glob.glob(os.path.join(dsg_dir, "*.png"))
            )
        if os.path.isdir(pcd_dir):
            output_pcds = sorted(glob.glob(os.path.join(pcd_dir, "*.pcd")))

        _last_result = {
            "output_dir": dsg_dir,
            "images": output_images,
            "pcds": output_pcds,
        }

        broadcast({
            "type": "done",
            "exit_code": exit_status,
            "output_dir": dsg_dir,
            "pcd_dir": pcd_dir,
            "image_count": len(output_images),
            "pcd_count": len(output_pcds),
            "images": [os.path.basename(p) for p in output_images],
            "pcds": [os.path.basename(p) for p in output_pcds],
            "is_export_run": is_export_run,
        })

    except FileNotFoundError:
        broadcast({"type": "error", "text": "Docker 未安装或不可用"})
        _running = False
        return
    except Exception as e:
        broadcast({"type": "error", "text": f"执行失败: {str(e)}"})
        _running = False
        return

    _running = False


def run_mono_test(input_dir: str) -> dict:
    """Run dsg_mono_perception on input_dir, return output image paths."""
    output_dir = os.path.join(input_dir, "dsg_mono_432")
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.isfile(MONO_EXE):
        return {"ok": False, "error": f"mono exe not found: {MONO_EXE}"}
    if not os.path.isfile(MONO_MODEL):
        return {"ok": False, "error": f"mono model not found: {MONO_MODEL}"}

    env = os.environ.copy()
    existing_lib = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = f"{OFFLINE_LIB}:{existing_lib}" if existing_lib else OFFLINE_LIB
    env["MONO_INPUT_DIR"] = input_dir
    env["MONO_OUTPUT_DIR"] = output_dir
    env["MONO_MODEL_PATH"] = MONO_MODEL

    try:
        proc = subprocess.run(
            [MONO_EXE, input_dir, output_dir, MONO_MODEL],
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
            cwd=os.path.dirname(MONO_EXE),
        )
        images = sorted(
            glob.glob(os.path.join(output_dir, "*_dsg_mono.jpg")) +
            glob.glob(os.path.join(output_dir, "*_dsg_mono.png"))
        )
        return {
            "ok": True,
            "output_dir": output_dir,
            "images": [os.path.basename(p) for p in images],
            "stdout": proc.stdout[-2000:] if proc.stdout else "",
            "exit_code": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def extract_avoiding_frames(local_dir: str, bag_data_dir: str, window_s: float = 1.0) -> dict:
    """
    从本地日志提取 AVOIDING 时间戳，在 bag_data_dir/images 和 pointclouds 中
    找到时间戳匹配（±window_s 秒）的文件，返回匹配列表。
    文件名格式: match_NNNN_pclYYYYMMDD_HHMMSS_mmm_...
    """
    import re as _re

    # 1. 解析 AVOIDING 时间戳
    if not os.path.isdir(local_dir):
        return {"ok": False, "error": f"目录不存在: {local_dir}"}

    all_files = sorted(glob.glob(os.path.join(local_dir, "*.log")))
    if not all_files:
        all_files = sorted(
            f for f in glob.glob(os.path.join(local_dir, "*"))
            if os.path.isfile(f) and not f.endswith(('.jpg', '.png', '.pcd', '.db3', '.mcap', '.yaml', '.json'))
        )

    avoiding_ts = []
    for fpath in all_files:
        try:
            with open(fpath, "r", errors="replace") as fh:
                for line in fh:
                    if "AVOIDING" not in line:
                        continue
                    ts = parse_ros2_log_timestamp(line)
                    if ts:
                        avoiding_ts.append(ts)
        except Exception:
            continue

    if not avoiding_ts:
        return {"ok": False, "error": "日志中未找到 AVOIDING 时间戳"}

    # 2. 解析 bag 文件名时间戳: pclYYYYMMDD_HHMMSS_mmm
    fname_ts_re = _re.compile(r'pcl(\d{8})_(\d{6})_(\d{3})')

    def parse_fname_ts(fname: str) -> datetime | None:
        m = fname_ts_re.search(fname)
        if not m:
            return None
        try:
            return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except Exception:
            return None

    # 3. 扫描 images 和 pointclouds
    images_dir = os.path.join(bag_data_dir, "images")
    pcds_dir = os.path.join(bag_data_dir, "pointclouds")

    def scan_matches(directory: str, exts: tuple) -> list:
        if not os.path.isdir(directory):
            return []
        matched = []
        for fname in sorted(os.listdir(directory)):
            if not fname.lower().endswith(exts):
                continue
            ft = parse_fname_ts(fname)
            if ft is None:
                continue
            for ats in avoiding_ts:
                if abs((ft - ats).total_seconds()) <= window_s:
                    matched.append(fname)
                    break
        return matched

    matched_images = scan_matches(images_dir, ('.jpg', '.jpeg', '.png'))
    matched_pcds = scan_matches(pcds_dir, ('.pcd',))

    return {
        "ok": True,
        "avoiding_count": len(avoiding_ts),
        "matched_images": matched_images,
        "matched_pcds": matched_pcds,
        "bag_data_dir": bag_data_dir,
    }


def export_suspicious_frames(frame_indices: list, export_dir: str) -> dict:
    """
    从 BAG_DATA_DIR/images/ 中复制疑似障碍物帧的双目拼接图到 export_dir。
    frame_indices: list of {"idx": int, "img_left": str|null, "img_right": str|null}
    返回 {"ok": True, "count": N, "export_dir": ...}
    """
    images_dir = os.path.join(BAG_DATA_DIR, "images")
    os.makedirs(export_dir, exist_ok=True)

    copied = 0
    errors = []
    for f in frame_indices:
        img_left = f.get("img_left")
        img_right = f.get("img_right")
        idx = f.get("idx", 0)

        # 优先使用双目拼接图（如果存在），否则分别复制左右图
        # offline_perception_debug_432 期望 1280x480 的双目拼接图
        if img_left and img_right:
            src_l = os.path.join(images_dir, img_left)
            src_r = os.path.join(images_dir, img_right)
            if os.path.isfile(src_l) and os.path.isfile(src_r):
                # 用 OpenCV 拼接左右图
                try:
                    import cv2
                    import numpy as np
                    l = cv2.imread(src_l)
                    r = cv2.imread(src_r)
                    if l is not None and r is not None:
                        combined = np.hstack([l, r])
                        dst = os.path.join(export_dir, f"frame_{idx:04d}.jpg")
                        cv2.imwrite(dst, combined)
                        copied += 1
                    else:
                        errors.append(f"frame {idx}: imread failed")
                except Exception as e:
                    errors.append(f"frame {idx}: {e}")
            elif os.path.isfile(src_l):
                dst = os.path.join(export_dir, f"frame_{idx:04d}.jpg")
                shutil.copy2(src_l, dst)
                copied += 1
            else:
                errors.append(f"frame {idx}: images not found")
        elif img_left:
            src = os.path.join(images_dir, img_left)
            if os.path.isfile(src):
                dst = os.path.join(export_dir, f"frame_{idx:04d}.jpg")
                shutil.copy2(src, dst)
                copied += 1
            else:
                errors.append(f"frame {idx}: {src} not found")
        else:
            errors.append(f"frame {idx}: no image")

    return {"ok": True, "count": copied, "export_dir": export_dir, "errors": errors}


SSH_KEY = get_ssh_key_path()
SSH_HOST = get_ssh_host()
SSH_USER = get_ssh_user()
ROBOT_LOG_DIR = "/userdata/log_dir/ros2_log"


def parse_bag_timerange(bag_dir: str) -> tuple[datetime | None, datetime | None]:
    """解析 bag 的起止时间，支持 ROS2 metadata.yaml 和 manifest.json"""
    import yaml

    # 1. 优先尝试 ROS2 metadata.yaml
    metadata_path = os.path.join(bag_dir, "metadata.yaml")
    if os.path.isfile(metadata_path):
        try:
            with open(metadata_path) as f:
                meta = yaml.safe_load(f)
            info = meta.get("rosbag2_bagfile_information", {})
            ns_epoch = info.get("starting_time", {}).get("nanoseconds_since_epoch")
            duration_ns = info.get("duration", {}).get("nanoseconds")
            if ns_epoch is not None and duration_ns is not None:
                t_start = datetime.fromtimestamp(ns_epoch / 1e9)
                t_end = t_start + timedelta(seconds=duration_ns / 1e9)
                return t_start, t_end
        except Exception:
            pass

    # 2. 回退到 manifest.json
    manifest_path = os.path.join(bag_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        return None, None
    try:
        with open(manifest_path) as f:
            m = json.load(f)
        recorded_at = m.get("recorded_at", "")
        duration_s = float(m.get("duration_s", 0))
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                t_start = datetime.strptime(recorded_at[:19], fmt[:19])
                break
            except Exception:
                continue
        else:
            return None, None
        t_end = t_start + timedelta(seconds=duration_s)
        return t_start, t_end
    except Exception:
        return None, None


def parse_ros2_log_timestamp(line: str) -> datetime | None:
    """从日志行提取时间戳，支持多种格式：
    [2026/03/19 03:09:12]  [2026-03-19 03:09:12]  2026-03-19 03:09:12"""
    # Format: [YYYY/MM/DD HH:MM:SS] (actual robot log format)
    m = re.search(r'\[(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})\]', line)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y/%m/%d %H:%M:%S")
        except Exception:
            pass
    # Format: [YYYY-MM-DD HH:MM:SS]
    m = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:\.\d+)?\]', line)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    # Format: YYYY-MM-DD HH:MM:SS (no brackets)
    m = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    return None


def _grep_log_files(ssh_base: list, pattern: str, log_files: list) -> list:
    """SSH grep pattern across log_files, return matched lines.
    If pattern is empty, cat all files (return all lines)."""
    if not log_files:
        return []
    if pattern:
        grep_cmds = " ; ".join(
            f"grep -h {pattern!r} {f} 2>/dev/null || true"
            for f in log_files
        )
    else:
        grep_cmds = " ; ".join(
            f"cat {f} 2>/dev/null || true"
            for f in log_files
        )
    try:
        r = subprocess.run(ssh_base + [grep_cmds], capture_output=True, text=True, timeout=30)
        return r.stdout.splitlines()
    except Exception:
        return []


def _filter_by_timerange(lines: list, t_start: datetime, t_end: datetime) -> list:
    """Keep only lines whose timestamp falls within [t_start, t_end], skip no-ts lines."""
    result = []
    for line in lines:
        if not line.strip():
            continue
        ts = parse_ros2_log_timestamp(line)
        if ts is None:
            continue
        if t_start <= ts <= t_end:
            result.append({"ts": ts, "ts_str": ts.strftime("%Y-%m-%d %H:%M:%S"), "text": line.strip()})
    result.sort(key=lambda x: x["ts"])
    return [{"ts": r["ts_str"], "text": r["text"]} for r in result]


def fetch_avoiding_logs_local(local_dir: str, bag_dir: str = "") -> dict:
    """
    从本地已下载的日志目录中解析避障相关日志。
    若提供 bag_dir，则按 bag 时间戳范围过滤日志行。
    支持任意 .log 文件，按文件名前缀分类：
    - robot_decision*: 提取含 AVOIDING 的行
    - stereo* / stere*: 所有行
    - nav*: 所有行
    - 其他: 所有行归入 robot_decision 类别
    """
    if not os.path.isdir(local_dir):
        return {"ok": False, "error": f"目录不存在: {local_dir}"}

    all_files = sorted(glob.glob(os.path.join(local_dir, "*.log")))
    if not all_files:
        # 也尝试不带扩展名的日志文件
        all_files = sorted(
            f for f in glob.glob(os.path.join(local_dir, "*"))
            if os.path.isfile(f) and not f.endswith(('.jpg', '.png', '.pcd', '.db3', '.mcap', '.yaml', '.json'))
        )
    if not all_files:
        return {"ok": False, "error": "未找到日志文件"}

    decision_files = [f for f in all_files if os.path.basename(f).startswith("robot_decision")]
    stereo_files   = [f for f in all_files if os.path.basename(f).startswith(("stere", "stereo"))]
    nav_files      = [f for f in all_files if os.path.basename(f).startswith("nav")]
    other_files    = [f for f in all_files if f not in decision_files + stereo_files + nav_files]
    # 未分类文件归入 decision
    decision_files += other_files

    def read_local(fpath: str) -> list:
        try:
            with open(fpath, "r", errors="replace") as fh:
                return fh.read().splitlines()
        except Exception:
            return []

    def grep_local(files: list, pattern: str) -> list:
        result = []
        for f in files:
            for line in read_local(f):
                if not pattern or pattern in line:
                    result.append(line)
        return result

    decision_raw = grep_local(decision_files, "AVOIDING")
    stereo_raw   = grep_local(stereo_files, "")
    nav_raw      = grep_local(nav_files, "")

    # 尝试从 bag_dir 获取时间范围用于过滤
    bag_t_start, bag_t_end = None, None
    if bag_dir:
        bag_t_start, bag_t_end = parse_bag_timerange(bag_dir)

    # 收集所有有效时间戳以确定整体范围（用于元信息显示）
    all_raw = decision_raw + stereo_raw + nav_raw
    ts_list = [parse_ros2_log_timestamp(l) for l in all_raw]
    ts_list = [t for t in ts_list if t is not None]
    if not ts_list:
        return {"ok": False, "error": "日志中未找到有效时间戳"}

    disp_start = bag_t_start if bag_t_start else min(ts_list)
    disp_end   = bag_t_end   if bag_t_end   else max(ts_list)

    def fmt_lines(raw: list) -> list:
        result = []
        for line in raw:
            if not line.strip():
                continue
            ts = parse_ros2_log_timestamp(line)
            # 若有 bag 时间范围，仅保留范围内的行
            if bag_t_start and bag_t_end and ts:
                if not (bag_t_start <= ts <= bag_t_end):
                    continue
            ts_str = ts.strftime("%H:%M:%S") if ts else "??:??:??"
            result.append({"ts": ts_str, "text": line.strip(), "_ts": ts or datetime.min})
        result.sort(key=lambda x: x["_ts"])
        return [{"ts": r["ts"], "text": r["text"]} for r in result]

    return {
        "ok": True,
        "bag_start": disp_start.strftime("%Y-%m-%d %H:%M:%S"),
        "bag_end":   disp_end.strftime("%Y-%m-%d %H:%M:%S"),
        "categories": {
            "robot_decision": {"files": [os.path.basename(f) for f in decision_files], "lines": fmt_lines(decision_raw)},
            "stereo":         {"files": [os.path.basename(f) for f in stereo_files],   "lines": fmt_lines(stereo_raw)},
            "nav":            {"files": [os.path.basename(f) for f in nav_files],       "lines": fmt_lines(nav_raw)},
        },
    }


def fetch_avoiding_logs(bag_dir: str, port: int) -> dict:
    """
    SSH 到机器，在 /userdata/log_dir/ros2_log 中找与 bag 时间戳重叠的日志。
    - robot_decision*: 提取含 AVOIDING 的行
    - stereo*: 提取时间戳在范围内的所有行
    - nav*: 提取时间戳在范围内的所有行
    返回按来源分类的结果。
    """
    t_start, t_end = parse_bag_timerange(bag_dir)
    if t_start is None:
        return {"ok": False, "error": "无法解析 bag 时间戳，请确认目录包含 metadata.yaml 或 manifest.json"}

    ssh_base = [
        "ssh", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        f"{SSH_USER}@{SSH_HOST}", "-p", str(port)
    ]

    # List all relevant log files in one SSH call
    ls_cmd = (
        f"ls {ROBOT_LOG_DIR}/robot_decision* 2>/dev/null; "
        f"ls {ROBOT_LOG_DIR}/stere* 2>/dev/null; "
        f"ls {ROBOT_LOG_DIR}/nav* 2>/dev/null"
    )
    try:
        r = subprocess.run(ssh_base + [ls_cmd], capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "SSH 连接超时"}
    except Exception as e:
        return {"ok": False, "error": f"SSH 错误: {e}"}

    if r.returncode != 0 and not r.stdout.strip():
        return {"ok": False, "error": f"SSH 失败: {r.stderr.strip()}"}

    all_files = [f.strip() for f in r.stdout.strip().splitlines() if f.strip()]
    decision_files = [f for f in all_files if os.path.basename(f).startswith("robot_decision")]
    stereo_files   = [f for f in all_files if os.path.basename(f).startswith("stere")]
    nav_files      = [f for f in all_files if os.path.basename(f).startswith("nav")]

    # robot_decision: only AVOIDING lines
    decision_raw = _grep_log_files(ssh_base, "AVOIDING", decision_files)
    decision_lines = _filter_by_timerange(decision_raw, t_start, t_end)

    # stereo / nav: all lines in time range
    stereo_raw = _grep_log_files(ssh_base, "", stereo_files) if stereo_files else []
    stereo_lines = _filter_by_timerange(stereo_raw, t_start, t_end)

    nav_raw = _grep_log_files(ssh_base, "", nav_files) if nav_files else []
    nav_lines = _filter_by_timerange(nav_raw, t_start, t_end)

    return {
        "ok": True,
        "bag_start": t_start.strftime("%Y-%m-%d %H:%M:%S"),
        "bag_end": t_end.strftime("%Y-%m-%d %H:%M:%S"),
        "categories": {
            "robot_decision": {"files": decision_files, "lines": decision_lines},
            "stereo":         {"files": stereo_files,   "lines": stereo_lines},
            "nav":            {"files": nav_files,       "lines": nav_lines},
        },
    }


def download_logs_to_local(bag_dir: str, port: int) -> dict:
    """
    SSH 到机器，找出与 bag 时间戳交叉的 robot_decision / stereo_perception_multi /
    nav2_single_node_navigator 日志文件，整体 scp 下载到 bag_dir/log2/。
    """
    t_start, t_end = parse_bag_timerange(bag_dir)
    if t_start is None:
        return {"ok": False, "error": "无法解析 bag 时间戳"}

    save_dir = os.path.join(bag_dir, "log2")
    os.makedirs(save_dir, exist_ok=True)

    ssh_base = [
        "ssh", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        f"{SSH_USER}@{SSH_HOST}", "-p", str(port)
    ]
    scp_base = [
        "scp", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-P", str(port)
    ]

    # 列出所有候选文件
    ls_cmd = (
        f"ls {ROBOT_LOG_DIR}/robot_decision* 2>/dev/null; "
        f"ls {ROBOT_LOG_DIR}/stereo_perception_multi* 2>/dev/null; "
        f"ls {ROBOT_LOG_DIR}/nav2_single_node_navigator* 2>/dev/null"
    )
    try:
        r = subprocess.run(ssh_base + [ls_cmd], capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "SSH 连接超时"}
    except Exception as e:
        return {"ok": False, "error": f"SSH 错误: {e}"}

    all_files = [f.strip() for f in r.stdout.strip().splitlines() if f.strip()]
    if not all_files:
        return {"ok": False, "error": "未找到匹配日志文件"}

    # 检查每个文件是否与 bag 时间戳有交叉（取文件前100行和后100行各采样一次时间戳）
    matched = []
    for fpath in all_files:
        sample_cmd = f"(head -100 {fpath}; tail -100 {fpath}) 2>/dev/null"
        try:
            rs = subprocess.run(ssh_base + [sample_cmd], capture_output=True, text=True, timeout=10)
            lines = rs.stdout.splitlines()
        except Exception:
            continue
        ts_list = [parse_ros2_log_timestamp(l) for l in lines]
        ts_list = [t for t in ts_list if t is not None]
        if not ts_list:
            continue
        file_start, file_end = min(ts_list), max(ts_list)
        # 时间戳有交叉
        if file_start <= t_end and file_end >= t_start:
            matched.append(fpath)

    if not matched:
        return {"ok": False, "error": "未找到与 bag 时间戳交叉的日志文件"}

    # scp 下载
    downloaded = []
    errors = []
    for fpath in matched:
        dst = os.path.join(save_dir, os.path.basename(fpath))
        try:
            rc = subprocess.run(
                scp_base + [f"{SSH_USER}@{SSH_HOST}:{fpath}", dst],
                capture_output=True, text=True, timeout=60
            )
            if rc.returncode == 0:
                downloaded.append(os.path.basename(fpath))
            else:
                errors.append(f"{os.path.basename(fpath)}: {rc.stderr.strip()}")
        except Exception as e:
            errors.append(f"{os.path.basename(fpath)}: {e}")

    return {
        "ok": True,
        "save_dir": save_dir,
        "downloaded": downloaded,
        "errors": errors,
    }


def _decode_compressed_image(data: bytes):
    """Extract JPEG from ROS2 compressed image CDR message."""
    off = 4  # CDR header
    off += 8  # stamp
    if off + 4 > len(data):
        return None
    slen = struct.unpack_from('<I', data, off)[0]
    off += 4 + slen
    off = (off + 3) & ~3
    if off + 4 > len(data):
        return None
    flen = struct.unpack_from('<I', data, off)[0]
    off += 4 + flen
    off = (off + 3) & ~3
    if off + 4 > len(data):
        return None
    dlen = struct.unpack_from('<I', data, off)[0]
    off += 4
    if off + dlen > len(data):
        return None
    return data[off:off + dlen]


def _decode_pointcloud2(data: bytes):
    """Parse ROS2 PointCloud2 CDR using the same logic as time_left_pcl.py.
    Returns list of dicts with x, y, z, rgb, label keys.
    """
    try:
        off = 0
        off += 4  # CDR header flags
        # timestamp
        off += 4  # stamp_sec
        off += 4  # stamp_nanosec
        # frame_id
        frame_id_len = struct.unpack_from('<I', data, off)[0]; off += 4
        off += frame_id_len
        # align to 4 bytes
        while off % 4 != 0:
            off += 1
        height = struct.unpack_from('<I', data, off)[0]; off += 4
        width  = struct.unpack_from('<I', data, off)[0]; off += 4
        nfields = struct.unpack_from('<I', data, off)[0]; off += 4
        fields = []
        for _ in range(nfields):
            name_len = struct.unpack_from('<I', data, off)[0]; off += 4
            fname = data[off:off + name_len].decode('utf-8', errors='ignore').rstrip('\x00')
            off += name_len
            while off % 4 != 0:
                off += 1
            foff  = struct.unpack_from('<I', data, off)[0]; off += 4
            dtype = struct.unpack_from('<B', data, off)[0]; off += 1
            off += 3  # pad to 4-byte align
            count = struct.unpack_from('<I', data, off)[0]; off += 4
            fields.append({'name': fname, 'offset': foff, 'datatype': dtype, 'count': count})
        off += 1  # is_bigendian
        off += 3  # pad
        point_step = struct.unpack_from('<I', data, off)[0]; off += 4
        off += 4  # row_step
        dlen = struct.unpack_from('<I', data, off)[0]; off += 4
        raw = data[off:off + dlen]
        n = min(height * width, len(raw) // point_step if point_step else 0)
        pts = []
        for i in range(n):
            base = i * point_step
            if base + point_step > len(raw):
                break
            pb = raw[base:base + point_step]
            pt = {}
            for f in fields:
                fn, fo, fdt = f['name'], f['offset'], f['datatype']
                if fo + 4 > len(pb):
                    continue
                try:
                    if fn in ('x', 'y', 'z') and fdt == 7:  # FLOAT32
                        pt[fn] = struct.unpack_from('<f', pb, fo)[0]
                    elif fn == 'rgb' and fdt == 6:  # UINT32
                        rgb_packed = struct.unpack_from('<I', pb, fo)[0]
                        pt['r'] = (rgb_packed >> 16) & 0xFF
                        pt['g'] = (rgb_packed >> 8) & 0xFF
                        pt['b'] = rgb_packed & 0xFF
                        pt['rgb'] = rgb_packed
                    elif fn == 'label' and fdt == 6:  # UINT32
                        pt['label'] = struct.unpack_from('<I', pb, fo)[0]
                except struct.error:
                    continue
            if 'x' in pt and 'y' in pt and 'z' in pt:
                x, y, z = pt['x'], pt['y'], pt['z']
                label = pt.get('label', 0)

                # Skip NaN or Inf values
                if not (x == x and y == y and z == z):
                    continue
                if x == float('inf') or x == float('-inf'):
                    continue
                if y == float('inf') or y == float('-inf'):
                    continue
                if z == float('inf') or z == float('-inf'):
                    continue

                # Only filter label=1 (background) and label=5 (obstacle triggers)
                # Keep label=3 (road) and other labels as-is
                if label == 1 or label == 5:
                    # Depth validity check: skip invalid or out-of-range points
                    if z <= 0 or z < MIN_DISTANCE or z > MAX_DISTANCE:
                        continue

                    # Height filtering: filter ground-level noise
                    if y < MIN_OBSTACLE_HEIGHT or y > MAX_HEIGHT:
                        continue

                pts.append(pt)
        return pts
    except Exception:
        return []


def _filter_pcd_file(pcd_path: str) -> bool:
    """
    Filter a PCD file in-place, removing label=1 (background) points that don't meet criteria.
    Keep label=5 (real obstacles) and label=3 (road) as-is.
    Returns True if successful, False otherwise.
    """
    try:
        with open(pcd_path, 'r') as f:
            lines = f.readlines()

        # Find data start
        data_start = 0
        for i, line in enumerate(lines):
            if line.strip().startswith('DATA'):
                data_start = i + 1
                break

        if data_start == 0:
            return False

        # Parse header
        header_lines = lines[:data_start]
        data_lines = lines[data_start:]

        # Filter data points
        filtered_data = []
        for line in data_lines:
            parts = line.strip().split()
            if len(parts) >= 5:
                try:
                    x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                    label = int(float(parts[4]))

                    # Skip NaN or Inf
                    if not (x == x and y == y and z == z):
                        continue
                    if x == float('inf') or x == float('-inf'):
                        continue
                    if y == float('inf') or y == float('-inf'):
                        continue
                    if z == float('inf') or z == float('-inf'):
                        continue

                    # Only filter label=1 (background noise)
                    # Keep label=5 (real obstacles) and label=3 (road) as-is
                    if label == 1:
                        if z <= 0 or z < MIN_DISTANCE or z > MAX_DISTANCE:
                            continue
                        if y < MIN_OBSTACLE_HEIGHT or y > MAX_HEIGHT:
                            continue

                    filtered_data.append(line)
                except (ValueError, IndexError):
                    continue

        # Update header with new point count
        new_count = len(filtered_data)
        new_header = []
        for line in header_lines:
            if line.strip().startswith('WIDTH'):
                new_header.append(f'WIDTH {new_count}\n')
            elif line.strip().startswith('POINTS'):
                new_header.append(f'POINTS {new_count}\n')
            else:
                new_header.append(line)

        # Write filtered PCD
        with open(pcd_path, 'w') as f:
            f.writelines(new_header + filtered_data)

        return True
    except Exception as e:
        print(f"[Error] Failed to filter {pcd_path}: {e}")
        return False


def _write_pcd(pts, path):
    """Write PCD with FIELDS x y z rgb label (5 fields, matching time_left_pcl.py format)."""
    lines = ['# .PCD v0.7 - Point Cloud Data file format',
             'VERSION 0.7', 'FIELDS x y z rgb label',
             'SIZE 4 4 4 4 4', 'TYPE F F F U U',
             'COUNT 1 1 1 1 1', f'WIDTH {len(pts)}',
             'HEIGHT 1', 'VIEWPOINT 0 0 0 1 0 0 0',
             f'POINTS {len(pts)}', 'DATA ascii']
    for pt in pts:
        x = pt.get('x', 0.0)
        y = pt.get('y', 0.0)
        z = pt.get('z', 0.0)
        rgb = pt.get('rgb', 0)
        label = pt.get('label', 0)
        lines.append(f'{x:.6f} {y:.6f} {z:.6f} {rgb} {label}')
    Path(path).write_text('\n'.join(lines))


def find_db3_file(path_str: str) -> Path | None:
    """Find .db3 file in path. If path is a directory, find the first .db3 file."""
    p = Path(path_str)
    if not p.exists():
        return None
    if p.is_file() and p.suffix == '.db3':
        return p
    if p.is_dir():
        db3_files = list(p.glob('*.db3'))
        if db3_files:
            return db3_files[0]
    return None


def extract_nav_bag(nav_bag_path: str, log_cb, bag_type: str = 'nav') -> bool:
    """Extract images and pointclouds from nav bag at move_abnormal timestamps.

    Args:
        nav_bag_path: Path to the bag file
        log_cb: Callback function for logging
        bag_type: 'nav' or 'camera' to determine output directory structure
    """
    db3_file = find_db3_file(nav_bag_path)
    if not db3_file:
        log_cb(f'ERROR: 找不到 .db3 文件: {nav_bag_path}')
        return False

    log_cb(f'使用 bag 文件: {db3_file}')
    p = db3_file
    # 根据包类型选择输出目录
    extract_dir = 'bag_extract_camera' if bag_type == 'camera' else 'bag_extract_nav'
    img_subdir = 'bag_extract_stereo' if bag_type == 'camera' else 'bag_extract_left'
    out_base = p.parent / extract_dir
    img_dir = out_base / img_subdir
    pcd_dir = out_base / 'bag_extract_pcd'
    img_dir.mkdir(parents=True, exist_ok=True)
    pcd_dir.mkdir(parents=True, exist_ok=True)
    log_cb(f'输出目录: {out_base}')

    conn = sqlite3.connect(str(p))
    cur = conn.cursor()
    topics = {}
    for row in cur.execute('SELECT id, name FROM topics'):
        topics[row[1]] = row[0]
    log_cb(f'话题列表: {list(topics.keys())}')

    abnormal_topic = '/decision_assistant/move_abnormal'
    img_topic = '/camera_sensors/rotation/sc132gs/left/image_rect/compressed'
    pcl_topic = '/perception_node/stereo/pcl_output'

    if abnormal_topic not in topics:
        log_cb(f'ERROR: 找不到话题 {abnormal_topic}')
        conn.close()
        return False

    abn_id = topics[abnormal_topic]
    abnormal_ts = [row[0] for row in cur.execute(
        'SELECT timestamp FROM messages WHERE topic_id=? ORDER BY timestamp', (abn_id,))]
    log_cb(f'发现 {len(abnormal_ts)} 个避障事件')

    img_id = topics.get(img_topic)
    pcl_id = topics.get(pcl_topic)
    window_ns = 2_000_000_000

    extracted_imgs = 0
    extracted_pcds = 0

    for i, ts in enumerate(abnormal_ts):
        ts_ms = ts // 1_000_000
        ts_str = f'{(ts_ms // 1000 % 86400) // 3600 + 8:02d}{ts_ms // 60000 % 60:02d}{ts_ms // 1000 % 60:02d}_{ts_ms % 1000:03d}'

        if img_id:
            rows = cur.execute(
                'SELECT timestamp, data FROM messages WHERE topic_id=? AND timestamp BETWEEN ? AND ? ORDER BY ABS(timestamp-?) LIMIT 1',
                (img_id, ts - window_ns, ts + window_ns, ts)).fetchall()
            for row in rows:
                img_data = _decode_compressed_image(bytes(row[1]))
                if img_data and img_data[:2] == b'\xff\xd8':
                    fname = img_dir / f'abnormal_{i+1:03d}_ts{ts}_{ts_str}.jpg'
                    fname.write_bytes(img_data)
                    extracted_imgs += 1
                    log_cb(f'  [img] {fname.name}')

        if pcl_id:
            rows = cur.execute(
                'SELECT timestamp, data FROM messages WHERE topic_id=? AND timestamp BETWEEN ? AND ? ORDER BY ABS(timestamp-?) LIMIT 1',
                (pcl_id, ts - window_ns, ts + window_ns, ts)).fetchall()
            for row in rows:
                pts = _decode_pointcloud2(bytes(row[1]))
                if pts:
                    fname = pcd_dir / f'abnormal_{i+1:03d}_ts{ts}_{ts_str}.pcd'
                    _write_pcd(pts, fname)
                    extracted_pcds += 1
                    log_cb(f'  [pcd] {fname.name} ({len(pts)}pts)')

    conn.close()
    log_cb(f'完成! 提取图片: {extracted_imgs}张, 点云: {extracted_pcds}个')
    log_cb(f'保存路径: {out_base}')
    return True


def extract_left_pcl_bag(nav_bag_path: str, log_cb, bag_type: str = 'nav') -> bool:
    """Extract all left images and pointclouds from a bag that has only mono+pcl (no move_abnormal).
    Matches left images to nearest pointcloud within 10ms, saves to bag_extract_nav/ or bag_extract_camera/.

    Args:
        nav_bag_path: Path to the bag file
        log_cb: Callback function for logging
        bag_type: 'nav' or 'camera' to determine output directory structure
    """
    db3_file = find_db3_file(nav_bag_path)
    if not db3_file:
        log_cb(f'ERROR: 找不到 .db3 文件: {nav_bag_path}')
        return False

    log_cb(f'使用 bag 文件: {db3_file}')
    p = db3_file
    # 根据包类型选择输出目录
    extract_dir = 'bag_extract_camera' if bag_type == 'camera' else 'bag_extract_nav'
    img_subdir = 'bag_extract_stereo' if bag_type == 'camera' else 'bag_extract_left'
    out_base = p.parent / extract_dir
    img_dir = out_base / img_subdir
    pcd_dir = out_base / 'bag_extract_pcd'
    img_dir.mkdir(parents=True, exist_ok=True)
    pcd_dir.mkdir(parents=True, exist_ok=True)
    log_cb(f'输出目录: {out_base}')

    conn = sqlite3.connect(str(p))
    cur = conn.cursor()
    topics = {}
    for row in cur.execute('SELECT id, name FROM topics'):
        topics[row[1]] = row[0]
    log_cb(f'话题列表: {list(topics.keys())}')

    left_img_topic = '/camera_sensors/rotation/sc132gs/left/image_rect/compressed'
    right_img_topic = '/camera_sensors/rotation/sc132gs/right/image_rect/compressed'
    pcl_topic = '/perception_node/stereo/pcl_output'

    left_img_id = topics.get(left_img_topic)
    right_img_id = topics.get(right_img_topic)
    pcl_id = topics.get(pcl_topic)

    if not left_img_id:
        log_cb(f'ERROR: 找不到左目话题 {left_img_topic}')
        conn.close()
        return False
    if not pcl_id:
        log_cb(f'ERROR: 找不到点云话题 {pcl_topic}')
        conn.close()
        return False

    # Load all pcl timestamps
    pcl_rows = cur.execute(
        'SELECT timestamp, data FROM messages WHERE topic_id=? ORDER BY timestamp', (pcl_id,)
    ).fetchall()
    log_cb(f'发现 {len(pcl_rows)} 帧点云')

    # Load all left image timestamps
    left_img_rows = cur.execute(
        'SELECT timestamp, data FROM messages WHERE topic_id=? ORDER BY timestamp', (left_img_id,)
    ).fetchall()
    log_cb(f'发现 {len(left_img_rows)} 帧左目图像')

    # Load right images if this is a camera bag (for stereo concatenation)
    right_img_rows = []
    if bag_type == 'camera' and right_img_id:
        right_img_rows = cur.execute(
            'SELECT timestamp, data FROM messages WHERE topic_id=? ORDER BY timestamp', (right_img_id,)
        ).fetchall()
        log_cb(f'发现 {len(right_img_rows)} 帧右目图像')

    if not pcl_rows or not left_img_rows:
        log_cb('ERROR: 图像或点云数据为空')
        conn.close()
        return False

    # Build list of pcl timestamps for binary search matching
    pcl_ts_list = [r[0] for r in pcl_rows]
    import bisect
    time_tolerance_ns = 10_000_000  # 10ms

    # Build right image timestamp list for stereo matching (camera bag only)
    right_img_ts_list = []
    right_img_data_list = []
    if bag_type == 'camera' and right_img_rows:
        for ts, data in right_img_rows:
            right_img_ts_list.append(ts)
            right_img_data_list.append(data)

    extracted_imgs = 0
    extracted_pcds = 0
    matched = 0

    for idx, (left_img_ts, left_img_data) in enumerate(left_img_rows):
        # Find nearest pcl timestamp
        pos = bisect.bisect_left(pcl_ts_list, left_img_ts)
        candidates = []
        if pos < len(pcl_ts_list):
            candidates.append(pos)
        if pos > 0:
            candidates.append(pos - 1)
        if not candidates:
            continue
        best_pos = min(candidates, key=lambda i: abs(pcl_ts_list[i] - left_img_ts))
        diff = abs(pcl_ts_list[best_pos] - left_img_ts)
        if diff > time_tolerance_ns:
            continue

        pcl_ts, pcl_data = pcl_rows[best_pos]
        ts_ms = left_img_ts // 1_000_000
        ts_str = f'{(ts_ms // 1000 % 86400) // 3600 + 8:02d}{ts_ms // 60000 % 60:02d}{ts_ms // 1000 % 60:02d}_{ts_ms % 1000:03d}'

        # Decode left image
        left_img_bytes = _decode_compressed_image(bytes(left_img_data))

        # For camera bag, concatenate left and right images
        if bag_type == 'camera' and right_img_ts_list and PIL_AVAILABLE:
            # Find matching right image using binary search with time tolerance
            pos = bisect.bisect_left(right_img_ts_list, left_img_ts)
            candidates = []
            if pos < len(right_img_ts_list):
                candidates.append(pos)
            if pos > 0:
                candidates.append(pos - 1)

            right_img_data = None
            if candidates:
                best_pos = min(candidates, key=lambda i: abs(right_img_ts_list[i] - left_img_ts))
                diff = abs(right_img_ts_list[best_pos] - left_img_ts)
                if diff <= time_tolerance_ns:
                    right_img_data = right_img_data_list[best_pos]

            if right_img_data:
                right_img_bytes = _decode_compressed_image(bytes(right_img_data))
                if left_img_bytes and right_img_bytes:
                    # Concatenate left and right images horizontally
                    try:
                        left_img = Image.open(io.BytesIO(left_img_bytes))
                        right_img = Image.open(io.BytesIO(right_img_bytes))

                        # Create concatenated image (left | right)
                        total_width = left_img.width + right_img.width
                        max_height = max(left_img.height, right_img.height)
                        stereo_img = Image.new('RGB', (total_width, max_height))
                        stereo_img.paste(left_img, (0, 0))
                        stereo_img.paste(right_img, (left_img.width, 0))

                        # Save concatenated image
                        fname = img_dir / f'match_{matched:04d}_ts{left_img_ts}_{ts_str}.jpg'
                        stereo_img.save(fname, 'JPEG', quality=95)
                        extracted_imgs += 1
                        log_cb(f'  [img] {fname.name}')
                    except Exception as e:
                        log_cb(f'  ERROR: 拼接图片失败 {e}')
                else:
                    log_cb(f'  WARN: 左右目图片解码失败，跳过')
            else:
                log_cb(f'  WARN: 未找到匹配的右目图片 (时间差>{time_tolerance_ns/1e6:.1f}ms)，跳过')
        else:
            # For nav bag or when PIL not available, save left image only
            if left_img_bytes and left_img_bytes[:2] == b'\xff\xd8':
                fname = img_dir / f'match_{matched:04d}_ts{left_img_ts}_{ts_str}.jpg'
                fname.write_bytes(left_img_bytes)
                extracted_imgs += 1
                log_cb(f'  [img] {fname.name}')

        pts = _decode_pointcloud2(bytes(pcl_data))
        if pts:
            fname = pcd_dir / f'match_{matched:04d}_ts{left_img_ts}_{ts_str}.pcd'
            _write_pcd(pts, fname)
            extracted_pcds += 1
            log_cb(f'  [pcd] {fname.name} ({len(pts)}pts)')

        matched += 1

    conn.close()
    log_cb(f'完成! 提取图片: {extracted_imgs}张, 点云: {extracted_pcds}个')
    log_cb(f'保存路径: {out_base}')
    return True


# ─── 图片下载基础路径：使用项目内 data/stereo_debug ───────────────
LOCAL_IMAGE_BASE = os.path.join(PROJECT_ROOT, "data/stereo_debug")
ROBOT_IMAGE_BASE = "/userdata/bestmow_data/image_perception_debug"


def upload_images_from_robot(port: int, date_str: str) -> dict:
    """
    从机器端 /userdata/bestmow_data/image_save_path/<date_str> 下载图片到
    data/uploads/<last4digits_of_port>/<date_str>/，使用 scp -r。
    date_str 格式: YYYY-MM-DD
    """
    if not date_str:
        return {"ok": False, "error": "未提供日期"}

    port_suffix = str(port)[-4:]
    local_dir = os.path.join(LOCAL_IMAGE_BASE, port_suffix, date_str)

    remote_dir = f"{ROBOT_IMAGE_BASE}/{date_str}"
    os.makedirs(local_dir, exist_ok=True)

    scp_cmd = [
        "scp", "-r",
        "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=15",
        "-P", str(port),
        f"{SSH_USER}@{SSH_HOST}:{remote_dir}/.",
        local_dir + "/",
    ]

    try:
        r = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            # 统计下载的文件数
            count = sum(
                len(files)
                for _, _, files in os.walk(local_dir)
            )
            return {"ok": True, "local_dir": local_dir, "file_count": count}
        else:
            return {"ok": False, "error": r.stderr.strip() or "scp 失败"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "scp 超时"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def upload_images_range_from_robot(port: int, date_start: str, date_end: str) -> dict:
    """
    从机器端 /userdata/bestmow_data/image_save_path 下载名称在 [date_start, date_end]
    范围内（YYYYMMDD 字符串比较）的文件夹到
    data/uploads/<last4digits_port>/<folder_name>/
    """
    if not date_start or not date_end:
        return {"ok": False, "error": "未提供起止日期"}
    if date_start > date_end:
        return {"ok": False, "error": "开始日期不能晚于截止日期"}

    port_suffix = str(port)[-4:]
    local_base = os.path.join(LOCAL_IMAGE_BASE, port_suffix)

    REMOTE_BASE = "/userdata/bestmow_data/image_save_path"
    # SSH options for rsync - use proper quoting
    ssh_opts = f"ssh -i {SSH_KEY} -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -p {port}"
    ssh_base = [
        "ssh", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=15",
        "-o", "ServerAliveInterval=10",
        "-o", "ServerAliveCountMax=3",
        "-p", str(port),
        f"{SSH_USER}@{SSH_HOST}",
    ]

    # List folders under REMOTE_BASE
    ls_cmd = f"ls -1 {REMOTE_BASE}/ 2>/dev/null"
    try:
        r = subprocess.run(ssh_base + [ls_cmd], capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "SSH 连接超时"}
    except Exception as e:
        return {"ok": False, "error": f"SSH 错误: {e}"}

    if r.returncode != 0 and not r.stdout.strip():
        return {"ok": False, "error": f"SSH 失败: {r.stderr.strip()}"}

    all_entries = [e.strip() for e in r.stdout.strip().splitlines() if e.strip()]

    # Extract date from folder names (handle formats like YYYYMMDD or YYYY-MM-DD)
    # and filter by date range
    matched_folders = []
    for entry in all_entries:
        # Try to extract YYYYMMDD pattern from folder name
        date_match = re.search(r'(\d{8})', entry)
        if date_match:
            folder_date = date_match.group(1)
            if date_start <= folder_date <= date_end:
                matched_folders.append(entry)
        # Also try direct string comparison for exact YYYYMMDD format
        elif date_start <= entry <= date_end:
            matched_folders.append(entry)

    if not matched_folders:
        return {
            "ok": False,
            "error": f"未找到 {date_start}~{date_end} 范围内的文件夹",
            "debug_info": f"远端共有 {len(all_entries)} 个文件夹: {', '.join(all_entries[:10])}"
        }

    os.makedirs(local_base, exist_ok=True)

    total_files = 0
    errors = []
    successful_folders = 0

    print(f"[upload_images_range] 开始下载 {len(matched_folders)} 个文件夹: {matched_folders}")

    for folder in matched_folders:
        remote_dir = f"{REMOTE_BASE}/{folder}"
        local_dir = os.path.join(local_base, folder)
        os.makedirs(local_dir, exist_ok=True)

        print(f"[upload_images_range] 正在下载: {remote_dir} -> {local_dir}")

        # Retry up to 3 times for transient SSH errors
        max_retries = 3
        retry_count = 0
        success = False

        while retry_count < max_retries and not success:
            try:
                if retry_count > 0:
                    print(f"[upload_images_range] 重试 {retry_count}/{max_retries}: {folder}")
                    time.sleep(2)  # Wait before retry

                rc = subprocess.run(
                    [
                        "rsync", "-avz", "--partial", "--timeout=60",
                        "-e", ssh_opts,
                        f"{SSH_USER}@{SSH_HOST}:{remote_dir}/",
                        local_dir + "/",
                    ],
                    capture_output=True, text=True, timeout=600
                )

                print(f"[upload_images_range] rsync returncode: {rc.returncode}")
                if rc.stdout:
                    print(f"[upload_images_range] rsync stdout: {rc.stdout[:500]}")
                if rc.stderr:
                    print(f"[upload_images_range] rsync stderr: {rc.stderr[:500]}")

                if rc.returncode == 0:
                    count = sum(len(files) for _, _, files in os.walk(local_dir))
                    total_files += count
                    successful_folders += 1
                    success = True
                    print(f"[upload_images_range] 成功下载 {folder}, 文件数: {count}")
                else:
                    error_msg = rc.stderr.strip() or rc.stdout.strip() or 'rsync 失败'
                    # Check if it's a transient SSH error
                    if "EOF during negotiation" in error_msg or "Connection reset" in error_msg or "Connection timed out" in error_msg:
                        retry_count += 1
                        if retry_count >= max_retries:
                            errors.append(f"{folder}: {error_msg} (重试 {max_retries} 次后失败)")
                            print(f"[upload_images_range] 下载失败 {folder}: {error_msg}")
                    else:
                        # Non-transient error, don't retry
                        errors.append(f"{folder}: {error_msg}")
                        print(f"[upload_images_range] 下载失败 {folder}: {error_msg}")
                        break
            except subprocess.TimeoutExpired:
                retry_count += 1
                if retry_count >= max_retries:
                    errors.append(f"{folder}: rsync 超时 (重试 {max_retries} 次后失败)")
                    print(f"[upload_images_range] 下载超时 {folder}")
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    errors.append(f"{folder}: {e}")
                    print(f"[upload_images_range] 下载异常 {folder}: {e}")

    print(f"[upload_images_range] 完成! 成功: {successful_folders}/{len(matched_folders)}, 总文件数: {total_files}")

    return {
        "ok": True,
        "local_base": local_base,
        "folder_count": successful_folders,
        "file_count": total_files,
        "matched_folders": matched_folders,
        "errors": errors,
    }


# ─── 日志拉取基础路径：使用项目内 data/uploads ───────────────
LOCAL_LOG_PULL_BASE = os.path.join(PROJECT_ROOT, "data/uploads")


def check_local_logs(local_dir: str) -> dict:
    """
    检查本地日志目录是否存在以及文件数量
    返回: {"exists": bool, "file_count": int, "files": list}
    """
    print(f"[check_local_logs] 检查目录: {local_dir}")

    if not local_dir:
        print("[check_local_logs] 目录为空")
        return {"exists": False, "file_count": 0, "files": []}

    # 转换为绝对路径
    if not os.path.isabs(local_dir):
        local_dir = os.path.join(PROJECT_ROOT, local_dir)

    print(f"[check_local_logs] 绝对路径: {local_dir}")

    if not os.path.exists(local_dir):
        print(f"[check_local_logs] 目录不存在")
        return {"exists": False, "file_count": 0, "files": []}

    try:
        files = []
        for root, dirs, filenames in os.walk(local_dir):
            for fname in filenames:
                files.append(os.path.join(root, fname))

        print(f"[check_local_logs] 找到 {len(files)} 个文件")
        return {
            "exists": True,
            "file_count": len(files),
            "files": files[:100]  # 只返回前100个文件名作为示例
        }
    except Exception as e:
        print(f"[check_local_logs] 异常: {e}")
        return {"exists": False, "file_count": 0, "error": str(e)}


def pull_robot_logs(port: int, local_save_dir: str = None, progress_callback=None) -> dict:
    """
    SSH 至机器，将 /userdata/log_dir 下的全部日志 rsync 到本地。
    本地路径: data/log_debug/<last4digits_port>/<YYYYMMDD>/
    如果指定了 local_save_dir，则使用该目录（如果不存在则创建）
    progress_callback(log_msg, percent): 进度回调，percent 为 0-100 百分比
    """
    logs = []

    def _log(msg, percent=None):
        logs.append(msg)
        if progress_callback:
            progress_callback(msg, percent)

    # 发送初始进度
    _log("[开始] 准备拉取日志...", 0)

    if local_save_dir:
        local_dir = local_save_dir.rstrip('/')
        os.makedirs(local_dir, exist_ok=True)
    else:
        port_suffix = str(port)[-4:]
        today = datetime.now().strftime("%Y%m%d")
        local_dir = os.path.join(LOCAL_LOG_PULL_BASE, port_suffix, today)
        os.makedirs(local_dir, exist_ok=True)

    ssh_base = [
        "ssh", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=15",
        f"{SSH_USER}@{SSH_HOST}", "-p", str(port)
    ]
    # Test connection
    _log(f"[连接] ssh root@{SSH_HOST} -p {port}")
    try:
        r = subprocess.run(
            ssh_base + ["echo ok"],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode != 0:
            return {"ok": False, "error": f"SSH 连接失败: {r.stderr.strip()}", "logs": logs}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "SSH 连接超时", "logs": logs}
    except Exception as e:
        return {"ok": False, "error": f"SSH 错误: {e}", "logs": logs}

    _log(f"[连接] SSH 连接成功", 5)

    # List log files
    remote_log_dir = "/userdata/log_dir"
    try:
        r = subprocess.run(
            ssh_base + [f"find {remote_log_dir} -type f 2>/dev/null | head -500"],
            capture_output=True, text=True, timeout=30
        )
        all_files = [f.strip() for f in r.stdout.strip().splitlines() if f.strip()]
    except Exception as e:
        return {"ok": False, "error": f"列举日志失败: {e}", "logs": logs}

    if not all_files:
        return {"ok": False, "error": f"远端 {remote_log_dir} 无日志文件", "logs": logs}

    _log(f"[扫描] 发现 {len(all_files)} 个文件", 10)

    # Find latest mtime to determine local folder date
    try:
        stat_cmd = " ; ".join(f"stat -c '%Y %n' {f} 2>/dev/null" for f in all_files[:100])
        r = subprocess.run(ssh_base + [stat_cmd], capture_output=True, text=True, timeout=30)
        mtimes = {}
        for line in r.stdout.strip().splitlines():
            parts = line.strip().split(" ", 1)
            if len(parts) == 2:
                try:
                    mtimes[parts[1]] = int(parts[0])
                except ValueError:
                    pass
    except Exception:
        mtimes = {}

    if mtimes and not local_save_dir:
        latest_ts = max(mtimes.values())
        latest_dt = datetime.fromtimestamp(latest_ts)
        folder_date = latest_dt.strftime("%Y%m%d")
        local_dir = os.path.join(LOCAL_LOG_PULL_BASE, port_suffix, folder_date)
        os.makedirs(local_dir, exist_ok=True)
        _log(f"[时间戳] 最新日志时间: {latest_dt.strftime('%Y-%m-%d %H:%M:%S')}", 12)

    _log(f"[保存] 本地目录: {local_dir}", 15)

    # Transfer files in batches (20/batch) to avoid SSH disconnection on large directories
    downloaded = []
    errors = []
    ssh_opts = (
        f"ssh -i {SSH_KEY} -o StrictHostKeyChecking=no -o ConnectTimeout=30 "
        f"-o ServerAliveInterval=10 -o ServerAliveCountMax=3 "
        f"-o TCPKeepAlive=yes -o LogLevel=ERROR "
        f"-o Compression=yes -o IPQoS=throughput -p {port}"
    )
    BATCH = 20
    total_ok = 0
    num_batches = (len(all_files) + BATCH - 1) // BATCH
    for bi, batch_start in enumerate(range(0, len(all_files), BATCH)):
        batch = all_files[batch_start:batch_start + BATCH]
        rel_paths = [f[len(remote_log_dir):].lstrip('/') for f in batch]
        tf_path = None
        retry_count = 0
        max_retries = 2

        while retry_count <= max_retries:
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tf:
                    tf.write('\n'.join(rel_paths) + '\n')
                    tf_path = tf.name
                rsync_cmd = [
                    "rsync", "-av", "--timeout=180", "--partial", "--inplace",
                    "--files-from", tf_path,
                    "-e", ssh_opts,
                    f"{SSH_USER}@{SSH_HOST}:{remote_log_dir}/",
                    local_dir + "/",
                ]
                rc = subprocess.run(rsync_cmd, capture_output=True, text=True, timeout=240)
                if rc.returncode == 0:
                    total_ok += len(batch)
                    percent = int(15 + (bi + 1) * 85 / num_batches) if num_batches > 0 else 100
                    _log(f"[进度] {percent}% - 批次 {bi+1}/{num_batches} 完成 ({len(batch)} 文件)", percent)
                    break
                else:
                    err = (rc.stderr.strip() or rc.stdout.strip() or "rsync 失败")[:300]
                    if retry_count < max_retries:
                        _log(f"[重试] 批次 {bi+1}/{num_batches} 失败，重试 {retry_count+1}/{max_retries}: {err[:100]}")
                        retry_count += 1
                        time.sleep(2)
                        continue
                    else:
                        errors.append(err)
                        _log(f"[错误] 批次 {bi+1}/{num_batches} 失败: {err[:100]}")
                        break
            except subprocess.TimeoutExpired:
                if retry_count < max_retries:
                    _log(f"[重试] 批次 {bi+1}/{num_batches} 超时(240秒)，重试 {retry_count+1}/{max_retries}")
                    retry_count += 1
                    time.sleep(2)
                    continue
                else:
                    err_msg = f"批次 {bi+1} 传输超时(240秒)"
                    errors.append(err_msg)
                    _log(f"[错误] {err_msg}")
                    break
            except Exception as e:
                if retry_count < max_retries:
                    _log(f"[重试] 批次 {bi+1}/{num_batches} 异常，重试 {retry_count+1}/{max_retries}: {str(e)[:100]}")
                    retry_count += 1
                    time.sleep(2)
                    continue
                else:
                    err_msg = f"批次 {bi+1} 异常: {str(e)[:200]}"
                    errors.append(err_msg)
                    _log(f"[错误] {err_msg}")
                    break
            finally:
                if tf_path and os.path.exists(tf_path):
                    try:
                        os.unlink(tf_path)
                    except Exception:
                        pass

    if total_ok > 0:
        downloaded.append(remote_log_dir)

    file_count = sum(len(files) for _, _, files in os.walk(local_dir))

    # 即使有错误，只要下载了部分文件就算部分成功
    if file_count > 0:
        if errors:
            _log(f"[完成] 部分成功: 已下载 {file_count} 个文件，{len(errors)} 个批次失败", 100)
        else:
            _log(f"[完成] 全部成功: 已下载 {file_count} 个文件", 100)
    else:
        _log(f"[失败] 未能下载任何文件", 0)

    return {
        "ok": file_count > 0,  # 只要有文件就算成功
        "local_dir": local_dir,
        "file_count": file_count,
        "logs": logs,
        "errors": errors,
        "partial_success": len(errors) > 0 and file_count > 0,
    }


def analyze_avoiding_logs(log_dir: str, img_dir: str, progress_callback=None) -> dict:
    """
    分析避障原因：
    1. 从 img_dir 的图片文件名提取时间戳
    2. 在 log_dir 的 nav/robot_decision/stereo_perception 日志中关联对应时间窗口的日志行
    3. 生成分析意见
    """
    def report_progress(step: str, current: int = 0, total: int = 0):
        if progress_callback:
            progress_callback(step, current, total)

    logs_result = {"robot_decision": [], "nav": [], "stereo": []}
    avoiding_count = 0
    image_list = []
    time_range_str = ""

    report_progress("正在扫描图片目录...")

    # 1. Collect images from img_dir and extract timestamps
    img_timestamps = []  # list of (datetime, filepath)
    img_dir_error = None
    if img_dir:
        if not os.path.isdir(img_dir):
            img_dir_error = f"避障图片目录不存在: {img_dir}"
        else:
            img_exts = ('.jpg', '.jpeg', '.png', '.bmp')
            img_files = sorted(
                os.path.join(img_dir, f) for f in os.listdir(img_dir)
                if f.lower().endswith(img_exts)
            )
            if not img_files:
                img_dir_error = f"避障图片目录为空（未找到图片文件）: {img_dir}"
            else:
                image_list = img_files
                report_progress(f"找到 {len(img_files)} 张图片，正在提取时间戳...")
                fname_ts_re = re.compile(r'(\d{8})_(\d{6})_(\d{3})')
                for i, fpath in enumerate(img_files):
                    if i % 10 == 0:
                        report_progress(f"提取图片时间戳...", i, len(img_files))
                    m = fname_ts_re.search(os.path.basename(fpath))
                    if m:
                        try:
                            dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
                            img_timestamps.append((dt, fpath))
                        except Exception:
                            pass

    report_progress("正在检查日志目录...")

    # 2. Parse log files from log_dir
    log_dir_error = None
    if log_dir and not os.path.isdir(log_dir):
        log_dir_error = f"日志目录不存在: {log_dir}"

    # Check if both directories are invalid
    if log_dir_error and img_dir_error:
        return {"ok": False, "error": f"{log_dir_error}\n{img_dir_error}"}
    elif log_dir_error and not image_list:
        return {"ok": False, "error": log_dir_error}
    elif img_dir_error and not log_dir:
        return {"ok": False, "error": img_dir_error}

    if not log_dir or not os.path.isdir(log_dir):
        if not image_list:
            return {"ok": False, "error": "日志目录和图片目录均无效"}
        # No logs, just return image info
        report_progress("生成分析结论...")
        return {
            "ok": True,
            "avoiding_count": len(image_list),
            "image_count": len(image_list),
            "images": image_list,
            "time_range": "",
            "categories": logs_result,
            "conclusion": _generate_conclusion(logs_result, len(image_list), img_timestamps),
        }

    report_progress("正在扫描日志文件...")
    all_log_files = sorted(
        f for f in glob.glob(os.path.join(log_dir, "**", "*"), recursive=True)
        if os.path.isfile(f) and not f.endswith(('.jpg', '.png', '.pcd', '.db3', '.mcap', '.yaml', '.json'))
    )
    if not all_log_files:
        # try flat
        all_log_files = sorted(
            f for f in glob.glob(os.path.join(log_dir, "*"))
            if os.path.isfile(f)
        )

    report_progress(f"找到 {len(all_log_files)} 个日志文件，正在分类...")
    decision_files = [f for f in all_log_files if os.path.basename(f).startswith("robot_decision")]
    stereo_files   = [f for f in all_log_files if os.path.basename(f).startswith(("stere", "stereo"))]
    nav_files      = [f for f in all_log_files if os.path.basename(f).startswith("nav")]

    def read_file_lines(fpath):
        try:
            with open(fpath, "r", errors="replace") as fh:
                return fh.read().splitlines()
        except Exception:
            return []

    def grep_files(files, pattern, file_type=""):
        result = []
        for i, f in enumerate(files):
            if file_type:
                report_progress(f"正在读取 {file_type} 日志...", i + 1, len(files))
            for line in read_file_lines(f):
                if not pattern or pattern in line:
                    result.append(line)
        return result

    report_progress(f"正在分析 robot_decision 日志 ({len(decision_files)} 个文件)...")
    decision_raw = grep_files(decision_files, "AVOIDING", "robot_decision")

    report_progress(f"正在分析 stereo_perception 日志 ({len(stereo_files)} 个文件)...")
    stereo_raw   = grep_files(stereo_files, "", "stereo_perception")

    report_progress(f"正在分析 nav 日志 ({len(nav_files)} 个文件)...")
    nav_raw      = grep_files(nav_files, "", "nav")

    avoiding_count = len(decision_raw)
    report_progress(f"找到 {avoiding_count} 条避障日志，正在关联时间窗口...")

    # Determine time window from image timestamps or AVOIDING log timestamps
    window_start = None
    window_end   = None
    if img_timestamps:
        ts_vals = [t for t, _ in img_timestamps]
        window_start = min(ts_vals) - timedelta(seconds=5)
        window_end   = max(ts_vals) + timedelta(seconds=5)
    elif decision_raw:
        ts_vals = [parse_ros2_log_timestamp(l) for l in decision_raw]
        ts_vals = [t for t in ts_vals if t]
        if ts_vals:
            window_start = min(ts_vals) - timedelta(seconds=30)
            window_end   = max(ts_vals) + timedelta(seconds=30)

    report_progress("正在格式化日志数据...")
    def fmt_lines(raw, window_s=None, window_e=None):
        result = []
        for line in raw:
            if not line.strip():
                continue
            ts = parse_ros2_log_timestamp(line)
            if window_s and window_e and ts:
                if not (window_s <= ts <= window_e):
                    continue
            ts_str = ts.strftime("%H:%M:%S") if ts else "??:??:??"
            result.append({"ts": ts_str, "text": line.strip()})
        return result

    logs_result["robot_decision"] = fmt_lines(decision_raw)
    logs_result["stereo"]         = fmt_lines(stereo_raw, window_start, window_end)
    logs_result["nav"]            = fmt_lines(nav_raw,    window_start, window_end)

    if window_start and window_end:
        time_range_str = f"{window_start.strftime('%H:%M:%S')} ~ {window_end.strftime('%H:%M:%S')}"

    report_progress("正在生成分析结论...")
    conclusion = _generate_conclusion(logs_result, len(image_list), img_timestamps)

    return {
        "ok": True,
        "avoiding_count": avoiding_count or len(image_list),
        "image_count": len(image_list),
        "images": image_list,
        "time_range": time_range_str,
        "categories": logs_result,
        "conclusion": conclusion,
    }


def _generate_conclusion(categories: dict, image_count: int, img_timestamps: list) -> str:
    """基于日志和图片时间戳生成避障原因分析文本。"""
    decision_lines = categories.get("robot_decision", [])
    stereo_lines   = categories.get("stereo", [])
    nav_lines      = categories.get("nav", [])

    lines = []
    lines.append("## 避障原因综合分析")
    lines.append("")

    avoiding_count = len(decision_lines)
    lines.append(f"**避障事件数**: {avoiding_count} 条 AVOIDING 日志")
    lines.append(f"**关联图片数**: {image_count} 张")

    if img_timestamps:
        ts_vals = [t for t, _ in img_timestamps]
        lines.append(f"**图片时间范围**: {min(ts_vals).strftime('%H:%M:%S')} ~ {max(ts_vals).strftime('%H:%M:%S')}")

    lines.append("")
    lines.append("### robot_decision 分析")
    if decision_lines:
        lines.append(f"共发现 {len(decision_lines)} 条 AVOIDING 决策日志。")
        # Look for common patterns
        stat_count = sum(1 for r in decision_lines if "stat" in r["text"].lower() or "static" in r["text"].lower())
        near_count = sum(1 for r in decision_lines if "near" in r["text"].lower() or "0.1" in r["text"] or "0.0" in r["text"])
        if stat_count > 0:
            lines.append(f"- 其中 {stat_count} 条涉及静态障碍物(stat)相关判定，疑似感知误识别触发。")
        if near_count > 0:
            lines.append(f"- 其中 {near_count} 条涉及近距离障碍物判定(near_obstacle_limit)。")
    else:
        lines.append("未找到 AVOIDING 日志，可能日志目录不含 robot_decision 日志文件。")

    lines.append("")
    lines.append("### stereo_perception 分析")
    if stereo_lines:
        lines.append(f"共找到 {len(stereo_lines)} 条感知日志。")
        # Check for obstacle labels (label=1 background, label=5 obstacle)
        obstacle_count = sum(1 for r in stereo_lines if "label=1" in r["text"] or "label=5" in r["text"])
        road_count = sum(1 for r in stereo_lines if "label=3" in r["text"])
        grass_count = sum(1 for r in stereo_lines if "grass" in r["text"].lower() or "label=2" in r["text"])
        if obstacle_count > 0:
            lines.append(f"- 感知日志中 {obstacle_count} 条包含 label=1(背景)/label=5(障碍物)，说明感知层检测到障碍物。")
        if road_count > 0:
            lines.append(f"- {road_count} 条包含 label=3(road/可通行区域)，正常可通行标签。")
        if grass_count > 0:
            lines.append(f"- {grass_count} 条包含 grass/label=2，草地场景。")
        if obstacle_count == 0:
            lines.append("- 未发现明显障碍物标签(label=1/5)，建议人工检查感知日志。")
    else:
        lines.append("未找到 stereo_perception 日志。")

    lines.append("")
    lines.append("### nav 导航分析")
    if nav_lines:
        lines.append(f"共找到 {len(nav_lines)} 条 nav 日志。")
        stop_count = sum(1 for r in nav_lines if "stop" in r["text"].lower() or "避障" in r["text"] or "blocked" in r["text"].lower())
        if stop_count > 0:
            lines.append(f"- nav 日志中 {stop_count} 条涉及停止/阻塞，与避障决策相关。")
    else:
        lines.append("未找到 nav 日志。")

    lines.append("")
    lines.append("### 综合判断")
    if decision_lines or stereo_lines:
        lines.append("根据日志分析，**最可能的误避障原因**为：")
        lines.append("1. stereo_perception 分割模型将草地/低矮植被误分类为障碍物(label=1 背景或 label=5 障碍物)")
        lines.append("2. 误识别导致 robot_decision 层触发 near_obstacle_limit 停障规则")
        lines.append("3. 建议：增加地面点过滤、调整 label=1/5 阈值、补充草地训练数据")
        lines.append("")
        lines.append("**标签说明**：label=3 是 road(可通行区域)，label=1 是 background(背景/障碍物)，label=5 是 obstacle(障碍物)")
    else:
        lines.append("日志数据不足，无法自动判断原因，建议人工检查图片和日志。")

    return "\n".join(lines)


class OfflineHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors()
        self.end_headers()

    def _json(self, data: dict, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_cors()
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/offline/list_camera_bag_files":
            # 列出 camera bag 中的所有图片和点云文件
            bag_dir = qs.get("bag_dir", [""])[0]
            if not bag_dir:
                self._json({"ok": False, "error": "Missing bag_dir"})
                return

            stereo_dir = os.path.join(bag_dir, "bag_extract_camera", "bag_extract_stereo")
            pcd_dir = os.path.join(bag_dir, "bag_extract_camera", "bag_extract_pcd")

            if not os.path.isdir(stereo_dir) or not os.path.isdir(pcd_dir):
                self._json({"ok": False, "error": "Directories not found"})
                return

            # 获取所有文件并按 match 编号排序
            img_files = sorted(glob.glob(os.path.join(stereo_dir, "match_*.jpg")))
            pcd_files = sorted(glob.glob(os.path.join(pcd_dir, "match_*.pcd")))

            # 构建配对列表
            files = []
            for img_path in img_files:
                img_name = os.path.basename(img_path)
                match_num = img_name.split('_')[1]  # 提取 match_XXXX 中的编号

                # 查找对应的 pcd 文件
                pcd_path = ""
                for pcd in pcd_files:
                    if f"match_{match_num}_" in pcd:
                        pcd_path = pcd
                        break

                files.append({
                    "img": img_path,
                    "pcd": pcd_path,
                    "label": img_name[:50],
                })

            self._json({"ok": True, "files": files})
            return

        if path == "/offline/list_camera_files":
            # 列出 camera 包中的图片和点云文件
            match_num = qs.get("match_num", [""])[0]
            bag_dir = qs.get("bag_dir", [""])[0]

            if not bag_dir or not match_num:
                self._json({"ok": False, "error": "Missing bag_dir or match_num"})
                return

            stereo_dir = os.path.join(bag_dir, "bag_extract_camera", "bag_extract_stereo")
            pcd_dir = os.path.join(bag_dir, "bag_extract_camera", "bag_extract_pcd")

            # 查找匹配的文件
            img_pattern = f"match_{match_num}_*.jpg"
            pcd_pattern = f"match_{match_num}_*.pcd"

            img_files = glob.glob(os.path.join(stereo_dir, img_pattern))
            pcd_files = glob.glob(os.path.join(pcd_dir, pcd_pattern))

            self._json({
                "ok": True,
                "img": os.path.basename(img_files[0]) if img_files else "",
                "pcd": os.path.basename(pcd_files[0]) if pcd_files else "",
                "img_path": img_files[0] if img_files else "",
                "pcd_path": pcd_files[0] if pcd_files else "",
            })
            return

        if path == "/offline/config":
            # 返回配置信息给前端
            from config_loader import load_ssh_config
            config = load_ssh_config()
            self._json({
                "ok": True,
                "default_ports": config.get("default_ports", {
                    "realtime_monitor": 10015,
                    "log_fetch": 10016,
                    "stereo_analysis": 10115
                })
            })
            return

        if path == "/offline/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_cors()
            self.end_headers()
            _sse_clients.append(self.wfile)
            try:
                while True:
                    time.sleep(15)
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except Exception:
                pass
            finally:
                if self.wfile in _sse_clients:
                    _sse_clients.remove(self.wfile)
            return

        if path == "/offline/check_existing_result":
            folder = qs.get("folder", [""])[0]
            if not folder or not os.path.isdir(folder):
                self._json({"ok": False, "error": "Folder not found"})
                return

            # Check for existing results (matching build_output_dir logic)
            # Priority: Mode 7 (Night/DSG) which is commonly used in StereoAnalysis2
            candidates = [
                (7, 205), (99, 205), (6, 205), (5, 205)
            ]

            found_dir = ""
            for mode, erode in candidates:
                out_dir = build_output_dir(folder, mode, erode)
                if os.path.isdir(out_dir):
                    found_dir = out_dir
                    break

            if found_dir:
                images = sorted([
                    os.path.basename(f) for f in
                    glob.glob(os.path.join(found_dir, "*.jpg")) +
                    glob.glob(os.path.join(found_dir, "*.png"))
                ])
                # Try to find PCD dir
                pcd_dir = ""
                pcd_candidates = [
                    os.path.join(folder, "dsg_pcd_debug"),
                    os.path.join(folder, "dsg_multi_pcd"),
                    os.path.join(folder, "pcd_7_205_432"),
                    os.path.join(folder, "pcd_99_205_432"),
                    os.path.join(folder, "images", "pcd_7_205_0304_432")
                ]
                for d in pcd_candidates:
                    if os.path.isdir(d):
                        pcd_dir = d
                        break

                pcds = sorted([os.path.basename(f) for f in glob.glob(os.path.join(pcd_dir, "*.pcd"))]) if pcd_dir else []

                self._json({
                    "ok": True,
                    "output_dir": found_dir,
                    "images": images,
                    "pcd_dir": pcd_dir,
                    "pcds": pcds
                })
            else:
                self._json({"ok": False, "error": "No existing results found"})
            return

        if path == "/offline/bag_timerange":
            bag_dir = qs.get("bag_dir", [""])[0]
            t_start, t_end = parse_bag_timerange(bag_dir)
            if t_start is None:
                self._json({"ok": False, "error": "无法解析 bag 时间戳，请确认目录包含 metadata.yaml 或 manifest.json"})
            else:
                self._json({"ok": True, "bag_start": t_start.strftime("%Y-%m-%d %H:%M:%S"), "bag_end": t_end.strftime("%Y-%m-%d %H:%M:%S")})
            return

        if path == "/offline/scan_dirs":
            base = qs.get("base", ["/home/youfeng/debug"])[0]
            dirs = scan_input_dirs(base)
            self._json({"dirs": dirs})
            return

        if path == "/offline/check_existing_result":
            try:
                folder = qs.get("folder", [""])[0]
                if not folder or not os.path.isdir(folder):
                    self._json({"ok": False, "error": "Folder not found"})
                    return

                # Check common output directory candidates
                candidates = [99, 7, 6, 5]
                found_dir = None
                for mode in candidates:
                    d = build_output_dir(folder, mode)
                    if os.path.isdir(d) and any(f.lower().endswith(('.jpg', '.png')) for f in os.listdir(d)):
                        found_dir = d
                        break

                if not found_dir:
                    self._json({"ok": False, "error": "No existing result found"})
                    return

                images = sorted([f for f in os.listdir(found_dir) if f.lower().endswith(('.jpg', '.png'))])

                # Try to find PCD directory
                pcd_dir = ""
                pcds = []
                pcd_candidates = [
                    os.path.join(folder, "dsg_pcd_debug"),
                    os.path.join(folder, "dsg_multi_pcd"),
                    os.path.join(folder, "pcd_7_205_432"),
                    os.path.join(folder, "pcd_99_205_432"),
                    os.path.join(folder, "images", "pcd_7_205_0304_432"),
                ]
                for d in pcd_candidates:
                    if os.path.isdir(d):
                        pcd_dir = d
                        pcds = sorted([f for f in os.listdir(d) if f.lower().endswith('.pcd')])
                        break

                self._json({
                    "ok": True,
                    "output_dir": found_dir,
                    "images": images,
                    "pcd_dir": pcd_dir,
                    "pcds": pcds
                })
            except Exception as e:
                self._json({"ok": False, "error": str(e)})
            return

        if path == "/offline/scan_nav_folder":
            try:
                folder = qs.get("folder", [""])[0]
                filter_label = qs.get("filter_label", [""])[0]
                if not folder or not os.path.isdir(folder):
                    self._json({"ok": False, "error": f"目录不存在: {folder}"})
                    return
                img_exts = ('.jpg', '.jpeg', '.png', '.bmp')
                # 首先检查是否存在子目录，如果不存在或子目录内无匹配文件，则回退到根目录
                images_dir = os.path.join(folder, "images")
                if not os.path.isdir(images_dir) or not any(f.lower().endswith(img_exts) for f in os.listdir(images_dir)):
                    images_dir = folder

                pcds_dir = os.path.join(folder, "pointclouds")
                if not os.path.isdir(pcds_dir) or not any(f.lower().endswith('.pcd') for f in os.listdir(pcds_dir)):
                    alt = os.path.join(folder, "pcd")
                    pcds_dir = alt if os.path.isdir(alt) and any(f.lower().endswith('.pcd') for f in os.listdir(alt)) else folder

                print(f"[Scan] folder={folder}, images_dir={images_dir}, pcds_dir={pcds_dir}")
                all_images = sorted(
                    f for f in os.listdir(images_dir)
                    if os.path.isfile(os.path.join(images_dir, f)) and f.lower().endswith(img_exts)
                ) if os.path.isdir(images_dir) else []
                all_pcds = sorted(
                    f for f in os.listdir(pcds_dir)
                    if os.path.isfile(os.path.join(pcds_dir, f)) and f.lower().endswith('.pcd')
                ) if os.path.isdir(pcds_dir) else []

                if filter_label and int(filter_label) > 0:
                    target_label = int(filter_label)

                    def _pcd_has_label(pcd_path, tgt):
                        try:
                            label_col = -1
                            in_data = False
                            with open(pcd_path, 'rb') as fh:
                                for raw in fh:
                                    line = raw.decode('ascii', errors='ignore').strip()
                                    if not in_data:
                                        if line.startswith('FIELDS'):
                                            cols = line.split()[1:]
                                            label_col = cols.index('label') if 'label' in cols else -1
                                            print(f"[Scan] FIELDS: {cols}, label_col: {label_col}")
                                        elif line.startswith('DATA'):
                                            if b'binary' in raw:
                                                return False
                                            in_data = True
                                            if label_col < 0:
                                                return False
                                    else:
                                        if not line:
                                            continue
                                        cols = line.split()
                                        if label_col < len(cols):
                                            try:
                                                if int(float(cols[label_col])) == tgt:
                                                    return True
                                            except (ValueError, IndexError):
                                                pass
                        except Exception:
                            pass
                        return False

                    img_stem_map = {os.path.splitext(f)[0]: f for f in all_images}
                    matched_pairs = []
                    for pcd_fname in all_pcds:
                        if not _pcd_has_label(os.path.join(pcds_dir, pcd_fname), target_label):
                            continue
                        pcd_stem = os.path.splitext(pcd_fname)[0]
                        img_fname = img_stem_map.get(pcd_stem)
                        if not img_fname:
                            m = re.match(r'(match_\d+)', pcd_stem)
                            if m:
                                prefix = m.group(1)
                                img_fname = next((f for f in all_images if f.startswith(prefix)), None)
                        matched_pairs.append({"pcd": pcd_fname, "img": img_fname})

                    self._json({
                        "ok": True,
                        "images_dir": images_dir,
                        "pcds_dir": pcds_dir,
                        "total_pcds": len(all_pcds),
                        "total_images": len(all_images),
                        "filtered": True,
                        "filter_label": target_label,
                        "match_count": len(matched_pairs),
                        "pairs": matched_pairs,
                    })
                else:
                    self._json({
                        "ok": True,
                        "images_dir": images_dir,
                        "pcds_dir": pcds_dir,
                        "image_count": len(all_images),
                        "pcd_count": len(all_pcds),
                        "images": all_images,
                        "pcds": all_pcds,
                        "filtered": False,
                    })
            except Exception as _e:
                self._json({"ok": False, "error": f"内部错误: {_e}"})
            return

        if path == "/offline/scan_images":
            directory = qs.get("dir", [""])[0]
            if not os.path.isdir(directory):
                self._json({"images": [], "pcds": [], "pcd_dir": ""})
                return
            img_exts = ('.jpg', '.jpeg', '.png', '.bmp')
            images = sorted(f for f in os.listdir(directory)
                            if os.path.isfile(os.path.join(directory, f))
                            and f.lower().endswith(img_exts))
            pcd_dir = os.path.join(directory, "pcd")
            pcds = []
            if os.path.isdir(pcd_dir):
                pcds = sorted(f for f in os.listdir(pcd_dir)
                              if f.lower().endswith('.pcd'))
            else:
                # Fall back: .pcd files co-located with images in the same directory
                inline_pcds = sorted(f for f in os.listdir(directory)
                                     if os.path.isfile(os.path.join(directory, f))
                                     and f.lower().endswith('.pcd'))
                if inline_pcds:
                    pcd_dir = directory
                    pcds = inline_pcds
            self._json({"images": images, "pcds": pcds, "pcd_dir": pcd_dir})
            return

        # Serve arbitrary local file: GET /offline/local_file?path=<abs_path>
        if path == "/offline/local_file":
            fpath = qs.get("path", [""])[0]
            if not fpath:
                self.send_response(404)
                self.end_headers()
                return

            # If path is relative, resolve it relative to the project root
            if not os.path.isabs(fpath):
                # Get the project root directory (parent of robot_monitor)
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                fpath = os.path.join(project_root, fpath)

            if not os.path.isfile(fpath):
                print(f"[local_file] File not found: {fpath}")
                self.send_response(404)
                self.end_headers()
                return
            ext = os.path.splitext(fpath)[1].lower()
            ctype = "image/jpeg" if ext in ('.jpg', '.jpeg') else \
                    "image/png" if ext == '.png' else \
                    "text/plain" if ext == '.pcd' else \
                    "application/octet-stream"

            try:
                with open(fpath, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_cors()
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                print(f"[local_file] Error reading file {fpath}: {e}")
                self.send_response(500)
                self.end_headers()
            return

        if path == "/offline/modes":
            self._json({"modes": [{"value": k, "label": f"Mode {k}: {v}"} for k, v in INFER_MODES.items()]})
            return

        if path == "/offline/status":
            self._json({"running": _running, "result": _last_result})
            return

        # Serve output image by filename
        if path.startswith("/offline/image/"):
            fname = os.path.basename(path)
            fpath = os.path.join(_last_result.get("output_dir", ""), fname)
            if os.path.isfile(fpath):
                with open(fpath, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_cors()
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()
            return

        # Serve extracted images from nav bag parsing
        if path.startswith("/offline/extracted_image/"):
            from urllib.parse import unquote
            # Remove the prefix and decode
            relative_path = path.replace("/offline/extracted_image/", "")
            relative_path = unquote(relative_path)

            # The path should be: {dir_path}/{filename}
            # Try to construct the full path
            if relative_path:
                # If it's an absolute path, use it directly
                if os.path.isabs(relative_path):
                    fpath = relative_path
                else:
                    # Otherwise, treat it as relative to PROJECT_ROOT
                    fpath = os.path.join(PROJECT_ROOT, relative_path)

                if os.path.isfile(fpath):
                    with open(fpath, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_cors()
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    print(f"[DEBUG] Image not found: {fpath}")
                    self.send_response(404)
                    self.send_header("Content-Type", "text/plain")
                    self.send_cors()
                    self.end_headers()
                    self.wfile.write(f"File not found: {fpath}".encode())
            else:
                self.send_response(400)
                self.end_headers()
            return

        # Serve pcd by filename
        if path.startswith("/offline/pcd/"):
            fname = os.path.basename(path)
            pcds = _last_result.get("pcds", [])
            fpath = next((p for p in pcds if os.path.basename(p) == fname), None)
            if fpath and os.path.isfile(fpath):
                with open(fpath, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(data)))
                self.send_cors()
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()
            return

        # Serve offline result image by frame index (for comparison view)
        # GET /offline/result_image/<frame_idx>  → finds matching image in _last_result
        if path.startswith("/offline/result_image/"):
            # Extract filename from path and remove extension
            filename = path.replace("/offline/result_image/", "")
            stem = os.path.splitext(filename)[0]  # e.g. "match_0000_ts1774552944595367288_272224_595_dsg"
            images = _last_result.get("images", [])
            # match by stem (without extension)
            fpath = next(
                (p for p in images if os.path.splitext(os.path.basename(p))[0] == stem),
                None
            )
            if fpath and os.path.isfile(fpath):
                with open(fpath, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_cors()
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()
            return

        # Serve offline result pcd by frame index
        # GET /offline/result_pcd/<frame_idx>
        if path.startswith("/offline/result_pcd/"):
            stem = os.path.basename(path)
            pcds = _last_result.get("pcds", [])
            fpath = next(
                (p for p in pcds if os.path.splitext(os.path.basename(p))[0].endswith(stem)),
                None
            )
            if fpath and os.path.isfile(fpath):
                with open(fpath, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(data)))
                self.send_cors()
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()
            return

        # Serve avoiding-matched image: GET /offline/avoiding_image/<filename>
        if path.startswith("/offline/avoiding_image/"):
            fname = os.path.basename(path)
            fpath = os.path.join(BAG_DATA_DIR, "images", fname)
            if os.path.isfile(fpath):
                with open(fpath, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_cors()
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()
            return

        # Serve avoiding-matched pcd: GET /offline/avoiding_pcd/<filename>
        if path.startswith("/offline/avoiding_pcd/"):
            fname = os.path.basename(path)
            fpath = os.path.join(BAG_DATA_DIR, "pointclouds", fname)
            if os.path.isfile(fpath):
                with open(fpath, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(data)))
                self.send_cors()
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()
            return

        if path == "/ros2deploy/start_docker":
            # Docker 交叉编译目录：使用项目内 cross_compile 目录（如果存在）
            cross_compile_dir = os.path.join(PROJECT_ROOT, "cross_compile")
            if not os.path.exists(cross_compile_dir):
                cross_compile_dir = PROJECT_ROOT  # 如果不存在，使用项目根目录

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_cors()
            self.end_headers()

            def _send(msg):
                try:
                    data = "data: " + json.dumps(msg, ensure_ascii=False) + "\n\n"
                    self.wfile.write(data.encode())
                    self.wfile.flush()
                except Exception:
                    pass

            _send({"type": "files", "files": [], "dir": cross_compile_dir})
            _send({"type": "log", "text": "[启动] 正在启动 Docker 交互终端..."})

            try:
                import pty, os as _os, select as _select, termios
                master_fd, slave_fd = pty.openpty()
                # Set a reasonable terminal size
                import fcntl, struct
                fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 200, 0, 0))
                env = _os.environ.copy()
                env['TERM'] = 'dumb'
                env.pop('LS_COLORS', None)
                proc = subprocess.Popen(
                    ['docker', 'run', '--cap-add=NET_ADMIN', '-it', '--rm',
                     '-v', f'{cross_compile_dir}:/open_explorer',
                     '-v', f'{PROJECT_ROOT}/data:/data',
                     '-v', f'{PROJECT_ROOT}:/offline_debug',
                     'evb_x5_system:v1.5', '/bin/bash'],
                    stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                    close_fds=True, env=env,
                )
                _os.close(slave_fd)
                _docker_sessions['current'] = {'proc': proc, 'master_fd': master_fd}
                _send({"type": "log", "text": f"[PID] {proc.pid}"})
                _send({"type": "ready"})
                buf = b''
                while True:
                    try:
                        r, _, _ = _select.select([master_fd], [], [], 0.1)
                    except Exception:
                        break
                    if r:
                        try:
                            chunk = _os.read(master_fd, 4096)
                        except OSError:
                            break
                        if not chunk:
                            break
                        buf += chunk
                        # Emit line-buffered output
                        while b'\n' in buf or b'\r' in buf:
                            for sep in [b'\r\n', b'\n', b'\r']:
                                idx = buf.find(sep)
                                if idx >= 0:
                                    line = _strip_ansi(buf[:idx].decode('utf-8', errors='replace'))
                                    buf = buf[idx+len(sep):]
                                    if line:
                                        _send({"type": "log", "text": line})
                                    break
                            else:
                                break
                    if proc.poll() is not None:
                        # Drain remaining
                        try:
                            while True:
                                r2, _, _ = _select.select([master_fd], [], [], 0.05)
                                if not r2:
                                    break
                                chunk = _os.read(master_fd, 4096)
                                if not chunk:
                                    break
                                for line in chunk.decode('utf-8', errors='replace').splitlines():
                                    line = _strip_ansi(line)
                                    if line:
                                        _send({"type": "log", "text": line})
                        except OSError:
                            pass
                        break
                try:
                    _os.close(master_fd)
                except OSError:
                    pass
                _docker_sessions.pop('current', None)
                _send({"type": "done", "exit_code": proc.returncode})
            except Exception as e:
                _send({"type": "error", "text": str(e)})
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/offline/run":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            input_dir = body.get("input_dir", "")
            infer_mode = int(body.get("infer_mode", 7))
            erode_pixel = int(body.get("erode_pixel", 205))
            resume = body.get("resume", False)

            if _running:
                self._json({"ok": False, "error": "already running"}, 409)
                return
            if not os.path.isdir(input_dir):
                self._json({"ok": False, "error": f"directory not found: {input_dir}"}, 400)
                return

            Thread(target=run_offline_test, args=(input_dir, infer_mode, erode_pixel, False, resume), daemon=True).start()
            self._json({"ok": True, "output_dir": build_output_dir(input_dir, infer_mode, erode_pixel)})
            return

        if path == "/offline/stop":
            if _current_proc:
                _current_proc.terminate()
                self._json({"ok": True})
            else:
                self._json({"ok": False, "error": "not running"})
            return

        if path == "/offline/check_result":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            input_dir = body.get("input_dir", "")
            infer_mode = int(body.get("infer_mode", 7))
            erode_pixel = int(body.get("erode_pixel", 205))

            if not input_dir or not os.path.isdir(input_dir):
                self._json({"ok": False, "exists": False})
                return

            # Check if result directory exists
            output_dir = build_output_dir(input_dir, infer_mode, erode_pixel)
            if not os.path.isdir(output_dir):
                self._json({"ok": True, "exists": False})
                return

            # Scan for result images
            output_images = sorted(
                glob.glob(os.path.join(output_dir, "*.jpg")) +
                glob.glob(os.path.join(output_dir, "*.png"))
            )

            if not output_images:
                self._json({"ok": True, "exists": False})
                return

            # Result exists, update _last_result so images can be served
            global _last_result
            _last_result = {
                "output_dir": output_dir,
                "images": output_images,
                "pcds": [],
            }

            # Return info
            self._json({
                "ok": True,
                "exists": True,
                "output_dir": output_dir,
                "image_count": len(output_images),
                "images": [os.path.basename(p) for p in output_images],
            })
            return

        # Export suspicious frames from bag data to a temp dir, then run offline test
        if path == "/offline/export_and_run":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            frames = body.get("frames", [])       # list of {idx, img_left, img_right}
            infer_mode = int(body.get("infer_mode", 7))
            erode_pixel = int(body.get("erode_pixel", 205))
            export_dir = body.get("export_dir", os.path.join(BAG_DATA_DIR, "_suspicious_export"))

            if _running:
                self._json({"ok": False, "error": "already running"}, 409)
                return
            if not frames:
                self._json({"ok": False, "error": "no frames provided"}, 400)
                return

            # Export frames synchronously (fast), then run offline test in background
            result = export_suspicious_frames(frames, export_dir)
            if result["count"] == 0:
                self._json({"ok": False, "error": "no images exported", "details": result["errors"]}, 400)
                return

            Thread(target=run_offline_test, args=(export_dir, infer_mode, erode_pixel, True), daemon=True).start()
            self._json({
                "ok": True,
                "export_dir": export_dir,
                "exported_count": result["count"],
                "output_dir": build_output_dir(export_dir, infer_mode, erode_pixel),
            })
            return

        if path == "/offline/mono_test":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            input_dir = body.get("input_dir", "")
            if not input_dir or not os.path.isdir(input_dir):
                self._json({"ok": False, "error": f"directory not found: {input_dir}"}, 400)
                return
            result = run_mono_test(input_dir)
            self._json(result)
            return

        if path == "/offline/parse_nav_bag":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            nav_path = body.get("nav_path", "")

            if not nav_path:
                self._json({"ok": False, "error": "nav_path required"}, 400)
                return

            if not os.path.exists(nav_path):
                self._json({"ok": False, "error": f"path not found: {nav_path}"}, 400)
                return

            # Collect logs
            logs = []
            def log_cb(msg):
                logs.append(msg)

            # Extract nav bag
            success = extract_left_pcl_bag(nav_path, log_cb, bag_type='nav')

            if not success:
                self._json({"ok": False, "error": "extraction failed", "logs": logs}, 400)
                return

            # Find extracted files
            nav_path_obj = Path(nav_path)
            extract_base = nav_path_obj / "bag_extract_nav"
            img_dir = extract_base / "bag_extract_left"
            pcd_dir = extract_base / "bag_extract_pcd"

            images = []
            pcds = []

            if img_dir.exists():
                images = sorted([f.name for f in img_dir.glob("*.jpg")])

            if pcd_dir.exists():
                pcds = sorted([f.name for f in pcd_dir.glob("*.pcd")])

            self._json({
                "ok": True,
                "image_count": len(images),
                "pcd_count": len(pcds),
                "image_dir": str(img_dir),
                "pcd_dir": str(pcd_dir),
                "images": images[:10],  # Return first 10 for preview
                "pcds": pcds[:10],
                "logs": logs
            })
            return

        if path == "/offline/download_logs":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            bag_dir = body.get("bag_dir", BAG_DATA_DIR)
            port = int(body.get("port", 10111))
            result = download_logs_to_local(bag_dir, port)
            self._json(result)
            return

        if path == "/offline/archive_frame":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            pcd_path = body.get("pcd_path", "")
            img_path = body.get("img_path", None)
            archive_dir = body.get("archive_dir", "")
            if not archive_dir:
                self._json({"ok": False, "error": "archive_dir required"})
                return
            stereo_dir = os.path.join(archive_dir, "select_stereo")
            pcd_dir = os.path.join(archive_dir, "select_pcd")
            os.makedirs(stereo_dir, exist_ok=True)
            os.makedirs(pcd_dir, exist_ok=True)
            archived = 0
            errors = []
            if img_path:
                if os.path.isfile(img_path):
                    try:
                        shutil.copy2(img_path, os.path.join(stereo_dir, os.path.basename(img_path)))
                        archived += 1
                    except Exception as e:
                        errors.append(str(e))
                else:
                    errors.append(f"not found: {img_path}")
            if pcd_path:
                if os.path.isfile(pcd_path):
                    try:
                        shutil.copy2(pcd_path, os.path.join(pcd_dir, os.path.basename(pcd_path)))
                        archived += 1
                    except Exception as e:
                        errors.append(str(e))
                else:
                    errors.append(f"not found: {pcd_path}")
            self._json({"ok": True, "archived_count": archived,
                        "stereo_dir": stereo_dir, "pcd_dir": pcd_dir, "errors": errors})
            return

        if path == "/offline/extract_avoiding_frames":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            local_dir = body.get("local_dir", "")
            bag_data_dir = body.get("bag_data_dir", BAG_DATA_DIR)
            window_s = float(body.get("window_s", 1.0))
            result = extract_avoiding_frames(local_dir, bag_data_dir, window_s)
            self._json(result)
            return

        if path == "/offline/fetch_avoiding_logs":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            local_dir = body.get("local_dir", "")
            if local_dir:
                bag_dir_for_local = body.get("bag_dir", "")
                result = fetch_avoiding_logs_local(local_dir, bag_dir_for_local)
            else:
                bag_dir = body.get("bag_dir", BAG_DATA_DIR)
                port = int(body.get("port", 10111))
                result = fetch_avoiding_logs(bag_dir, port)
            self._json(result)
            return

        if path == "/api/extract":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            nav_path = body.get("nav_bag", "")
            bag_type = body.get("bag_type", "nav")  # 获取包类型，默认为nav
            logs = []
            try:
                ok = extract_nav_bag(nav_path, logs.append, bag_type)
                self._json({"ok": ok, "logs": logs})
            except Exception as e:
                logs.append(f"ERROR: {e}")
                self._json({"ok": False, "logs": logs}, 500)
            return

        if path == "/api/bag_topics":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            nav_path = body.get("nav_bag", "")
            try:
                db3_file = find_db3_file(nav_path)
                if not db3_file:
                    self._json({"ok": False, "topics": [], "error": f"找不到 .db3 文件: {nav_path}"})
                    return
                conn = sqlite3.connect(str(db3_file))
                cur = conn.cursor()
                topics = [row[0] for row in cur.execute('SELECT name FROM topics')]
                conn.close()
                self._json({"ok": True, "topics": topics})
            except Exception as e:
                self._json({"ok": False, "topics": [], "error": str(e)})
            return

        if path == "/api/extract_left_pcl":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            nav_path = body.get("nav_bag", "")
            bag_type = body.get("bag_type", "nav")  # 获取包类型，默认为nav
            logs = []
            try:
                ok = extract_left_pcl_bag(nav_path, logs.append, bag_type)
                self._json({"ok": ok, "logs": logs})
            except Exception as e:
                logs.append(f"ERROR: {e}")
                self._json({"ok": False, "logs": logs}, 500)
            return

        if path == "/offline/upload_images":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            port = int(body.get("port", 10111))
            date_str = body.get("date", "")  # YYYY-MM-DD
            result = upload_images_from_robot(port, date_str)
            self._json(result)
            return

        if path == "/offline/upload_images_range":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            port = int(body.get("port", 10111))
            date_start = body.get("date_start", "")  # YYYYMMDD
            date_end = body.get("date_end", "")      # YYYYMMDD
            result = upload_images_range_from_robot(port, date_start, date_end)
            self._json(result)
            return

        if path == "/offline/pull_robot_logs":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            port = int(body.get("port", 10111))
            local_save_dir = body.get("local_save_dir", None)
            # 流式SSE输出进度
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            def progress_callback(log_msg: str, percent: int = None):
                import json as _json
                data = {"log": log_msg}
                if percent is not None:
                    data["percent"] = percent
                self.wfile.write(f"data: {_json.dumps(data)}\n\n".encode())
                self.wfile.flush()

            result = pull_robot_logs(port, local_save_dir, progress_callback)
            # 最后发送完成标记
            self.wfile.write(f"data: {json.dumps({'done': True, **result})}\n\n".encode())
            self.wfile.flush()
            return

        if path == "/offline/check_local_logs":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            local_dir = body.get("local_dir", "")
            result = check_local_logs(local_dir)
            self._json(result)
            return

        if path == "/offline/analyze_avoiding":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            log_dir = body.get("log_dir", "")
            img_dir = body.get("img_dir", "")

            # 使用流式响应返回进度
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            def progress_callback(step: str, current: int = 0, total: int = 0):
                data = {"step": step}
                if total > 0:
                    data["current"] = current
                    data["total"] = total
                    data["percent"] = int(current * 100 / total)
                self.wfile.write(f"data: {json.dumps(data)}\n\n".encode())
                self.wfile.flush()

            result = analyze_avoiding_logs(log_dir, img_dir, progress_callback)

            # 分批发送结果，避免JSON过大
            # 先发送基本信息
            basic_info = {
                "done": False,
                "ok": result.get("ok", False),
                "avoiding_count": result.get("avoiding_count", 0),
                "image_count": result.get("image_count", 0),
                "time_range": result.get("time_range", ""),
                "conclusion": result.get("conclusion", "")
            }
            self.wfile.write(f"data: {json.dumps(basic_info, ensure_ascii=True)}\n\n".encode('utf-8'))
            self.wfile.flush()

            # 发送图片列表
            if "images" in result:
                self.wfile.write(f"data: {json.dumps({'images': result['images']}, ensure_ascii=True)}\n\n".encode('utf-8'))
                self.wfile.flush()

            # 分批发送日志分类数据，每批最多100行
            if "categories" in result:
                for category_name, lines in result["categories"].items():
                    # 分批发送，每次最多100行
                    batch_size = 100
                    for i in range(0, len(lines), batch_size):
                        batch = lines[i:i+batch_size]
                        self.wfile.write(f"data: {json.dumps({'category': category_name, 'lines': batch, 'batch_index': i//batch_size}, ensure_ascii=True)}\n\n".encode('utf-8'))
                        self.wfile.flush()

            # 最后发送完成标记
            self.wfile.write(f"data: {json.dumps({'done': True}, ensure_ascii=True)}\n\n".encode('utf-8'))
            self.wfile.flush()
            return

        # ── ros2deploy routes ────────────────────────────────────────
        if path == "/ros2deploy/list_dir":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            dir_path = body.get("path", "")
            if not dir_path or not os.path.isdir(dir_path):
                self._json({"ok": False, "error": f"目录不存在: {dir_path}"})
                return
            files = _build_file_tree(dir_path)
            self._json({"ok": True, "files": files})
            return

        if path == "/ros2deploy/file_content":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            fpath = body.get("path", "")
            if not fpath or not os.path.isfile(fpath):
                self._json({"ok": False, "error": "文件不存在"})
                return
            try:
                size = os.path.getsize(fpath)
                if size > 512 * 1024:
                    self._json({"ok": False, "error": f"文件过大 ({size // 1024}KB)，不支持预览"})
                    return
                with open(fpath, "r", errors="replace") as f:
                    content = f.read()
                self._json({"ok": True, "content": content})
            except Exception as e:
                self._json({"ok": False, "error": str(e)})
            return

        if path == "/ros2deploy/docker_input":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            text = body.get("text", "")
            session = _docker_sessions.get('current')
            if session and text:
                import os as _os
                try:
                    _os.write(session['master_fd'], (text + '\n').encode())
                    self._json({"ok": True})
                except Exception as e:
                    self._json({"ok": False, "error": str(e)})
            else:
                self._json({"ok": False, "error": "no active docker session"})
            return

        if path == "/ros2deploy/exec":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            cmd = body.get("cmd", "")
            cwd = body.get("cwd") or None
            if not cmd:
                self._json({"ok": False, "error": "no cmd"})
                return
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=30, cwd=cwd
                )
                output = (result.stdout or "") + (result.stderr or "")
                self._json({"ok": True, "output": output})
            except subprocess.TimeoutExpired:
                self._json({"ok": False, "error": "命令超时"})
            except Exception as e:
                self._json({"ok": False, "error": str(e)})
            return

        self.send_response(404)
        self.end_headers()


def _build_file_tree(base_dir: str, max_depth: int = 4) -> list:
    """Build a flat list of FileEntry dicts for the given directory."""
    result = []
    base_dir = base_dir.rstrip("/")

    SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".cache", "build", "install", "log"}
    SKIP_EXTS = {".pyc", ".pyo", ".o", ".a", ".so", ".d"}

    def _walk(dir_path: str, depth: int):
        if depth > max_depth:
            return
        try:
            entries = sorted(os.scandir(dir_path), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                if entry.name in SKIP_DIRS:
                    continue
                result.append({"name": entry.name, "path": entry.path, "isDir": True, "depth": depth})
                _walk(entry.path, depth + 1)
            else:
                if os.path.splitext(entry.name)[1].lower() in SKIP_EXTS:
                    continue
                result.append({"name": entry.name, "path": entry.path, "isDir": False, "depth": depth})

    _walk(base_dir, 0)
    return result


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def main():
    server = ThreadingHTTPServer(("localhost", OFFLINE_SERVER_PORT), OfflineHandler)
    print(f"[offline-server] listening on http://localhost:{OFFLINE_SERVER_PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
