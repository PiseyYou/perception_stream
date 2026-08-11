from __future__ import annotations

import cgi
import json
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

from . import config_manager, core, run_state
from .shadow_batch import freeze_batch
from .path_utils import InvalidPathError, resolve_under, safe_filename, unique_path, validate_run_id, validate_upload_id

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}
OWNER_HEADER = "X-Prelabel-Owner-Token"
UPLOAD_ID_PREFIX_RE = re.compile(r"[^A-Za-z0-9_-]+")

gpu_semaphore = threading.Semaphore(1)
pipeline_semaphore = threading.Semaphore(1)


def handle(handler, parsed) -> None:
    path = parsed.path.rstrip("/") or parsed.path
    query = parse_qs(parsed.query or "")
    method = getattr(handler, "command", None) or _default_method_for_path(path)

    try:
        if method == "OPTIONS":
            _send_options(handler)
            return
        if method == "POST" and path == "/prelabel/upload":
            _handle_upload(handler)
            return
        if method == "POST" and path == "/prelabel/run":
            _handle_run(handler)
            return
        if method == "POST" and path == "/prelabel/shadow-run":
            _handle_shadow_run(handler)
            return
        if method == "POST" and path.startswith("/prelabel/runs/") and path.endswith("/shadow-retry"):
            _handle_shadow_retry(handler, path.split("/")[-2])
            return
        if method == "POST" and path.startswith("/prelabel/runs/") and path.endswith("/shadow-reconcile"):
            _handle_shadow_reconcile(handler, path.split("/")[-2])
            return
        if method == "GET" and path.startswith("/prelabel/stream/"):
            _handle_stream(handler, path.rsplit("/", 1)[-1], query)
            return
        if method == "GET" and path == "/prelabel/runs":
            _handle_runs_list(handler)
            return
        if method == "GET" and path.startswith("/prelabel/runs/"):
            _handle_run_detail(handler, path.rsplit("/", 1)[-1])
            return
        if method == "DELETE" and path.startswith("/prelabel/runs/"):
            _handle_run_delete(handler, path.rsplit("/", 1)[-1])
            return
        if method == "POST" and path.startswith("/prelabel/runs/") and path.endswith("/cancel"):
            run_id = path.split("/")[-2]
            _handle_cancel(handler, run_id)
            return
        if method == "GET" and path == "/prelabel/container-status":
            _handle_container_status(handler)
            return
        if method == "POST" and path == "/prelabel/restart-container":
            _handle_restart_container(handler, query)
            return
        if method == "GET" and path == "/prelabel/cvat-users":
            _handle_cvat_users(handler, query)
            return
        if method == "GET" and path == "/prelabel/cvat-servers":
            _handle_cvat_servers(handler)
            return
        if method == "PATCH" and path.startswith("/prelabel/settings/cvat-server/"):
            _handle_cvat_server_patch(handler, path.rsplit("/", 1)[-1])
            return
        if method == "GET" and path == "/prelabel/browse":
            _handle_browse(handler, query)
            return
        _send_json(handler, {"ok": False, "error": "not found"}, status=404)
    except Exception as exc:
        _send_json(handler, {"ok": False, "error": str(exc)}, status=500)


def _default_method_for_path(path: str) -> str:
    if path in {"/prelabel/upload", "/prelabel/run", "/prelabel/shadow-run", "/prelabel/restart-container"}:
        return "POST"
    if path.startswith("/prelabel/runs/") and path.endswith("/cancel"):
        return "POST"
    if path.startswith("/prelabel/runs/") and path.endswith("/shadow-retry"):
        return "POST"
    if path.startswith("/prelabel/runs/") and path.endswith("/shadow-reconcile"):
        return "POST"
    if path.startswith("/prelabel/settings/cvat-server/"):
        return "PATCH"
    return "GET"


def _send_options(handler) -> None:
    handler.send_response(200)
    _send_cors(handler)
    handler.end_headers()


def _send_cors(handler) -> None:
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", f"Content-Type, {OWNER_HEADER}")


