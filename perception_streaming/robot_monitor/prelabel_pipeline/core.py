from __future__ import annotations

import copy
import glob
import hashlib
import json
import os
import shlex
import subprocess
import threading
import time as _time_module
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count
from pathlib import Path
from typing import Any, Callable

import requests as _requests
import yaml

LogFn = Callable[[Any], None]

_cvat_session_cache: dict[str, dict[str, Any]] = {}
_cvat_session_lock = threading.Lock()

_CUDA_ERROR_KEYWORDS = [
    "No CUDA GPUs are available",
    "Failed to initialize NVML",
    "CUDA error",
    "cuda runtime error",
    "RuntimeError: CUDA",
    "torch._C._cuda_init",
]


def _get_cvat_server(config: dict, server_id: str | None = None) -> dict:
    servers = config.get("cvat_servers", [])
    if not servers:
        return config.get("cvat", {})
    if not server_id:
        return servers[0]
    for server in servers:
        if server.get("id") == server_id:
            return server
    return servers[0]


def _require_cvat_server(config: dict) -> dict:
    server = _get_cvat_server(config, config.get("_cvat_server_id"))
    missing = [key for key in ("host", "port", "user", "password") if not server.get(key)]
    if missing:
        raise ValueError(f"CVAT server config missing required fields: {', '.join(missing)}")
    return server


def _cvat_task_url(config: dict, task_id: int) -> str:
    server = _require_cvat_server(config)
    return f"http://{server['host']}:{server['port']}/tasks/{task_id}"


def clear_cvat_session_cache(server_id: str | None = None) -> None:
    with _cvat_session_lock:
        if server_id:
            _cvat_session_cache.pop(server_id, None)
        else:
            _cvat_session_cache.clear()


def _emit(log_fn: LogFn | None, event_fn: LogFn | None, item: Any) -> None:
    if callable(log_fn):
        log_fn(item)
    if callable(event_fn) and event_fn is not log_fn:
        if isinstance(item, dict):
            event_fn(item)
        else:
            event_fn({"type": "log", "msg": str(item)})


def _make_logger(log_fn: LogFn | None, event_fn: LogFn | None) -> LogFn:
    def emit(item: Any) -> None:
        _emit(log_fn, event_fn, item)

    return emit


def _validate_image(image_path: str) -> bool:
    try:
        if os.path.getsize(image_path) == 0:
            return False
        from PIL import Image

        with Image.open(image_path) as img:
            img.verify()
        return True
    except Exception:
        return False


def _filter_valid_images(image_paths: list[str]) -> list[str]:
    max_workers = min(cpu_count() * 2, 32)

    def process(path: str) -> tuple[str, bool]:
        if _validate_image(path):
            return path, True
        try:
            os.remove(path)
        except Exception:
            pass
        return path, False

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(process, image_paths))
    return [path for path, ok in results if ok]


def build_label_mapping(mapping_file: str | Path | None = None) -> dict:
    path = Path(mapping_file) if mapping_file else Path(__file__).resolve().parent / "labels_mapping.yaml"
    with path.open("r", encoding="utf-8") as f:
        mapping = yaml.safe_load(f)
    if not isinstance(mapping, dict):
        raise ValueError("labels mapping must be a mapping")
    return mapping


def build_cvat_labels(labels_csv: str) -> list[dict]:
    import pandas as pd

    colorboard = pd.read_csv(labels_csv, header=0).to_dict()
    labels = []
    for i in range(len(colorboard["id"])):
        is_crowd = str(colorboard["is_crowd"][i]).lower()
        labels.append({
            "name": colorboard["name"][i],
            "color": colorboard["color"][i],
            "attributes": [
                {
                    "name": "is_crowd",
                    "mutable": False,
                    "input_type": "checkbox",
                    "values": [is_crowd],
                    "default_value": is_crowd,
                },
                {
                    "name": "seg_pixel_value",
                    "mutable": False,
                    "input_type": "number",
                    "values": [str(i)],
                    "default_value": str(i),
                },
            ],
        })
    return labels


def convert_labels_in_xml(
    xml_path: str | Path,
    label_mapping: dict[str, str],
    output_path: str | Path | None = None,
) -> bool:
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        for labels_elem in root.findall(".//labels"):
            for label_elem in labels_elem.findall("label"):
                name_elem = label_elem.find("name")
                if name_elem is not None and name_elem.text in label_mapping:
                    name_elem.text = label_mapping[name_elem.text]

        for polygon in root.findall(".//polygon"):
            label = polygon.get("label")
            if label in label_mapping:
                polygon.set("label", label_mapping[label])

        target = output_path if output_path is not None else xml_path
        tree.write(target, encoding="utf-8", xml_declaration=True)
        return True
    except Exception:
        return False


