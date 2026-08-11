from __future__ import annotations

import copy
import json
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .path_utils import validate_run_id

STREAMING_DIR = Path(__file__).resolve().parents[2]
RUNS_DIR = STREAMING_DIR / "data" / "prelabel_runs"
UPLOADS_DIR = STREAMING_DIR / "data" / "prelabel_uploads"
UPLOAD_META_NAME = ".upload_meta.json"
SHADOW_INDEX_NAME = "shadow_snapshot_index.json"
TERMINAL_STATUSES = {"success", "failed", "cancelled"}
INTERRUPTED_RESTART_MSG = "服务重启，运行中任务已中断"

runs: dict = {}
runs_lock = threading.RLock()


def shadow_idempotency_key(batch_id: str, branch_id: str, snapshot_hash: str) -> str:
    """The complete durable identity for one shadow branch side effect."""
    if not all(isinstance(value, str) and value for value in (batch_id, branch_id, snapshot_hash)):
        raise ValueError("shadow idempotency identity is required")
    return f"{batch_id}:{branch_id}:{snapshot_hash}"


def shadow_index_path(runs_dir: str | Path = RUNS_DIR) -> Path:
    return Path(runs_dir) / SHADOW_INDEX_NAME


def load_shadow_index(runs_dir: str | Path = RUNS_DIR) -> dict[str, dict]:
    try:
        data = json.loads(shadow_index_path(runs_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def update_shadow_index(run_id: str, run_data: dict, runs_dir: str | Path = RUNS_DIR) -> None:
    shadow = run_data.get("shadow")
    if not isinstance(shadow, dict) or not shadow.get("batch_id") or not shadow.get("snapshot_hash"):
        return
    owner = run_data.get("owner_token", "")
    key = f"{owner}:{shadow['batch_id']}:{shadow['snapshot_hash']}"
    index = load_shadow_index(runs_dir)
    index[key] = {"run_id": run_id, "owner_token": owner, "batch_id": shadow["batch_id"], "snapshot_hash": shadow["snapshot_hash"], "status": run_data.get("status"), "branches": copy.deepcopy(shadow.get("branches", {})), "updated_at": datetime.now().isoformat(timespec="seconds")}
    path = shadow_index_path(runs_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def make_runtime_run(
    task_prefix: str,
    input_dirs: list[str] | tuple[str, ...],
    owner_token: str = "",
    skip_steps: list[int] | tuple[int, ...] | None = None,
    upload_dir: str | Path | None = None,
    created_at: str | None = None,
    shadow: dict[str, Any] | None = None,
) -> dict:
    record = {
        "status": "running",
        "task_prefix": task_prefix,
        "input_dirs": [str(d) for d in input_dirs],
        "created_at": created_at or datetime.now().isoformat(timespec="seconds"),
        "finished_at": None,
        "logs": [],
        "result": None,
        "owner_token": owner_token or "",
        "event": threading.Event(),
        "done": False,
        "cancel": False,
        "proc": None,
        "skip_steps": list(skip_steps or []),
    }
    if upload_dir is not None:
        record["upload_dir"] = str(upload_dir)
    if shadow is not None:
        record["shadow"] = copy.deepcopy(shadow)
    return record


def serialize_run(
    run_id: str,
    run_data: dict,
    expose_paths: bool = True,
    include_logs: bool = False,
    owner_token: str = "",
) -> dict:
    input_dirs = list(run_data.get("input_dirs", []))
    if not expose_paths:
        input_dirs = [Path(d).name for d in input_dirs]
    record = {
        "run_id": run_id,
        "status": run_data["status"],
        "task_prefix": run_data["task_prefix"],
        "input_dirs": input_dirs,
        "created_at": run_data["created_at"],
        "finished_at": run_data.get("finished_at"),
        "result": run_data.get("result"),
        "owned_by_client": bool(owner_token and owner_token == run_data.get("owner_token", "")),
    }
    if include_logs:
        record["logs"] = run_data.get("logs", [])
    return record


def run_json_path(runs_dir: str | Path, run_id: str) -> Path:
    return Path(runs_dir) / f"{validate_run_id(run_id)}.json"


def _disk_record(run_id: str, run_data: dict) -> dict:
    record = serialize_run(run_id, run_data, expose_paths=True, include_logs=True)
    record.pop("owned_by_client", None)
    record["input_dirs"] = copy.deepcopy(record.get("input_dirs", []))
    record["logs"] = copy.deepcopy(record.get("logs", []))
    record["result"] = copy.deepcopy(record.get("result"))
    record["owner_token"] = run_data.get("owner_token", "")
    if "skip_steps" in run_data:
        record["skip_steps"] = copy.deepcopy(run_data.get("skip_steps", []))
    if "upload_dir" in run_data:
        record["upload_dir"] = run_data.get("upload_dir")
    if isinstance(run_data.get("shadow"), dict):
        record["shadow"] = copy.deepcopy(run_data["shadow"])
    return record


def save_run(run_id: str, runs_dir: str | Path = RUNS_DIR) -> None:
    path = run_json_path(runs_dir, run_id)
    with runs_lock:
        run = runs.get(run_id)
        if not run:
            return
        record = _disk_record(run_id, run)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    update_shadow_index(run_id, run, runs_dir)
    cleanup_old_runs(runs_dir)
    cleanup_old_runs_in_memory()


def load_history(runs_dir: str | Path = RUNS_DIR) -> list[dict]:
    target_dir = Path(runs_dir)
    records: list[dict] = []
    if not target_dir.exists():
        return records
    for path, _mtime in _json_files_by_mtime(target_dir):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            records.append(data)
    return records


def _json_files_by_mtime(directory: Path) -> list[tuple[Path, float]]:
    files = []
    for path in directory.glob("*.json"):
        try:
            files.append((path, path.stat().st_mtime))
        except OSError:
            continue
    return sorted(files, key=lambda item: item[1], reverse=True)


def _string_field(record: dict, key: str) -> str:
    value = record.get(key, "")
    return value if isinstance(value, str) else ""


def _list_field(record: dict, key: str) -> list:
    value = record.get(key, [])
    return copy.deepcopy(value) if isinstance(value, list) else []


def _result_field(record: dict) -> Any:
    result = record.get("result")
    if result is None or isinstance(result, (dict, list)):
        return copy.deepcopy(result)
    return {"value": copy.deepcopy(result)}


def _restore_history_record(record: dict) -> dict:
    status = record.get("status", "success")
    if status not in TERMINAL_STATUSES:
        status = "failed"
        interrupted = True
    else:
        interrupted = False

    finished_at = _string_field(record, "finished_at")
    logs = _list_field(record, "logs")
    result = _result_field(record)
    if interrupted:
        finished_at = finished_at or datetime.now().isoformat(timespec="seconds")
        if not isinstance(result, dict):
            result = {}
        result.setdefault("error", INTERRUPTED_RESTART_MSG)
        logs.append({"type": "log", "level": "error", "msg": INTERRUPTED_RESTART_MSG})

    event = threading.Event()
    event.set()
    restored = {
        "status": status,
        "task_prefix": _string_field(record, "task_prefix"),
        "input_dirs": _list_field(record, "input_dirs"),
        "created_at": _string_field(record, "created_at"),
        "finished_at": finished_at,
        "logs": logs,
        "result": result,
        "owner_token": _string_field(record, "owner_token"),
        "skip_steps": _list_field(record, "skip_steps"),
        "upload_dir": _string_field(record, "upload_dir"),
        "event": event,
        "done": True,
        "cancel": False,
        "proc": None,
    }
    if isinstance(record.get("shadow"), dict):
        restored["shadow"] = copy.deepcopy(record["shadow"])
        if interrupted:
            # Recovery never creates/retries tasks.  It preserves enough durable
            # information for an explicit operator cleanup/retry action.
            for branch in restored["shadow"].get("branches", {}).values():
                if isinstance(branch, dict) and branch.get("task_id"):
                    branch.setdefault("cleanup", {"status": "needed", "task_id": branch["task_id"], "reason": "service_recovery"})
    return restored


def init_runs_from_history(runs_dir: str | Path = RUNS_DIR) -> None:
    restored: dict[str, dict[str, Any]] = {}
    for record in load_history(runs_dir):
        run_id = record.get("run_id")
        try:
            validate_run_id(run_id)
        except (TypeError, ValueError):
            continue
        restored[run_id] = _restore_history_record(record)
    with runs_lock:
        runs.update(restored)


def cleanup_old_runs(
    runs_dir: str | Path = RUNS_DIR,
    max_days: int = 30,
    max_count: int = 100,
) -> None:
    target_dir = Path(runs_dir)
    if not target_dir.exists():
        return
    files = _json_files_by_mtime(target_dir)
    cutoff = time.time() - max_days * 86400
    for index, (path, mtime) in enumerate(files):
        old_by_count = index >= max_count
        old_by_age = mtime < cutoff
        if old_by_count or old_by_age:
            path.unlink(missing_ok=True)


def cleanup_old_runs_in_memory(max_age_seconds: int = 3600) -> None:
    now = time.time()
    with runs_lock:
        expired = []
        for run_id, run in list(runs.items()):
            if not run.get("done") or not run.get("finished_at"):
                continue
            try:
                finished_at = datetime.fromisoformat(run["finished_at"]).timestamp()
            except (TypeError, ValueError):
                continue
            if now - finished_at > max_age_seconds:
                expired.append(run_id)
        for run_id in expired:
            runs.pop(run_id, None)


def cleanup_old_uploads(
    uploads_dir: str | Path = UPLOADS_DIR,
    max_age_seconds: int = 86400,
) -> None:
    target_dir = Path(uploads_dir)
    if not target_dir.exists():
        return
    cutoff = time.time() - max_age_seconds
    for path in target_dir.iterdir():
        try:
            is_old_upload = path.is_dir() and path.stat().st_mtime < cutoff
        except OSError:
            continue
        if is_old_upload:
            shutil.rmtree(path, ignore_errors=True)


def write_upload_meta(upload_dir: str | Path, owner_token: str) -> None:
    path = Path(upload_dir) / UPLOAD_META_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"owner_token": owner_token or ""}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_upload_owner(upload_dir: str | Path) -> str:
    path = Path(upload_dir) / UPLOAD_META_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""
    if not isinstance(data, dict):
        return ""
    owner_token = data.get("owner_token", "")
    return owner_token if isinstance(owner_token, str) else ""