def _send_json(handler, payload, status: int = 200) -> None:
    body = json.dumps(_redact(payload), ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    _send_cors(handler)
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler) -> dict:
    length = int(handler.headers.get("Content-Length", 0) or 0)
    if length <= 0:
        return {}
    data = handler.rfile.read(length)
    if not data:
        return {}
    parsed = json.loads(data.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("JSON body must be an object")
    return parsed


def _owner_token_from_header(handler) -> str:
    return handler.headers.get(OWNER_HEADER, "") or ""


def _owner_token_from_body_or_header(handler, body: dict) -> str:
    token = body.get("owner_token") or body.get("token") or _owner_token_from_header(handler)
    return token if isinstance(token, str) else ""


def _redact(value):
    if isinstance(value, dict):
        return {key: _redact(val) for key, val in value.items() if key != "owner_token"}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    return value


def _sse_json(item) -> str:
    try:
        return json.dumps(_redact(item), ensure_ascii=False, default=str)
    except Exception:
        return json.dumps({"type": "log", "level": "error", "msg": "SSE event serialization failed"}, ensure_ascii=False)


def _parse_multipart(handler):
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type.lower():
        raise ValueError("Content-Type must be multipart/form-data")
    return cgi.FieldStorage(
        fp=handler.rfile,
        headers=handler.headers,
        environ={
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": handler.headers.get("Content-Type", ""),
            "CONTENT_LENGTH": handler.headers.get("Content-Length", "0"),
        },
    )


def _form_value(form, key: str, default: str = "") -> str:
    try:
        field = form[key]
    except (KeyError, TypeError):
        return default
    if isinstance(field, list):
        field = field[0] if field else None
    value = getattr(field, "value", default)
    return value if isinstance(value, str) else default


def _form_files(form) -> list:
    try:
        fields = form["files"]
    except (KeyError, TypeError):
        return []
    if not isinstance(fields, list):
        fields = [fields]
    return [field for field in fields if getattr(field, "filename", None)]


def _upload_root(config: dict | None = None) -> Path:
    if config and config.get("upload_dir"):
        return Path(config["upload_dir"]).expanduser().resolve()
    return Path(run_state.UPLOADS_DIR).expanduser().resolve()


def _runs_dir(config: dict | None = None) -> Path:
    if config and config.get("runs_dir"):
        return Path(config["runs_dir"]).expanduser().resolve()
    return Path(run_state.RUNS_DIR).expanduser().resolve()


def _safe_remove_upload_dir(upload_dir: str | None, config: dict) -> None:
    if not upload_dir:
        return
    root = _upload_root(config)
    target = Path(upload_dir).expanduser().resolve()
    if not (target == root or root in target.parents):
        raise ValueError(f"refusing to remove upload path outside upload root: {target}")
    shutil.rmtree(target, ignore_errors=True)


def _make_upload_id(folder_name: str) -> str:
    try:
        hint = safe_filename(folder_name or "upload")
    except ValueError:
        hint = "upload"
    hint = UPLOAD_ID_PREFIX_RE.sub("_", hint).strip("_-") or "upload"
    hint = hint[:39]
    upload_id = f"{hint}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    return validate_upload_id(upload_id)


def _image_count(directory: Path) -> int:
    return sum(1 for path in directory.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)


def _handle_upload(handler) -> None:
    try:
        form = _parse_multipart(handler)
    except ValueError as exc:
        _send_json(handler, {"ok": False, "error": str(exc)}, status=400)
        return
    owner_token = _form_value(form, "owner_token") or _owner_token_from_header(handler)
    if not owner_token:
        _send_json(handler, {"ok": False, "error": "owner_token required"}, status=400)
        return

    upload_id = _form_value(form, "upload_id")
    folder_name = _form_value(form, "folder_name", "upload")
    cfg = _try_load_config()
    root = _upload_root(cfg)
    root.mkdir(parents=True, exist_ok=True)

    if upload_id:
        try:
            upload_id = validate_upload_id(upload_id)
        except ValueError as exc:
            _send_json(handler, {"ok": False, "error": str(exc)}, status=400)
            return
        upload_dir = root / upload_id
        if not upload_dir.is_dir():
            _send_json(handler, {"ok": False, "error": "upload_id not found"}, status=400)
            return
        if run_state.read_upload_owner(upload_dir) != owner_token:
            _send_json(handler, {"ok": False, "error": "owner token mismatch"}, status=400)
            return
    else:
        upload_id = _make_upload_id(folder_name)
        upload_dir = root / upload_id
        upload_dir.mkdir(parents=True, exist_ok=False)
        run_state.write_upload_meta(upload_dir, owner_token)

    files = _form_files(form)
    if not files:
        _send_json(handler, {"ok": False, "error": "no files"}, status=400)
        return

    saved = 0
    skipped: list[str] = []
    for field in files:
        original = getattr(field, "filename", "") or ""
        try:
            filename = safe_filename(original)
        except ValueError:
            skipped.append(original)
            continue
        if Path(filename).suffix.lower() not in IMAGE_EXTENSIONS:
            skipped.append(original)
            continue
        target = unique_path(upload_dir, filename)
        with target.open("wb") as out:
            shutil.copyfileobj(field.file, out)
        saved += 1

    if saved <= 0:
        _send_json(handler, {"ok": False, "error": "no accepted image files", "skipped": skipped}, status=400)
        return

    _send_json(handler, {
        "ok": True,
        "upload_id": upload_id,
        "upload_dir": str(upload_dir),
        "count": saved,
        "total_count": _image_count(upload_dir),
        "skipped": skipped,
    })


def _try_load_config() -> dict:
    try:
        return config_manager.load_config()
    except Exception:
        return {}


def _handle_run(handler) -> None:
    body = _read_json(handler)
    task_prefix = str(body.get("task_prefix", "")).strip()
    if not task_prefix:
        _send_json(handler, {"ok": False, "error": "task_prefix required"}, status=400)
        return

    owner_token = _owner_token_from_body_or_header(handler, body)
    try:
        cfg = config_manager.load_config()
        input_dirs, upload_dir = _validated_inputs(body, cfg, owner_token)
    except (ValueError, InvalidPathError) as exc:
        _send_json(handler, {"ok": False, "error": str(exc)}, status=400)
        return
    except PermissionError as exc:
        _send_json(handler, {"ok": False, "error": str(exc)}, status=403)
        return

    if not input_dirs:
        _send_json(handler, {"ok": False, "error": "no input dirs"}, status=400)
        return

    run_id = uuid.uuid4().hex[:12]
    runtime = run_state.make_runtime_run(
        task_prefix,
        input_dirs,
        owner_token=owner_token,
        skip_steps=body.get("skip_steps") or [],
        upload_dir=upload_dir,
    )
    with run_state.runs_lock:
        run_state.runs[run_id] = runtime
    run_state.save_run(run_id, _runs_dir(cfg))

    params = dict(body)
    params.update({
        "cancel_fn": lambda: _is_cancelled(run_id),
        "set_proc_fn": lambda proc: _set_proc(run_id, proc),
        "clear_proc_fn": lambda: _clear_proc(run_id),
        "gpu_semaphore": gpu_semaphore,
        "pipeline_semaphore": pipeline_semaphore,
    })

    def thread_target() -> None:
        _run_pipeline_thread(run_id, task_prefix, input_dirs, params, cfg, upload_dir)

    thread = threading.Thread(target=thread_target, daemon=True)
    thread.start()
    _send_json(handler, {"run_id": run_id})


def _handle_shadow_run(handler) -> None:
    """Submit one frozen A/B job; duplicate snapshots return the existing run."""
    body = _read_json(handler)
    task_prefix = str(body.get("task_prefix", "")).strip()
    if not task_prefix:
        _send_json(handler, {"ok": False, "error": "task_prefix required"}, status=400)
        return
    owner_token = _owner_token_from_body_or_header(handler, body)
    if not owner_token:
        _send_json(handler, {"ok": False, "error": "owner token required"}, status=403)
        return
    try:
        cfg = config_manager.load_config()
        input_dirs, upload_dir = _validated_inputs(body, cfg, owner_token)
        if len(input_dirs) != 1:
            raise ValueError("shadow run requires exactly one input directory")
        snapshot_root = cfg.get("shadow_snapshot_root") or str(_runs_dir(cfg).parent / "shadow_snapshots")
        snapshot = freeze_batch(input_dirs[0], snapshot_root)
    except (ValueError, InvalidPathError) as exc:
        _send_json(handler, {"ok": False, "error": str(exc)}, status=400)
        return
    except PermissionError as exc:
        _send_json(handler, {"ok": False, "error": str(exc)}, status=403)
        return
    with run_state.runs_lock:
        indexed = run_state.load_shadow_index(_runs_dir(cfg))
        index_key = f"{owner_token}:{snapshot['batch_id']}:{snapshot['snapshot_hash']}"
        if index_key in indexed:
            _send_json(handler, {"run_id": indexed[index_key]["run_id"], "idempotent": True, "retained": True})
            return
        for existing_id, existing in run_state.runs.items():
            shadow = existing.get("shadow", {})
            if shadow.get("batch_id") == snapshot["batch_id"] and shadow.get("snapshot_hash") == snapshot["snapshot_hash"]:
                if existing.get("owner_token") != owner_token:
                    _send_json(handler, {"ok": False, "error": "shadow batch already exists"}, status=409)
                    return
                _send_json(handler, {"run_id": existing_id, "idempotent": True})
                return
        run_id = uuid.uuid4().hex[:12]
        intents = {branch: {"branch_id": branch, "status": "intent_persisted", "idempotency_key": run_state.shadow_idempotency_key(snapshot["batch_id"], branch, snapshot["snapshot_hash"])} for branch in ("A", "B")}
        runtime = run_state.make_runtime_run(task_prefix, input_dirs, owner_token=owner_token, upload_dir=upload_dir, shadow={**snapshot, "status": "running", "branches": intents})
        run_state.runs[run_id] = runtime
    run_state.save_run(run_id, _runs_dir(cfg))
    params = dict(body)
    # Never accept executable integration callbacks from JSON.  The route owns
    # the real CVAT boundary; tests patch this factory with deterministic fakes.
    params["shadow_adapters"] = core.build_shadow_adapters(cfg)
    params.update({"shadow_snapshot": snapshot, "cancel_fn": lambda: _is_cancelled(run_id), "gpu_semaphore": gpu_semaphore})

    def checkpoint(state: dict) -> None:
        with run_state.runs_lock:
            run = run_state.runs.get(run_id)
            if run:
                run["shadow"] = _redact(state)
                run["result"] = _redact(state)
        run_state.save_run(run_id, _runs_dir(cfg))
    params["shadow_checkpoint"] = checkpoint
    with run_state.runs_lock:
        run_state.runs[run_id]["shadow_cleanup"] = params["shadow_adapters"]["cleanup"]

    def target() -> None:
        try:
            result = core.run_shadow_pipeline(run_id, task_prefix, input_dirs, params, cfg, lambda item: _append_log(run_id, item))
            with run_state.runs_lock:
                run = run_state.runs.get(run_id)
                if run:
                    run["result"] = _redact(result)
                    run["shadow"] = _redact(result)
                    run["status"] = result.get("status", "failed")
        except Exception as exc:
            _append_log(run_id, {"type": "log", "level": "error", "msg": str(exc)})
            with run_state.runs_lock:
                run = run_state.runs.get(run_id)
                if run:
                    run["status"] = "failed"
                    run["result"] = {"error": str(exc)}
        finally:
            with run_state.runs_lock:
                run = run_state.runs.get(run_id)
                if run:
                    run["finished_at"] = datetime.now().isoformat(timespec="seconds")
                    run["done"] = True
                    run["event"].set()
            run_state.save_run(run_id, _runs_dir(cfg))
            # A snapshot is immutable and deliberately retained for audit/retry;
            # uploaded staging data can be removed only after it has been frozen.
            if upload_dir:
                _safe_remove_upload_dir(upload_dir, cfg)

    threading.Thread(target=target, daemon=True).start()
    _send_json(handler, {"run_id": run_id, "batch_id": snapshot["batch_id"]})


def _handle_shadow_retry(handler, run_id: str) -> None:
    """Retry exactly one durable failed branch; no recovery path creates tasks."""
    body = _read_json(handler)
    owner_token = _owner_token_from_body_or_header(handler, body)
    branch = body.get("branch_id")
    if branch not in {"A", "B"}:
        _send_json(handler, {"ok": False, "error": "branch_id A or B required"}, status=400)
        return
    try:
        validate_run_id(run_id)
        cfg = config_manager.load_config()
    except (ValueError, InvalidPathError) as exc:
        _send_json(handler, {"ok": False, "error": str(exc)}, status=400)
        return
    with run_state.runs_lock:
        run = run_state.runs.get(run_id)
        shadow = run.get("shadow") if run else None
        previous = shadow.get("branches", {}).get(branch, {}) if isinstance(shadow, dict) else {}
        if not run or not isinstance(shadow, dict) or previous.get("status") != "failed":
            _send_json(handler, {"ok": False, "error": "only a failed shadow branch may be retried"}, status=409)
            return
        if not owner_token or owner_token != run.get("owner_token"):
            _send_json(handler, {"ok": False, "error": "owner token mismatch"}, status=403)
            return
        run["status"] = "running"
        run["done"] = False
        run["event"].clear()
    params = {"shadow_snapshot": {key: shadow[key] for key in ("batch_id", "snapshot_hash", "snapshot_path")}, "shadow_state": shadow, "retry_branch": branch, "shadow_adapters": core.build_shadow_adapters(cfg), "gpu_semaphore": gpu_semaphore, "cancel_fn": lambda: _is_cancelled(run_id)}
    def checkpoint(state: dict) -> None:
        with run_state.runs_lock:
            current = run_state.runs.get(run_id)
            if current:
                current["shadow"] = _redact(state)
                current["result"] = _redact(state)
        run_state.save_run(run_id, _runs_dir(cfg))
    params["shadow_checkpoint"] = checkpoint
    def target() -> None:
        try:
            result = core.run_shadow_pipeline(run_id, run["task_prefix"], run["input_dirs"], params, cfg, lambda item: _append_log(run_id, item))
            checkpoint(result)
            with run_state.runs_lock:
                current = run_state.runs.get(run_id)
                if current:
                    current["status"], current["done"], current["finished_at"] = result["status"], True, datetime.now().isoformat(timespec="seconds")
                    current["event"].set()
        except Exception as exc:
            _append_log(run_id, {"type": "log", "level": "error", "msg": str(exc)})
            with run_state.runs_lock:
                current = run_state.runs.get(run_id)
                if current:
                    current["status"], current["done"], current["finished_at"] = "failed", True, datetime.now().isoformat(timespec="seconds")
                    current["result"] = {"error": str(exc)}
                    current["event"].set()
        finally:
            run_state.save_run(run_id, _runs_dir(cfg))
    threading.Thread(target=target, daemon=True).start()
    _send_json(handler, {"run_id": run_id, "retry_branch": branch})


def _handle_shadow_reconcile(handler, run_id: str) -> None:
    """Authorized cleanup of durable orphan tasks; it never creates work."""
    body = _read_json(handler)
    token = _owner_token_from_body_or_header(handler, body)
    try:
        validate_run_id(run_id)
        cfg = config_manager.load_config()
    except ValueError as exc:
        _send_json(handler, {"ok": False, "error": str(exc)}, status=400)
        return
    with run_state.runs_lock:
        run = run_state.runs.get(run_id)
        if not run or not token or token != run.get("owner_token"):
            _send_json(handler, {"ok": False, "error": "owner token mismatch"}, status=403)
            return
        branches = run.get("shadow", {}).get("branches", {})
    cleanup = core.build_shadow_adapters(cfg)["cleanup"]
    reconciled = []
    for branch in branches.values():
        if not isinstance(branch, dict) or not branch.get("task_id") or branch.get("cleanup", {}).get("status") not in {"needed", "failed"}:
            continue
        task_id = branch["task_id"]
        try:
            cleanup(task_id)
            branch["cleanup"] = {"status": "reconciled", "task_id": task_id}
            reconciled.append(task_id)
        except Exception as exc:
            branch["cleanup"] = {"status": "failed", "task_id": task_id, "error": str(exc)}
    run_state.save_run(run_id, _runs_dir(cfg))
    _send_json(handler, {"ok": True, "reconciled_task_ids": reconciled})


def _validated_inputs(body: dict, cfg: dict, owner_token: str) -> tuple[list[str], str | None]:
    roots = cfg.get("browse_roots") or []
    input_dirs = []
    raw_dirs = body.get("input_dirs") or []
    if isinstance(raw_dirs, (str, bytes)):
        raw_dirs = [raw_dirs]
    for item in raw_dirs:
        if not item:
            continue
        input_dirs.append(str(resolve_under(item, roots)))

    upload_dir = None
    upload_id = body.get("upload_id") or ""
    if upload_id:
        upload_id = validate_upload_id(str(upload_id))
        upload_path = _upload_root(cfg) / upload_id
        if not upload_path.is_dir():
            raise ValueError("upload_id not found")
        saved_owner = run_state.read_upload_owner(upload_path)
        if not saved_owner:
            raise PermissionError("upload owner metadata missing")
        if saved_owner != owner_token:
            raise PermissionError("owner token mismatch")
        upload_dir = str(upload_path)
        if upload_dir not in input_dirs:
            input_dirs.append(upload_dir)
    return input_dirs, upload_dir


def _run_pipeline_thread(run_id: str, task_prefix: str, input_dirs: list[str], params: dict, cfg: dict, upload_dir: str | None) -> None:
    acquired = False
    try:
        if params.get("serial_mode"):
            while not pipeline_semaphore.acquire(timeout=0.2):
                if _is_cancelled(run_id):
                    raise RuntimeError("用户已取消")
            acquired = True
        result = core.run_pipeline(run_id, task_prefix, input_dirs, params, cfg, lambda item: _append_log(run_id, item))
        with run_state.runs_lock:
            run = run_state.runs.get(run_id)
            if run:
                run["result"] = _redact(result)
                if run.get("cancel"):
                    run["status"] = "cancelled"
                else:
                    statuses = [item.get("status") for item in result if isinstance(item, dict)]
                    if statuses and all(status == "success" for status in statuses):
                        run["status"] = "success"
                    elif any(status == "success" for status in statuses):
                        run["status"] = "partial"
                    else:
                        run["status"] = "failed"
    except Exception as exc:
        _append_log(run_id, {"type": "log", "level": "error", "msg": str(exc)})
        with run_state.runs_lock:
            run = run_state.runs.get(run_id)
            if run:
                run["status"] = "cancelled" if run.get("cancel") else "failed"
                run["result"] = {"error": str(exc)}
    finally:
        if acquired:
            pipeline_semaphore.release()
        _clear_proc(run_id)
        with run_state.runs_lock:
            run = run_state.runs.get(run_id)
            if run:
                run["finished_at"] = datetime.now().isoformat(timespec="seconds")
                run["done"] = True
                event = run.get("event")
                if event:
                    event.set()
        run_state.save_run(run_id, _runs_dir(cfg))
        if upload_dir:
            _safe_remove_upload_dir(upload_dir, cfg)


def _append_log(run_id: str, item) -> None:
    if not isinstance(item, dict):
        item = {"type": "log", "msg": str(item)}
    item = _redact(dict(item))
    item.setdefault("time", datetime.now().strftime("%H:%M:%S"))
    with run_state.runs_lock:
        run = run_state.runs.get(run_id)
        if not run:
            return
        run.setdefault("logs", []).append(item)
        event = run.get("event")
        if event:
            event.set()


def _is_cancelled(run_id: str) -> bool:
    with run_state.runs_lock:
        run = run_state.runs.get(run_id)
        return bool(run and run.get("cancel"))


def _set_proc(run_id: str, proc) -> None:
    with run_state.runs_lock:
        run = run_state.runs.get(run_id)
        if run:
            run["proc"] = proc


def _clear_proc(run_id: str) -> None:
    with run_state.runs_lock:
        run = run_state.runs.get(run_id)
        if run:
            run["proc"] = None


def _handle_stream(handler, run_id: str, query: dict | None = None) -> None:
    try:
        run_id = validate_run_id(run_id)
    except ValueError as exc:
        _send_json(handler, {"ok": False, "error": str(exc)}, status=404)
        return
    with run_state.runs_lock:
        run = run_state.runs.get(run_id)
    if not run:
        _send_json(handler, {"ok": False, "error": "run not found"}, status=404)
        return
    expected = run.get("owner_token") or ""
    token = _owner_token_from_header(handler)
    if not token and query:
        token = (query.get("token") or [""])[0]
    if expected and token != expected:
        _send_json(handler, {"ok": False, "error": "owner token mismatch"}, status=403)
        return

    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.send_header("X-Accel-Buffering", "no")
    _send_cors(handler)
    handler.end_headers()

    sent = 0
    while True:
        with run_state.runs_lock:
            current = run_state.runs.get(run_id)
            if not current:
                pending = []
                done = True
                event = None
            else:
                logs = list(current.get("logs", []))
                pending = logs[sent:]
                sent = len(logs)
                done = bool(current.get("done"))
                event = current.get("event")
                if event:
                    event.clear()
        try:
            for item in pending:
                handler.wfile.write(("data: " + _sse_json(item) + "\n\n").encode("utf-8"))
                handler.wfile.flush()
            if done:
                handler.wfile.write(b"data: null\n\n")
                handler.wfile.flush()
                return
        except (BrokenPipeError, ConnectionResetError, OSError):
            return
        if event:
            event.wait(timeout=25)
        else:
            time.sleep(0.2)


def _handle_runs_list(handler) -> None:
    token = _owner_token_from_header(handler)
    with run_state.runs_lock:
        records = [
            run_state.serialize_run(run_id, run, expose_paths=False, owner_token=token)
            for run_id, run in run_state.runs.items()
        ]
    records.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    _send_json(handler, records)


def _handle_run_detail(handler, run_id: str) -> None:
    try:
        run_id = validate_run_id(run_id)
    except ValueError as exc:
        _send_json(handler, {"ok": False, "error": str(exc)}, status=404)
        return
    token = _owner_token_from_header(handler)
    with run_state.runs_lock:
        run = run_state.runs.get(run_id)
        if not run:
            _send_json(handler, {"ok": False, "error": "run not found"}, status=404)
            return
        if isinstance(run.get("shadow"), dict) and (not token or token != run.get("owner_token")):
            _send_json(handler, {"ok": False, "error": "run not found"}, status=404)
            return
        record = run_state.serialize_run(run_id, run, expose_paths=False, include_logs=True, owner_token=token)
    _send_json(handler, record)


def _handle_run_delete(handler, run_id: str) -> None:
    try:
        run_id = validate_run_id(run_id)
    except ValueError as exc:
        _send_json(handler, {"ok": False, "error": str(exc)}, status=404)
        return
    with run_state.runs_lock:
        run = run_state.runs.get(run_id)
        if run:
            expected = run.get("owner_token") or ""
            token = _owner_token_from_header(handler)
            if expected and token != expected:
                _send_json(handler, {"ok": False, "error": "owner token mismatch"}, status=403)
                return
        run_state.runs.pop(run_id, None)
    run_state.run_json_path(_runs_dir(_try_load_config()), run_id).unlink(missing_ok=True)
    _send_json(handler, {"ok": True})


def _handle_cancel(handler, run_id: str) -> None:
    try:
        run_id = validate_run_id(run_id)
    except ValueError as exc:
        _send_json(handler, {"ok": False, "error": str(exc)}, status=404)
        return
    body = _read_json(handler)
    token = _owner_token_from_body_or_header(handler, body)
    with run_state.runs_lock:
        run = run_state.runs.get(run_id)
        if not run:
            _send_json(handler, {"ok": False, "error": "run not found"}, status=404)
            return
        if run.get("done") or run.get("status") != "running":
            _send_json(handler, {"ok": False, "error": "run is not running"}, status=400)
            return
        expected = run.get("owner_token") or ""
        if expected and token != expected:
            _send_json(handler, {"ok": False, "error": "owner token mismatch"}, status=403)
            return
        run["cancel"] = True
        shadow_cleanup = run.get("shadow_cleanup")
        shadow_task_ids = [branch.get("task_id") for branch in run.get("shadow", {}).get("branches", {}).values() if isinstance(branch, dict) and branch.get("task_id")]
        if isinstance(run.get("shadow"), dict):
            for branch in run["shadow"].get("branches", {}).values():
                if isinstance(branch, dict) and branch.get("task_id"):
                    branch["status"] = "cancelled"
                    branch["cleanup"] = {"status": "needed", "task_id": branch["task_id"], "reason": "cancel"}
        proc = run.get("proc")
        event = run.get("event")
        if event:
            event.set()
    killed = False
    if proc:
        try:
            proc.kill()
            killed = True
        except Exception:
            killed = False
    if callable(shadow_cleanup):
        for branch in run.get("shadow", {}).get("branches", {}).values():
            if not isinstance(branch, dict) or not branch.get("task_id"):
                continue
            task_id = branch["task_id"]
            try:
                outcome = shadow_cleanup(task_id)
                branch["cleanup"] = {"status": "attempted", "task_id": task_id, "result": outcome}
            except Exception as exc:
                branch["cleanup"] = {"status": "failed", "task_id": task_id, "error": str(exc)}
    if shadow_task_ids:
        run_state.save_run(run_id, _runs_dir(_try_load_config()))
    _send_json(handler, {
        "ok": True,
        "msg": "已立即终止当前步骤" if killed else "已设置取消标志（无进行中的子进程）",
    })


def _handle_container_status(handler) -> None:
    cfg = _try_load_config()
    container = cfg.get("docker", {}).get("container", "MPformer")
    payload = {"container": container, "container_status": "unknown", "gpu_ok": False, "gpu_info": ""}
    try:
        docker = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}}", container],
            capture_output=True,
            text=True,
            timeout=8,
        )
        payload["container_status"] = docker.stdout.strip() if docker.returncode == 0 else "not_found"
        if docker.returncode != 0:
            payload["docker_error"] = docker.stderr.strip()
    except Exception as exc:
        payload["docker_error"] = str(exc)

    try:
        gpu_cmd = ["docker", "exec", container, "nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader"]
        gpu = subprocess.run(
            gpu_cmd,
            capture_output=True,
            text=True,
            timeout=8,
        )
        payload["gpu_ok"] = gpu.returncode == 0
        payload["gpu_command"] = " ".join(gpu_cmd)
        payload["gpu_info"] = gpu.stdout.strip() if gpu.returncode == 0 else gpu.stderr.strip()
    except Exception as exc:
        payload["gpu_info"] = str(exc)
    _send_json(handler, payload)