def step1_upload(
    task_name: str,
    input_dir: str,
    config: dict,
    log_fn: LogFn,
    extra_image_files: list[str] | None = None,
) -> tuple[Any, int, int]:
    log_fn({"type": "step_start", "step": 1, "msg": f"开始上传目录: {input_dir}"})
    log_fn(f"[Step1] 开始上传目录: {input_dir}")

    labels_csv = config["labels_csv"]
    segment_size = config.get("segment_size", 1000)
    server = _require_cvat_server(config)

    extensions = ["*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff", "*.tif"]
    image_paths: list[str] = []
    for ext in extensions:
        image_paths.extend(glob.glob(os.path.join(input_dir, ext)))
        image_paths.extend(glob.glob(os.path.join(input_dir, ext.upper())))
    image_paths = sorted(image_paths)

    if extra_image_files:
        image_paths = list(dict.fromkeys(image_paths + extra_image_files))
        log_fn(f"[Step1] 额外追加 {len(extra_image_files)} 张上传图片")

    log_fn(f"[Step1] 找到 {len(image_paths)} 张图片")
    if not image_paths:
        raise ValueError(f"目录 {input_dir} 中没有找到图片文件")

    valid_images = _filter_valid_images(image_paths)
    log_fn(f"[Step1] 有效图片: {len(valid_images)} 张（删除 {len(image_paths) - len(valid_images)} 张损坏文件）")
    if not valid_images:
        raise ValueError(f"目录 {input_dir} 中没有有效图片")

    from cvat_sdk import make_client
    from cvat_sdk.api_client.exceptions import ApiException
    from cvat_sdk.core.proxies.tasks import ResourceType

    client = make_client(
        host=server["host"],
        port=server["port"],
        credentials=(server["user"], server["password"]),
    )
    labels = build_cvat_labels(labels_csv)
    task_specs = {"name": task_name, "labels": labels, "segment_size": segment_size}

    log_fn(f"[Step1] 创建 CVAT 任务: {task_name}")
    fallback_sizes = [500, 250, 125, 62, 50, 25, 10, 5, 3, 1]
    attempt_sequence = [segment_size] + [s for s in fallback_sizes if s < segment_size]
    last_error: Exception | None = None
    jobs = []

    for attempt_size in attempt_sequence:
        if attempt_size != segment_size:
            task_specs = {"name": task_name, "labels": labels, "segment_size": attempt_size}
            log_fn(f"[Step1] 重试 with segment_size={attempt_size}")
        try:
            task = client.tasks.create_from_data(
                spec=task_specs,
                resource_type=ResourceType.LOCAL,
                resources=valid_images,
            )
            log_fn(f"[Step1] 任务创建成功，task_id={task.id}，获取jobs...")
            try:
                task.fetch()
                jobs = task.get_jobs()
            except Exception as fetch_err:
                log_fn(f"[Step1] 获取jobs时出错: {fetch_err}")
                jobs = []
            if not jobs:
                raise RuntimeError("[Step1] CVAT 任务创建后没有jobs，数据上传可能失败。请检查 CVAT Web界面。")
            log_fn(f"[Step1] 任务验证成功，task_id={task.id}, jobs={len(jobs)}")
            break
        except ApiException as exc:
            last_error = exc
            error_parts = []
            if getattr(exc, "reason", None):
                error_parts.append(str(exc.reason))
            if getattr(exc, "body", None):
                error_parts.append(str(exc.body))
            error_parts.append(str(exc))
            error_msg = " | ".join(error_parts)
            status_val = getattr(exc, "status", None)
            reason_val = getattr(exc, "reason", None)
            reason_str = str(reason_val)[:200] if reason_val else "?"
            log_fn(f"[Step1] CVAT API异常: status={status_val}, reason={reason_str}")
            if status_val == 200:
                if "frames" in error_msg:
                    raise RuntimeError("[Step1] CVAT 任务创建失败：服务器返回200但数据损坏(frames=null)。请手动检查 CVAT 中的任务。")
                raise RuntimeError("[Step1] CVAT 任务创建失败：服务器返回异常。请检查 CVAT 日志。")
            if status_val and status_val >= 500 and "frames" in error_msg:
                log_fn(f"[Step1] CVAT server bug (segment_size={attempt_size}), frames=null, 将重试...")
                continue
            raise
    else:
        raise RuntimeError(f"[Step1] CVAT 任务创建失败 (IntegrityError): {last_error}")

    job_id = jobs[0].id
    log_fn(f"[Step1] job_id={job_id}")
    log_fn({"type": "step_done", "step": 1, "status": "success", "msg": f"task_id={task.id}, job_id={job_id}"})
    return client, task.id, job_id


def is_cuda_error(text: str | list[str] | tuple[str, ...]) -> bool:
    if isinstance(text, str):
        combined = text
    else:
        combined = "\n".join(str(line) for line in text)
    return any(keyword.lower() in combined.lower() for keyword in _CUDA_ERROR_KEYWORDS)


def diagnose_cuda_error(container: str, log_fn: LogFn) -> None:
    log_fn("[诊断] ── CUDA 异常诊断 ─────────────────")

    def run(cmd: list[str], timeout: int = 8) -> str:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return (result.stdout + result.stderr).strip()
        except Exception as exc:
            return f"(执行失败: {exc})"

    host_driver = run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"])
    log_fn(f"[诊断] 宿主机驱动版本: {host_driver}")
    ctr_driver = run([
        "docker",
        "exec",
        container,
        "nvidia-smi",
        "--query-gpu=driver_version",
        "--format=csv,noheader",
    ])
    log_fn(f"[诊断] 容器内驱动版本: {ctr_driver}")
    if host_driver and ctr_driver and host_driver != ctr_driver:
        log_fn(f"[诊断] 驱动版本不一致！宿主机={host_driver} vs 容器={ctr_driver}")
        log_fn("[诊断] 根因：宿主机驱动更新后未重启容器，重启容器即可修复")
    elif "执行失败" in ctr_driver or "Error" in ctr_driver:
        log_fn("[诊断] 容器内 nvidia-smi 无法运行，NVML 库可能失效")

    dev_files = run(["ls", "-la", "/dev/nvidia0", "/dev/nvidiactl", "/dev/nvidia-uvm"])
    log_fn(f"[诊断] 宿主机设备文件:\n{dev_files}")
    ctr_dev = run(["docker", "exec", container, "ls", "-la", "/dev/nvidia0", "/dev/nvidiactl"])
    log_fn(f"[诊断] 容器内设备文件:\n{ctr_dev}")
    kmod = run(["lsmod"])
    nvidia_mods = [line for line in kmod.splitlines() if "nvidia" in line.lower()]
    log_fn(f"[诊断] 内核 NVIDIA 模块: {nvidia_mods if nvidia_mods else '(未找到)'}")
    log_fn("[诊断] ────────────────────────────────────")
    log_fn("[诊断] 修复建议：重启容器；若重启后仍失败，检查宿主机 GPU 驱动和内核模块。")