def _has_active_run() -> bool:
    with run_state.runs_lock:
        return any(run.get("status") == "running" and not run.get("done") for run in run_state.runs.values())


def _handle_restart_container(handler, query: dict) -> None:
    mode = (query.get("mode") or ["manual"])[0]
    if mode not in {"manual", "auto"}:
        _send_json(handler, {"ok": False, "error": "invalid mode"}, status=400)
        return
    if mode == "auto" and _has_active_run():
        _send_json(handler, {"ok": True, "skipped": True, "mode": mode, "message": "active prelabel run"}, status=409)
        return
    cfg = config_manager.load_config()
    container = cfg.get("docker", {}).get("container", "MPformer")
    logs: list[str] = []
    core.diagnose_cuda_error(container, logs.append)
    ok = core.restart_docker_container(container, logs.append)
    _send_json(handler, {"ok": ok, "skipped": False, "mode": mode, "message": "\n".join(logs)}, status=200 if ok else 500)


def _handle_cvat_users(handler, query: dict) -> None:
    server_id = (query.get("server_id") or [None])[0]
    try:
        users = core.list_cvat_users(config_manager.load_config(), server_id=server_id)
        _send_json(handler, {"ok": True, "users": users})
    except Exception as exc:
        _send_json(handler, {"ok": False, "error": str(exc)}, status=500)