def restart_docker_container(container: str, log_fn: LogFn, wait_seconds: int = 8) -> bool:
    log_fn(f"[Docker] 正在重启容器 {container}...")
    try:
        result = subprocess.run(["docker", "restart", container], capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            log_fn(f"[Docker] 重启失败: {result.stderr.strip()}")
            return False
        log_fn(f"[Docker] 容器已重启，等待 {wait_seconds}s 初始化...")
        _time_module.sleep(wait_seconds)
        check = subprocess.run(
            ["docker", "exec", container, "nvidia-smi", "-L"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if check.returncode == 0:
            gpu_info = check.stdout.strip().splitlines()[0] if check.stdout.strip() else "unknown"
            log_fn(f"[Docker] GPU 已就绪: {gpu_info}")
            return True
        log_fn(f"[Docker] GPU 验证失败: {check.stderr.strip()}")
        return False
    except subprocess.TimeoutExpired:
        log_fn("[Docker] 重启超时")
        return False
    except Exception as exc:
        log_fn(f"[Docker] 重启异常: {exc}")
        return False


def build_predict_cmd(
    input_dir: str,
    output_dir: str,
    label_id: int,
    config: dict,
    container_name: str | None = None,
) -> tuple[list[str], str]:
    demo_dir = config["demo_dir"]
    min_area = config.get("min_area", 50)
    smooth_contours = config.get("smooth_contours", True)
    fill_holes = config.get("fill_holes", True)
    docker_container = container_name or config.get("container") or "MPformer"

    demo_args = [
        "python",
        "demo_xml_1.py",
        "--config-file",
        config["config"],
        "--input",
        input_dir,
        "--output",
        output_dir,
        "--job-id",
        str(label_id),
        "--min-area",
        str(min_area),
    ]
    if smooth_contours:
        demo_args.append("--smooth-contours")
    if fill_holes:
        demo_args.append("--fill-holes")
    demo_args += ["--opts", "MODEL.WEIGHTS", config["weights"]]

    inner_cmd = shlex.join(demo_args)
    shell_cmd = f"cd {shlex.quote(demo_dir)} && {inner_cmd}"
    docker_cmd = ["docker", "exec", docker_container, "bash", "-c", shell_cmd]
    return docker_cmd, inner_cmd


def step2_predict(
    input_dir: str,
    output_dir: str,
    job_id: int,
    config: dict,
    log_fn: LogFn,
    cancel_fn: Callable[[], bool] | None = None,
    set_proc_fn: Callable[[subprocess.Popen], None] | None = None,
    clear_proc_fn: Callable[[], None] | None = None,
    params: dict | None = None,
) -> Path | None:
    log_fn({"type": "step_start", "step": 2, "msg": f"开始 AI 预标注，job_id={job_id}"})
    log_fn(f"[Step2] 开始 AI 预标注，job_id={job_id}")

    model_cfg = config["model"]
    docker_container = config["docker"]["container"]
    demo_dir = model_cfg["demo_dir"]
    max_attempts = 2

    docker_cmd, inner_cmd = build_predict_cmd(input_dir, output_dir, job_id, model_cfg, docker_container)
    log_fn(f"[Step2] 执行命令: {' '.join(shlex.quote(part) for part in docker_cmd)}")

    gpu_sem = params.get("gpu_semaphore") if params else None
    gpu_acquired = False
    if gpu_sem is not None:
        log_fn("[Step2] 等待 GPU 资源（当前有其他任务占用）...")
        while not gpu_sem.acquire(timeout=0.2):
            if cancel_fn and cancel_fn():
                log_fn("[Step2] 等待 GPU 时任务被取消")
                return None
        gpu_acquired = True
        log_fn("[Step2] 获得 GPU，开始推理...")

    try:
        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                log_fn(f"[Step2] 第 {attempt} 次尝试...")

            output_lines: list[str] = []
            proc = subprocess.Popen(
                docker_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            if set_proc_fn:
                set_proc_fn(proc)

            cancelled = False
            stdout = proc.stdout or []
            for line in stdout:
                if cancel_fn and cancel_fn():
                    proc.kill()
                    cancelled = True
                    break
                line = line.rstrip()
                if line:
                    output_lines.append(line)
                    log_fn(f"[Step2] {line}")

            proc.wait()
            if clear_proc_fn:
                clear_proc_fn()

            if cancelled or (cancel_fn and cancel_fn()):
                raise RuntimeError("用户已取消")
            if proc.returncode == 0:
                break
            if is_cuda_error(output_lines):
                log_fn("[Step2] 检测到 CUDA 异常！自动诊断中...")
                diagnose_cuda_error(docker_container, log_fn)
                if attempt < max_attempts:
                    if restart_docker_container(docker_container, log_fn):
                        log_fn("[Step2] 容器重启完成，自动重试推理...")
                        continue
                    raise RuntimeError("CUDA 异常且容器重启失败，请手动检查 Docker 和 GPU 驱动")
                raise RuntimeError("CUDA 异常，重启容器后重试仍失败，请手动检查 GPU 驱动")
            raise RuntimeError(f"demo_xml_1.py 执行失败，返回码: {proc.returncode}")

        xml_path = Path(output_dir) / "annotations.xml"
        if not xml_path.exists():
            raise FileNotFoundError(f"预标注结果不存在: {xml_path}")
        log_fn(f"[Step2] 预标注完成: {xml_path}")
        log_fn({"type": "step_done", "step": 2, "status": "success", "msg": f"预标注完成: {xml_path}"})
        return xml_path
    finally:
        if gpu_acquired:
            gpu_sem.release()
            log_fn("[Step2] GPU 资源已释放")


def step3_rename(xml_path: str | Path, config: dict, log_fn: LogFn) -> Path:
    xml_path = Path(xml_path)
    log_fn({"type": "step_start", "step": 3, "msg": f"开始标签转换: {xml_path}"})
    log_fn(f"[Step3] 开始标签转换: {xml_path}")
    label_mapping = build_label_mapping()
    output_path = xml_path.parent / "annotations_cvat.xml"
    if not convert_labels_in_xml(xml_path, label_mapping, output_path):
        raise RuntimeError("标签转换失败")
    log_fn(f"[Step3] 标签转换完成: {output_path}")
    log_fn({"type": "step_done", "step": 3, "status": "success", "msg": f"标签转换完成: {output_path}"})
    return output_path


def step4_import(client: Any, task_id: int, xml_path: str | Path, config: dict, log_fn: LogFn) -> str:
    log_fn({"type": "step_start", "step": 4, "msg": f"开始导入标注到 task_id={task_id}"})
    log_fn(f"[Step4] 开始导入标注到 task_id={task_id}")
    task = client.tasks.retrieve(task_id)
    task.import_annotations("CVAT 1.1", str(xml_path))
    task_url = _cvat_task_url(config, task_id)
    log_fn(f"[Step4] 导入完成，CVAT 任务: {task_url}")
    log_fn({"type": "step_done", "step": 4, "status": "success", "msg": f"导入完成，CVAT 任务: {task_url}"})
    return task_url


def cvat_session(cvat_server: dict) -> tuple[_requests.Session, str]:
    server_id = cvat_server.get("id", "default")
    now = _time_module.time()
    cache = _cvat_session_cache.get(server_id)
    if cache and now < cache["expires"]:
        return cache["session"], cache["base"]

    with _cvat_session_lock:
        cache = _cvat_session_cache.get(server_id)
        if cache and now < cache["expires"]:
            return cache["session"], cache["base"]

        base = f"http://{cvat_server['host']}:{cvat_server['port']}"
        session = _requests.Session()
        session.trust_env = False
        login = session.post(
            f"{base}/api/auth/login",
            json={"username": cvat_server["user"], "password": cvat_server["password"]},
            timeout=10,
        )
        login.raise_for_status()
        token = login.json()["key"]
        session.headers.update({"Authorization": f"Token {token}", "Content-Type": "application/json"})

        _cvat_session_cache[server_id] = {"session": session, "base": base, "expires": now + 1800}
        return session, base


def list_cvat_users(config: dict, server_id: str | None = None) -> list[dict]:
    cfg = config
    if server_id is not None:
        cfg = copy.deepcopy(config)
        cfg["_cvat_server_id"] = server_id
    server = _require_cvat_server(cfg)
    session, base = cvat_session(server)
    response = session.get(f"{base}/api/users?page_size=100", timeout=10)
    response.raise_for_status()
    results = response.json().get("results", [])
    return [
        {
            "id": user["id"],
            "username": user["username"],
            "full_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
        }
        for user in results
    ]


def step5_assign(task_id: int, assignee_id: int, config: dict, log_fn: LogFn) -> None:
    log_fn({"type": "step_start", "step": 5, "msg": f"分配任务 task_id={task_id} -> assignee_id={assignee_id}"})
    log_fn(f"[Step5] 分配任务 task_id={task_id} -> assignee_id={assignee_id}")

    server = _require_cvat_server(config)
    session, base = cvat_session(server)
    response = session.patch(f"{base}/api/tasks/{task_id}", json={"assignee_id": assignee_id}, timeout=10)
    response.raise_for_status()
    assignee_info = response.json().get("assignee") or {}
    username = assignee_info.get("username", str(assignee_id))
    log_fn(f"[Step5] Task 已分配给: {username}")

    jobs_response = session.get(f"{base}/api/jobs?task_id={task_id}&page_size=100", timeout=10)
    jobs_response.raise_for_status()
    jobs = jobs_response.json().get("results", [])
    for job in jobs:
        job_response = session.patch(f"{base}/api/jobs/{job['id']}", json={"assignee": assignee_id}, timeout=10)
        job_response.raise_for_status()
        log_fn(f"[Step5] Job {job['id']} 已分配给: {username}")

    log_fn(f"[Step5] 分配完成，共分配 {len(jobs)} 个 job")
    log_fn({"type": "step_done", "step": 5, "status": "success", "msg": f"分配完成，共分配 {len(jobs)} 个 job"})


def _cancel_fn_from_params(params: dict) -> Callable[[], bool]:
    provided = params.get("cancel_fn")
    cancel_event = params.get("cancel_event")

    def cancelled() -> bool:
        if callable(provided) and provided():
            return True
        return bool(cancel_event and cancel_event.is_set())

    return cancelled


def _callback_from_params(params: dict, key: str, arity: int) -> Callable:
    candidate = params.get(key)
    if callable(candidate):
        return candidate
    if arity == 1:
        return lambda _value: None
    return lambda: None


def _apply_runtime_overrides(config: dict, params: dict) -> dict:
    cfg = copy.deepcopy(config)
    if "min_area" in params:
        cfg.setdefault("model", {})["min_area"] = int(params["min_area"])
    if "segment_size" in params:
        cfg["segment_size"] = int(params["segment_size"])
    if "cvat_server_id" in params:
        cfg["_cvat_server_id"] = params["cvat_server_id"]
    return cfg


def _skip_steps_from_params(params: dict) -> set[int]:
    raw_steps = params.get("skip_steps", [])
    if raw_steps is None:
        values: list[Any] = []
    elif isinstance(raw_steps, (str, bytes)):
        values = [part.strip() for part in raw_steps.decode().split(",")] if isinstance(raw_steps, bytes) else [
            part.strip() for part in raw_steps.split(",")
        ]
    elif isinstance(raw_steps, int):
        values = [raw_steps]
    else:
        try:
            values = list(raw_steps)
        except TypeError:
            values = []

    skip_steps: set[int] = set()
    for step in values:
        if step in ("", None):
            continue
        try:
            step_int = int(step)
        except (TypeError, ValueError):
            continue
        if 1 <= step_int <= 5:
            skip_steps.add(step_int)
    if params.get("upload_only"):
        skip_steps.update({2, 3, 4})
    return skip_steps


def run_pipeline(
    run_id: str,
    task_prefix: str,
    input_dirs: list[str],
    params: dict,
    config: dict,
    log_fn: LogFn | None,
) -> list[dict]:
    cfg = _apply_runtime_overrides(config, params)
    event_fn = params.get("event_fn") or params.get("event_callback")
    emit = _make_logger(log_fn, event_fn)
    skip_steps = _skip_steps_from_params(params)
    assignee_id = params.get("assignee_id")
    has_assign = assignee_id is not None
    cancel_fn = _cancel_fn_from_params(params)
    set_proc_fn = _callback_from_params(params, "set_proc_fn", 1)
    clear_proc_fn = _callback_from_params(params, "clear_proc_fn", 0)
    extra_image_files = params.get("extra_image_files")

    results: list[dict] = []
    total = len(input_dirs)

    for idx, input_dir in enumerate(input_dirs, 1):
        if cancel_fn():
            emit(f"已取消，跳过剩余 {total - idx + 1} 个目录")
            break

        dir_name = Path(input_dir).name
        task_name = f"{task_prefix}_{dir_name}"
        emit(f"\n{'=' * 50}")
        emit(f"处理目录 {idx}/{total}: {input_dir}")
        emit(f"CVAT 任务名: {task_name}")
        emit(f"{'=' * 50}")

        result = {
            "input_dir": input_dir,
            "task_name": task_name,
            "task_id": None,
            "job_id": None,
            "cvat_url": None,
            "status": "running",
            "failed_step": None,
            "error": None,
        }

        current_step = 0
        try:
            current_step = 1
            emit("[进度] 80%" if {2, 3, 4}.issubset(skip_steps) else "[进度] 20%")
            client, task_id, job_id = step1_upload(task_name, input_dir, cfg, emit, extra_image_files=extra_image_files)
            result["task_id"] = task_id
            result["job_id"] = job_id

            if 2 not in skip_steps:
                output_base = cfg["output_base"]
                output_dir = os.path.join(output_base, dir_name)
                os.makedirs(output_dir, exist_ok=True)

                current_step = 2
                emit("[进度] 40%")
                xml_path = step2_predict(
                    input_dir,
                    output_dir,
                    job_id,
                    cfg,
                    emit,
                    cancel_fn=cancel_fn,
                    set_proc_fn=set_proc_fn,
                    clear_proc_fn=clear_proc_fn,
                    params=params,
                )
                if xml_path is None:
                    raise RuntimeError("用户已取消")

                current_step = 3
                emit("[进度] 60%")
                cvat_xml_path = step3_rename(xml_path, cfg, emit)

                current_step = 4
                emit("[进度] 80%")
                cvat_url = step4_import(client, task_id, cvat_xml_path, cfg, emit)
                result["cvat_url"] = cvat_url
            else:
                skip_labels = {2: "AI 预标注", 3: "标签转换", 4: "导入标注"}
                for step in (2, 3, 4):
                    emit({"type": "step_skip", "step": step, "msg": f"已跳过{skip_labels[step]}"})
                    emit(f"[Step{step}] 已跳过")
                cvat_url = _cvat_task_url(cfg, task_id)
                result["cvat_url"] = cvat_url

            if has_assign:
                current_step = 5
                emit("[进度] 95%")
                step5_assign(task_id, int(assignee_id), cfg, emit)

            emit("[进度] 100%")
            result["status"] = "success"
            emit(f"目录 {dir_name} 处理完成！CVAT: {result['cvat_url']}")
        except Exception as exc:
            result["status"] = "cancelled" if cancel_fn() else "failed"
            result["failed_step"] = current_step or None
            result["error"] = str(exc)
            if current_step > 0:
                emit({"type": "step_done", "step": current_step, "status": "failed", "msg": str(exc)})
            emit(f"目录 {dir_name} 处理失败: {exc}")

        results.append(result)

    success_count = sum(1 for record in results if record["status"] == "success")
    if cancel_fn() and success_count < total:
        overall_status = "cancelled"
    elif success_count == total:
        overall_status = "success"
    elif success_count > 0:
        overall_status = "partial"
    else:
        overall_status = "failed"
    emit({
        "type": "pipeline_done",
        "status": overall_status,
        "dir_count": total,
        "success_count": success_count,
        "msg": f"流水线完成，共 {total} 个目录，成功 {success_count} 个",
    })
    emit(f"\n流水线完成，共 {total} 个目录，成功 {success_count} 个")
    return results


run_prelabel_pipeline = run_pipeline


# Shadow A/B runs intentionally do not reuse ``run_pipeline``: the legacy path
# imports immediately after upload, while the shadow contract must attest CVAT's
# real frames (including bytes) before an import can occur.
def _shadow_call(adapter: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Call narrow test/deployment adapters without imposing one SDK signature."""
    try:
        return adapter(*args, **kwargs)
    except TypeError:
        return adapter(*args)


def _shadow_manifest(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    files = snapshot.get("files")
    if not isinstance(files, list):
        try:
            files = json.loads((Path(snapshot["snapshot_path"]) / "manifest.json").read_text(encoding="utf-8"))["files"]
        except (KeyError, OSError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("shadow snapshot manifest is required") from exc
    if not files:
        raise ValueError("shadow snapshot contains no images")
    return copy.deepcopy(files)


def _shadow_task_id(task: Any) -> int | None:
    value = task.get("id") if isinstance(task, dict) else getattr(task, "id", None)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _shadow_frame_outcomes(files: list[dict[str, Any]], frames: list[Any], frame_bytes: Callable[..., Any], task: Any) -> tuple[list[dict[str, Any]], bool]:
    """Attest CVAT frame identity and raw bytes against the frozen snapshot."""
    outcomes: list[dict[str, Any]] = []
    valid = len(frames) == len(files)
    for index, source in enumerate(files):
        frame = frames[index] if index < len(frames) else {}
        info = frame if isinstance(frame, dict) else vars(frame)
        frame_id = info.get("id")
        raw = _shadow_call(frame_bytes, task, frame_id, frame=frame)
        if not isinstance(raw, bytes):
            raw = bytes(raw)
        dimensions = {"width": info.get("width"), "height": info.get("height")}
        expected_dims = source.get("normalized_dimensions") or source.get("original_dimensions") or {}
        actual_hash = hashlib.sha256(raw).hexdigest()
        ok = (
            isinstance(frame_id, int)
            and info.get("name") == source.get("path")
            and dimensions == expected_dims
            and actual_hash == source.get("sha256")
        )
        outcomes.append({"path": source.get("path"), "sha256": actual_hash, "dimensions": dimensions, "frame_id": frame_id, "status": "success" if ok else "failed"})
        valid = valid and ok
    return outcomes, valid


def build_shadow_adapters(config: dict, *, client_factory: Callable[[], Any] | None = None) -> dict[str, Callable[..., Any]]:
    """Production CVAT boundary used by the route (tests can inject this factory).

    Frame bytes are fetched from CVAT's data endpoint rather than trusting local
    upload paths.  That is the only meaningful attestation of what CVAT received.
    """
    server = _require_cvat_server(config)
    client_box: dict[str, Any] = {}
    def client() -> Any:
        if "client" not in client_box:
            if client_factory:
                client_box["client"] = client_factory()
            else:
                from cvat_sdk import make_client
                client_box["client"] = make_client(host=server["host"], port=server["port"], credentials=(server["user"], server["password"]))
        return client_box["client"]
    def create(branch: str, task_prefix: str, _input: str | Path, **_kwargs: Any) -> Any:
        labels = build_cvat_labels(config["labels_csv"])
        return client().tasks.create({"name": f"{task_prefix}_{branch}", "labels": labels, "segment_size": config.get("segment_size", 1000)})
    def upload(task: Any, input_dir: str | Path) -> None:
        paths = sorted(str(path) for path in Path(input_dir).rglob("*") if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"})
        if not paths:
            raise ValueError("shadow branch has no images")
        task.upload_data(resources=paths)
        task.fetch()
    def frames(task: Any) -> list[dict[str, Any]]:
        session, base = cvat_session(server)
        response = session.get(f"{base}/api/tasks/{task.id}/data/meta", timeout=30)
        response.raise_for_status()
        data = response.json()
        raw = data.get("frames", []) if isinstance(data, dict) else []
        return [{"id": index, "name": item.get("name"), "width": item.get("width"), "height": item.get("height")} for index, item in enumerate(raw)]
    def frame_bytes(task: Any, frame_id: int, **_kwargs: Any) -> bytes:
        session, base = cvat_session(server)
        response = session.get(f"{base}/api/tasks/{task.id}/data", params={"number": frame_id, "quality": "original"}, timeout=60)
        response.raise_for_status()
        return response.content
    def importer(task: Any, xml: Any) -> Any:
        path = Path(xml)
        task.import_annotations("CVAT 1.1", str(path))
        return _cvat_task_url(config, task.id)
    def cleanup(task_id: int) -> Any:
        return client().tasks.delete(task_id)
    def baseline(input_dir: str | Path, task: Any, _snapshot: dict) -> Path:
        jobs = task.get_jobs()
        if not jobs:
            raise RuntimeError("baseline CVAT task has no job")
        output = Path(config["output_base"]) / f"shadow-{task.id}-A"
        output.mkdir(parents=True, exist_ok=True)
        xml = step2_predict(str(input_dir), str(output), jobs[0].id, config, lambda _item: None)
        if xml is None:
            raise RuntimeError("baseline inference cancelled")
        return step3_rename(xml, config, lambda _item: None)
    alpha_runner = config.get("alpha50_runner")
    def alpha50(input_dir: str | Path, task: Any, snapshot: dict) -> Any:
        if not callable(alpha_runner):
            raise RuntimeError("Alpha50 production runner is not configured")
        return alpha_runner(input_dir, task, snapshot)
    return {"create_task": create, "upload": upload, "frames": frames, "frame_bytes": frame_bytes, "import": importer, "cleanup": cleanup, "baseline": baseline, "alpha50": alpha50}


def run_shadow_pipeline(run_id: str, task_prefix: str, input_dirs: list[str], params: dict, config: dict, log_fn: LogFn | None) -> dict[str, Any]:
    """Run isolated baseline/candidate branches from one frozen upload snapshot.

    All external effects are explicit adapters.  This makes recovery safe: callers
    persist the returned record and may retry only a branch whose status is failed.
    """
    from .shadow_batch import freeze_batch, materialize_branch_input
    from .run_state import shadow_idempotency_key

    adapters = params.get("shadow_adapters") or {}
    if not isinstance(adapters, dict):
        raise ValueError("shadow_adapters are required")
    snapshot = params.get("shadow_snapshot")
    if not isinstance(snapshot, dict):
        if len(input_dirs) != 1:
            raise ValueError("shadow run requires exactly one input directory")
        freezer = adapters.get("freeze_batch", freeze_batch)
        snapshot = _shadow_call(freezer, input_dirs[0], config.get("shadow_snapshot_root") or Path(config.get("shadow_root", ".")) / "snapshots")
    files = _shadow_manifest(snapshot)
    snapshot_hash = snapshot.get("snapshot_hash")
    batch_id = snapshot.get("batch_id")
    if not isinstance(batch_id, str) or not isinstance(snapshot_hash, str):
        raise ValueError("shadow snapshot identity is required")
    state = {"run_id": run_id, "batch_id": batch_id, "snapshot_hash": snapshot_hash, "branches": {}, "common_success": []}
    retry_branch = params.get("retry_branch")
    if retry_branch not in (None, "A", "B"):
        raise ValueError("retry_branch must be A or B")
    gpu_queue = params.get("gpu_semaphore")
    materializer = adapters.get("materialize_branch_input", materialize_branch_input)
    cleanup = adapters.get("cleanup")
    if not callable(cleanup):
        raise ValueError("shadow cleanup adapter is required")
    checkpoint = params.get("shadow_checkpoint")
    cancel_fn = params.get("cancel_fn") if callable(params.get("cancel_fn")) else (lambda: False)
    def persist() -> None:
        if callable(checkpoint):
            _shadow_call(checkpoint, copy.deepcopy(state))
    for branch in ("A", "B"):
        if cancel_fn():
            state["branches"][branch] = {"branch_id": branch, "status": "cancelled", "cleanup": {"status": "not_needed"}}
            state["status"] = "cancelled"
            persist()
            break
        previous = (params.get("shadow_state") or {}).get("branches", {}).get(branch, {})
        if retry_branch and branch != retry_branch:
            state["branches"][branch] = copy.deepcopy(previous)
            continue
        if retry_branch == branch and previous.get("status") != "failed":
            raise ValueError("only an explicitly failed branch may be retried")
        key = shadow_idempotency_key(batch_id, branch, snapshot_hash)
        provenance = {"batch_id": batch_id, "branch_id": branch, "snapshot_hash": snapshot_hash}
        if branch == "B" and isinstance(params.get("candidate_config"), dict):
            candidate_config = copy.deepcopy(params["candidate_config"])
            provenance["candidate_config"] = candidate_config
            provenance["candidate_config_sha256"] = hashlib.sha256(json.dumps(candidate_config, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        record = {"branch_id": branch, "idempotency_key": key, "status": "running", "provenance": provenance}
        state["branches"][branch] = record
        persist()
        task = None
        try:
            branch_input = _shadow_call(materializer, snapshot, branch, config.get("shadow_work_root") or Path(config.get("shadow_root", ".")) / "work")
            record["input_path"] = str(branch_input)
            persist()
            if branch == "B" and callable(adapters.get("candidate_preflight")):
                _shadow_call(adapters["candidate_preflight"], branch_input, snapshot, record)
                record["preflight"] = "passed"
                persist()
            create = adapters.get("create_task")
            if not callable(create):
                raise ValueError("shadow create_task adapter is required")
            task = _shadow_call(create, branch, task_prefix, branch_input, idempotency_key=key, snapshot_hash=snapshot_hash)
            record["task_id"] = _shadow_task_id(task)
            if record["task_id"] is None:
                raise ValueError("shadow CVAT task id is invalid")
            persist()
            upload = adapters.get("upload")
            frames_fn, bytes_fn = adapters.get("frames"), adapters.get("frame_bytes")
            if not all(callable(fn) for fn in (upload, frames_fn, bytes_fn)):
                raise ValueError("shadow upload/frame adapters are required")
            _shadow_call(upload, task, branch_input)
            record["upload_status"] = "success"
            persist()
            frames = _shadow_call(frames_fn, task)
            record["images"], valid = _shadow_frame_outcomes(files, list(frames), bytes_fn, task)
            record["attestation_status"] = "success" if valid else "failed"
            persist()
            if not valid:
                raise ValueError("frame verification failed; import blocked")
            if cancel_fn():
                raise RuntimeError("shadow run cancelled")
            runner = adapters.get("baseline" if branch == "A" else "alpha50")
            if not callable(runner):
                raise ValueError(f"shadow {branch} inference adapter is required")
            # Both model paths contend for the same GPU; the queue is deliberately
            # held only around inference, never around CVAT/network side effects.
            if gpu_queue is not None:
                gpu_queue.acquire()
                try:
                    xml = _shadow_call(runner, branch_input, task, snapshot)
                finally:
                    gpu_queue.release()
            else:
                xml = _shadow_call(runner, branch_input, task, snapshot)
            if branch == "B" and callable(adapters.get("validate_candidate_xml")):
                _shadow_call(adapters["validate_candidate_xml"], xml, files, task)
            if cancel_fn():
                raise RuntimeError("shadow run cancelled")
            importer = adapters.get("import")
            if not callable(importer):
                raise ValueError("shadow import adapter is required")
            record["import_result"] = _shadow_call(importer, task, xml)
            record["import_status"] = "success"
            record["status"] = "success"
            persist()
        except Exception as exc:
            record["status"] = "cancelled" if cancel_fn() else "failed"
            record["error"] = str(exc)
            record["cleanup"] = {"status": "needed", "task_id": record.get("task_id")}
            if callable(cleanup) and record.get("task_id"):
                try:
                    record["cleanup"] = {"status": "attempted", "result": _shadow_call(cleanup, record["task_id"])}
                except Exception as cleanup_exc:
                    record["cleanup"] = {"status": "failed", "error": str(cleanup_exc), "task_id": record.get("task_id")}
            persist()
    successful = [set(item["path"] for item in state["branches"][name].get("images", []) if item.get("status") == "success") for name in ("A", "B") if state["branches"].get(name, {}).get("status") == "success"]
    state["common_success"] = sorted(set.intersection(*successful)) if len(successful) == 2 else []
    state["status"] = "success" if len(successful) == 2 else ("cancelled" if cancel_fn() else "failed")
    if len(successful) == 2:
        state["common_success_manifest"] = {"immutable": True, "images": [{"path": path, "branches": {name: next(item for item in state["branches"][name]["images"] if item["path"] == path) for name in ("A", "B")}} for path in state["common_success"]]}
        state["review_ready"] = True
    else:
        state["review_ready"] = False
    persist()
    return state