def _handle_cvat_servers(handler) -> None:
    try:
        cfg = config_manager.load_config(expand_placeholders=False, require_credentials=False)
        _send_json(handler, {"ok": True, "servers": config_manager.safe_cvat_servers(cfg)})
    except Exception as exc:
        _send_json(handler, {"ok": False, "error": str(exc)}, status=500)


def _handle_cvat_server_patch(handler, server_id: str) -> None:
    body = _read_json(handler)
    try:
        cfg = config_manager.load_config(expand_placeholders=False, require_credentials=False)
        server = next((item for item in cfg.get("cvat_servers", []) if item.get("id") == server_id), None)
        if not server:
            _send_json(handler, {"ok": False, "error": "server not found"}, status=404)
            return
        if "host" in body:
            server["host"] = str(body["host"]).strip()
            if not server["host"]:
                raise ValueError("host required")
        if "port" in body:
            port = int(body["port"])
            if port < 1 or port > 65535:
                raise ValueError("invalid port")
            server["port"] = port
        if "user" in body:
            user = str(body["user"]).strip()
            if user:
                server["user"] = user
            else:
                server.pop("user", None)
        if "password" in body:
            password = str(body["password"])
            if password:
                server["password"] = password
        config_manager.save_config(cfg)
        core.clear_cvat_session_cache(server_id)
        _send_json(handler, {"ok": True, "server": config_manager.safe_cvat_servers({"cvat_servers": [server]})[0]})
    except ValueError as exc:
        _send_json(handler, {"ok": False, "error": str(exc)}, status=400)


def _handle_browse(handler, query: dict) -> None:
    cfg = config_manager.load_config()
    roots = cfg.get("browse_roots") or []
    requested = (query.get("path") or [roots[0] if roots else ""])[0]
    try:
        directory = resolve_under(requested, roots)
    except InvalidPathError as exc:
        _send_json(handler, {"ok": False, "error": str(exc)}, status=403)
        return
    if not directory.is_dir():
        _send_json(handler, {"ok": False, "error": "directory not found"}, status=404)
        return
    children = []
    try:
        entries = sorted(directory.iterdir(), key=lambda path: path.name.lower())
        for entry in entries:
            if not entry.name.startswith("."):
                try:
                    child = resolve_under(entry, roots)
                except InvalidPathError:
                    continue
                if child.is_dir():
                    children.append({"name": entry.name, "path": str(child)})
    except PermissionError as exc:
        _send_json(handler, {"ok": False, "error": str(exc)}, status=403)
        return
    _send_json(handler, {"ok": True, "path": str(directory), "directories": children})
