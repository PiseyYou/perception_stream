# Prelabel Pipeline Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the complete `/media/sdc2/lhx/pipeline` prelabel upload workflow into `perception_streaming` as a native `/prelabel` module and Vue tab beside `双目分析`.

**Architecture:** Add a focused `robot_monitor/prelabel_pipeline` Python package for config, path safety, run state, core five-step pipeline logic, and HTTP route handling. Keep `offline_server.py` as the central threaded backend and dispatch `/prelabel/*` into the new package. Add `PrelabelPipelinePanel.vue` to the existing Vue tab shell and apply low-risk migration fixes discovered during path review.

**Tech Stack:** Python 3.10 stdlib `BaseHTTPRequestHandler`/`ThreadingHTTPServer`, `threading`, `subprocess`, `yaml`, CVAT SDK, `requests`, `PIL`, `pandas`; Vue 3 + TypeScript + Vite; existing `unittest` and `npm run build`.

---

## Source Documents

- Spec: `docs/superpowers/specs/2026-04-29-prelabel-pipeline-integration-design.md`
- Source pipeline: `/media/sdc2/lhx/pipeline`
- Target app: `/media/sdc2/lhx/perception_process/perception_streaming`

## File Structure

Create backend package:

- Create: `perception_streaming/robot_monitor/prelabel_pipeline/__init__.py`
  - Package marker and public route import.
- Create: `perception_streaming/robot_monitor/prelabel_pipeline/path_utils.py`
  - Shared path validation, id validation, filename sanitization, JSON response helpers where useful.
- Create: `perception_streaming/robot_monitor/prelabel_pipeline/config_manager.py`
  - Load/save `prelabel_config.yaml`, inject CVAT credentials from env, expose safe server data.
- Create: `perception_streaming/robot_monitor/prelabel_pipeline/run_state.py`
  - Own `runs`, `runs_lock`, serialization, persistence in `data/prelabel_runs`, upload metadata, cleanup.
- Create: `perception_streaming/robot_monitor/prelabel_pipeline/core.py`
  - Port five-step pipeline core from `/media/sdc2/lhx/pipeline/pipeline_core.py`, remove runtime dependency on `/media/sdc2/lhx/pipeline`.
- Create: `perception_streaming/robot_monitor/prelabel_pipeline/routes.py`
  - Implement `/prelabel/*` route dispatch for `OfflineHandler`.
- Create: `perception_streaming/robot_monitor/prelabel_pipeline/prelabel_config.yaml`
  - Default config from spec.
- Create: `perception_streaming/robot_monitor/prelabel_pipeline/labels_mapping.yaml`
  - Copy label mapping from source pipeline.

Modify existing backend:

- Modify: `perception_streaming/robot_monitor/offline_server.py`
  - Dispatch `/prelabel/*`.
  - Harden legacy local file and ros2deploy paths.
  - Fix `_current_proc` assignment and stop behavior for offline Docker run.
- Modify: `perception_streaming/robot_monitor/config_loader.py`
  - Resolve relative SSH key paths from config directory and allow env override if needed for migration fix.
- Modify: `perception_streaming/restart_services.sh`
  - Compute project directory from script path.
- Modify: `perception_streaming/src/composables/useObstacleMonitor.ts`
  - Use `location.hostname` for WebSocket host.
- Modify: `perception_streaming/src/components/PointCloudPanel.vue`
  - Use `location.hostname` and the local proxy port `8766`.
- Modify: `perception_streaming/vite.config.ts`
  - Proxy `/prelabel` to the existing offline server on port `8769`, including SSE-friendly streaming behavior.
- Modify: `perception_streaming/config/machine_config.json`
  - Normalize SSH key path only if the code path requires it after `config_loader.py` fix.
- Modify: `01_evb/run_evb_remote.sh`
  - Compute project root from script path.

Create/modify tests:

- Create: `perception_streaming/robot_monitor/tests/test_prelabel_path_utils.py`
- Create: `perception_streaming/robot_monitor/tests/test_prelabel_config.py`
- Create: `perception_streaming/robot_monitor/tests/test_prelabel_run_state.py`
- Create: `perception_streaming/robot_monitor/tests/test_prelabel_routes.py`
- Create: `perception_streaming/robot_monitor/tests/test_prelabel_core.py`
- Modify: `perception_streaming/robot_monitor/tests/test_offline_server.py`
  - Add migration bug regression tests where import-safe.

Create frontend:

- Create: `perception_streaming/src/components/PrelabelPipelinePanel.vue`
- Modify: `perception_streaming/src/App.vue`
  - Add tab and component import.

## Task 1: Backend Package Skeleton, Config, And Path Utilities

**Files:**
- Create: `perception_streaming/robot_monitor/prelabel_pipeline/__init__.py`
- Create: `perception_streaming/robot_monitor/prelabel_pipeline/path_utils.py`
- Create: `perception_streaming/robot_monitor/prelabel_pipeline/config_manager.py`
- Create: `perception_streaming/robot_monitor/prelabel_pipeline/prelabel_config.yaml`
- Create: `perception_streaming/robot_monitor/prelabel_pipeline/labels_mapping.yaml`
- Test: `perception_streaming/robot_monitor/tests/test_prelabel_path_utils.py`
- Test: `perception_streaming/robot_monitor/tests/test_prelabel_config.py`

- [ ] **Step 1: Write failing path utility tests**

Create `perception_streaming/robot_monitor/tests/test_prelabel_path_utils.py`:

```python
import sys
import tempfile
import unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
ROBOT_MONITOR_DIR = TEST_DIR.parent
if str(ROBOT_MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(ROBOT_MONITOR_DIR))

from prelabel_pipeline.path_utils import (
    InvalidPathError,
    safe_filename,
    validate_run_id,
    validate_upload_id,
    resolve_under,
)


class PrelabelPathUtilsTest(unittest.TestCase):
    def test_resolve_under_accepts_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            child = root / "images"
            child.mkdir()
            self.assertEqual(resolve_under(child, [root]), child)

    def test_resolve_under_rejects_outside_path(self):
        with tempfile.TemporaryDirectory() as root_tmp, tempfile.TemporaryDirectory() as other_tmp:
            with self.assertRaises(InvalidPathError):
                resolve_under(Path(other_tmp), [Path(root_tmp)])

    def test_resolve_under_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as root_tmp, tempfile.TemporaryDirectory() as other_tmp:
            root = Path(root_tmp)
            link = root / "escape"
            link.symlink_to(Path(other_tmp), target_is_directory=True)
            with self.assertRaises(InvalidPathError):
                resolve_under(link, [root])

    def test_safe_filename_keeps_basename_and_extension(self):
        self.assertEqual(safe_filename("../foo/image 1.jpg"), "image_1.jpg")

    def test_safe_filename_rejects_empty(self):
        with self.assertRaises(ValueError):
            safe_filename("..")

    def test_validate_upload_id_accepts_expected_ids(self):
        upload_id = "folder_0429_153012_a1b2c3d4"
        self.assertEqual(validate_upload_id(upload_id), upload_id)

    def test_validate_upload_id_rejects_short_or_path_fragments(self):
        for value in ("../abc", "abc/def", "abc.def", "short", "abcDEF_123456"):
            with self.assertRaises(ValueError):
                validate_upload_id(value)

    def test_validate_run_id_requires_12_hex_chars(self):
        self.assertEqual(validate_run_id("abcdef123456"), "abcdef123456")
        for value in ("abcdef12345", "abcdef1234567", "ABCDEF123456", "../abcdef123456"):
            with self.assertRaises(ValueError):
                validate_run_id(value)
```

- [ ] **Step 2: Run path utility tests to verify they fail**

Run:

```bash
cd /media/sdc2/lhx/perception_process/perception_streaming
python3 -m unittest robot_monitor.tests.test_prelabel_path_utils -v
```

Expected: fail with `ModuleNotFoundError` or missing functions.

- [ ] **Step 3: Implement minimal path utilities**

Create `perception_streaming/robot_monitor/prelabel_pipeline/path_utils.py`:

```python
from __future__ import annotations

import re
from pathlib import Path

_UPLOAD_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{16,64}$")
_RUN_ID_RE = re.compile(r"^[a-f0-9]{12}$")


class InvalidPathError(ValueError):
    pass


def resolve_under(path: str | Path, roots: list[str | Path]) -> Path:
    resolved = Path(path).expanduser().resolve()
    resolved_roots = [Path(root).expanduser().resolve() for root in roots]
    if not any(resolved == root or root in resolved.parents for root in resolved_roots):
        raise InvalidPathError(f"path outside allowed roots: {resolved}")
    return resolved


def validate_upload_id(value: str) -> str:
    if not value or not _UPLOAD_ID_RE.fullmatch(value):
        raise ValueError("invalid upload_id")
    return value


def validate_run_id(value: str) -> str:
    if not value or not _RUN_ID_RE.fullmatch(value):
        raise ValueError("invalid run_id")
    return value


def safe_filename(name: str) -> str:
    raw = Path((name or "").replace("\\", "/")).name
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")
    if not stem:
        raise ValueError("empty filename")
    return stem


def unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    index = 2
    while True:
        next_candidate = directory / f"{stem}_{index}{suffix}"
        if not next_candidate.exists():
            return next_candidate
        index += 1
```

- [ ] **Step 4: Write failing config tests**

Create `perception_streaming/robot_monitor/tests/test_prelabel_config.py`:

```python
import sys
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

TEST_DIR = Path(__file__).resolve().parent
ROBOT_MONITOR_DIR = TEST_DIR.parent
if str(ROBOT_MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(ROBOT_MONITOR_DIR))

from prelabel_pipeline.config_manager import load_config, safe_cvat_servers


class PrelabelConfigTest(unittest.TestCase):
    def _write_config(self, path: Path):
        path.write_text(yaml.safe_dump({
            "cvat_servers": [{"id": "remote", "name": "Remote", "host": "127.0.0.1", "port": 8080}],
            "docker": {"container": "MPformer"},
            "model": {
                "demo_dir": "/media/sdc2/lhx/MPformer/MP-Former/demo",
                "config": "/cfg.yaml",
                "weights": "/weights.pth",
                "min_area": 50,
            },
            "labels_csv": "/labels.csv",
            "output_base": "/tmp/output",
            "upload_dir": "/tmp/uploads",
            "runs_dir": "/tmp/runs",
            "browse_roots": ["/tmp"],
            "segment_size": 1000,
        }, allow_unicode=True), encoding="utf-8")

    def test_load_config_injects_env_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "prelabel_config.yaml"
            self._write_config(config_path)
            with patch.dict(os.environ, {
                "CVAT_REMOTE_USER": "alice",
                "CVAT_REMOTE_PASSWORD": "secret",
            }, clear=False):
                cfg = load_config(config_path)
            self.assertEqual(cfg["cvat_servers"][0]["user"], "alice")
            self.assertEqual(cfg["cvat_servers"][0]["password"], "secret")

    def test_load_config_requires_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "prelabel_config.yaml"
            self._write_config(config_path)
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ValueError):
                    load_config(config_path)

    def test_safe_servers_redacts_credentials(self):
        servers = [{"id": "remote", "name": "Remote", "host": "h", "port": 1, "user": "u", "password": "p"}]
        self.assertEqual(safe_cvat_servers({"cvat_servers": servers}), [
            {"id": "remote", "name": "Remote", "host": "h", "port": 1}
        ])
```

- [ ] **Step 5: Implement config manager and default config**

Create `prelabel_config.yaml` from the spec. Copy `labels_mapping.yaml` from `/media/sdc2/lhx/pipeline/labels_mapping.yaml`.

Create `perception_streaming/robot_monitor/prelabel_pipeline/config_manager.py`:

```python
from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "prelabel_config.yaml"


def load_config(config_path: str | Path | None = None) -> dict:
    path = Path(config_path) if config_path else CONFIG_PATH
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    for server in cfg.get("cvat_servers", []):
        sid = server["id"].upper().replace("-", "_")
        user = os.environ.get(f"CVAT_{sid}_USER", server.get("user", ""))
        password = os.environ.get(f"CVAT_{sid}_PASSWORD", server.get("password", ""))
        if not user or not password:
            raise ValueError(f"请设置环境变量 CVAT_{sid}_USER 和 CVAT_{sid}_PASSWORD")
        server["user"] = user
        server["password"] = password
    return cfg


def save_config(config: dict, config_path: str | Path | None = None) -> None:
    path = Path(config_path) if config_path else CONFIG_PATH
    safe = copy.deepcopy(config)
    for server in safe.get("cvat_servers", []):
        server.pop("user", None)
        server.pop("password", None)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(safe, f, allow_unicode=True, sort_keys=False)


def safe_cvat_servers(config: dict) -> list[dict]:
    return [
        {"id": s["id"], "name": s["name"], "host": s["host"], "port": s["port"]}
        for s in config.get("cvat_servers", [])
    ]
```

- [ ] **Step 6: Run Task 1 tests**

Run:

```bash
cd /media/sdc2/lhx/perception_process/perception_streaming
python3 -m unittest robot_monitor.tests.test_prelabel_path_utils robot_monitor.tests.test_prelabel_config -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```bash
cd /media/sdc2/lhx/perception_process
git add perception_streaming/robot_monitor/prelabel_pipeline perception_streaming/robot_monitor/tests/test_prelabel_path_utils.py perception_streaming/robot_monitor/tests/test_prelabel_config.py
git commit -m "feat: add prelabel config and path utilities"
```

## Task 2: Run State, Upload Metadata, And Serialization

**Files:**
- Create: `perception_streaming/robot_monitor/prelabel_pipeline/run_state.py`
- Test: `perception_streaming/robot_monitor/tests/test_prelabel_run_state.py`

- [ ] **Step 1: Write failing run state tests**

Create `test_prelabel_run_state.py`:

```python
import sys
import tempfile
import threading
import unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
ROBOT_MONITOR_DIR = TEST_DIR.parent
if str(ROBOT_MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(ROBOT_MONITOR_DIR))

from prelabel_pipeline import run_state


class PrelabelRunStateTest(unittest.TestCase):
    def test_serialize_run_redacts_paths_and_computes_ownership(self):
        run = {
            "status": "running",
            "task_prefix": "demo",
            "input_dirs": ["/media/sdc2/lhx/MPformer/foo"],
            "created_at": "2026-04-29T12:00:00",
            "finished_at": None,
            "logs": [{"type": "log", "msg": "hello"}],
            "result": None,
            "owner_token": "token-1",
        }
        data = run_state.serialize_run("abcdef123456", run, expose_paths=False, include_logs=True, owner_token="token-1")
        self.assertEqual(data["input_dirs"], ["foo"])
        self.assertTrue(data["owned_by_client"])
        self.assertNotIn("owner_token", data)
        self.assertEqual(data["logs"], [{"type": "log", "msg": "hello"}])

    def test_run_json_path_rejects_invalid_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                run_state.run_json_path(Path(tmp), "../bad")

    def test_upload_metadata_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            upload_dir = Path(tmp)
            run_state.write_upload_meta(upload_dir, "owner-token")
            self.assertEqual(run_state.read_upload_owner(upload_dir), "owner-token")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /media/sdc2/lhx/perception_process/perception_streaming
python3 -m unittest robot_monitor.tests.test_prelabel_run_state -v
```

Expected: FAIL because `run_state.py` does not exist.

- [ ] **Step 3: Implement run state**

Create `run_state.py` with:

- `runs: dict = {}`
- `runs_lock = threading.RLock()`
- `make_runtime_run(...)`
- `serialize_run(...)`
- `save_run(...)`
- `load_history(...)`
- `init_runs_from_history(...)`
- `cleanup_old_runs(...)`
- `cleanup_old_uploads(...)`
- `run_json_path(runs_dir, run_id)`
- `write_upload_meta(upload_dir, owner_token)`
- `read_upload_owner(upload_dir)`

Implementation notes:

```python
def serialize_run(run_id, run_data, expose_paths=True, include_logs=False, owner_token=""):
    input_dirs = run_data.get("input_dirs", [])
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
```

Never serialize `owner_token`.

- [ ] **Step 4: Run run state tests**

```bash
cd /media/sdc2/lhx/perception_process/perception_streaming
python3 -m unittest robot_monitor.tests.test_prelabel_run_state -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
cd /media/sdc2/lhx/perception_process
git add perception_streaming/robot_monitor/prelabel_pipeline/run_state.py perception_streaming/robot_monitor/tests/test_prelabel_run_state.py
git commit -m "feat: add prelabel run state"
```

## Task 3: Core Pipeline Port

**Files:**
- Create: `perception_streaming/robot_monitor/prelabel_pipeline/core.py`
- Test: `perception_streaming/robot_monitor/tests/test_prelabel_core.py`

- [ ] **Step 1: Write failing core tests**

Create `test_prelabel_core.py`:

```python
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

TEST_DIR = Path(__file__).resolve().parent
ROBOT_MONITOR_DIR = TEST_DIR.parent
if str(ROBOT_MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(ROBOT_MONITOR_DIR))

from prelabel_pipeline import core


class PrelabelCoreTest(unittest.TestCase):
    def test_build_predict_cmd_keeps_opts_last(self):
        cfg = {"demo_dir": "/demo", "config": "/cfg.yaml", "weights": "/w.pth", "min_area": 50, "smooth_contours": True, "fill_holes": True}
        docker_cmd, inner = core.build_predict_cmd("/input", "/output", 123, cfg, "MPformer")
        self.assertEqual(docker_cmd[:3], ["docker", "exec", "MPformer"])
        self.assertTrue(inner.endswith("--opts MODEL.WEIGHTS /w.pth"))

    def test_cuda_error_detection(self):
        self.assertTrue(core.is_cuda_error(["RuntimeError: CUDA error"]))
        self.assertFalse(core.is_cuda_error(["ordinary failure"]))

    def test_label_mapping_is_module_local(self):
        mapping = core.build_label_mapping()
        self.assertIn("lawn", mapping)

    def test_upload_only_emits_skipped_steps(self):
        cfg = {
            "segment_size": 1000,
            "model": {"min_area": 50},
            "cvat_servers": [{"id": "local", "host": "localhost", "port": 8080, "user": "u", "password": "p"}],
        }
        logs = []
        with patch.object(core, "step1_upload", return_value=(Mock(), 10, 20)), \
             patch.object(core, "step5_assign", return_value=None):
            result = core.run_pipeline("rid", "task", ["/tmp/images"], {"skip_steps": [2, 3, 4]}, cfg, logs.append)
        self.assertEqual(result[0]["status"], "success")
        skip_events = [entry for entry in logs if isinstance(entry, dict) and entry.get("type") == "step_skip"]
        self.assertEqual([e["step"] for e in skip_events], [2, 3, 4])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /media/sdc2/lhx/perception_process/perception_streaming
python3 -m unittest robot_monitor.tests.test_prelabel_core -v
```

Expected: FAIL because `core.py` does not exist.

- [ ] **Step 3: Port core implementation**

Copy from `/media/sdc2/lhx/pipeline/pipeline_core.py` into `core.py`, then adapt:

- Rename `_build_predict_cmd` to public `build_predict_cmd` or export a wrapper for tests.
- Rename `_is_cuda_error` to public `is_cuda_error` or export a wrapper for tests.
- Replace module-level `sys.path.insert(0, "/media/sdc2/lhx")`.
- Implement local label conversion:
  - Option A: copy the minimal `convert_labels_in_xml` logic into `core.py`.
  - Option B: create `label_convert.py` in this package and import it.
- `build_label_mapping()` reads `labels_mapping.yaml` from `Path(__file__).parent`.
- Preserve CVAT SDK behavior, REST assignment, session cache lock, Docker restart diagnostics, GPU semaphore, serial skip events, and full five-step flow.
- Keep `requests.Session.trust_env = False`.

- [ ] **Step 4: Run core tests**

```bash
cd /media/sdc2/lhx/perception_process/perception_streaming
python3 -m unittest robot_monitor.tests.test_prelabel_core -v
```

Expected: PASS.

- [ ] **Step 5: Run import compile for backend package**

```bash
cd /media/sdc2/lhx/perception_process/perception_streaming
python3 -m py_compile robot_monitor/prelabel_pipeline/*.py
```

Expected: no output and exit code 0.

- [ ] **Step 6: Commit Task 3**

```bash
cd /media/sdc2/lhx/perception_process
git add perception_streaming/robot_monitor/prelabel_pipeline/core.py perception_streaming/robot_monitor/tests/test_prelabel_core.py
git commit -m "feat: port prelabel pipeline core"
```

## Task 4: `/prelabel` Routes, Upload, SSE, And Dispatch

**Files:**
- Create: `perception_streaming/robot_monitor/prelabel_pipeline/routes.py`
- Modify: `perception_streaming/robot_monitor/offline_server.py`
- Modify: `perception_streaming/vite.config.ts`
- Test: `perception_streaming/robot_monitor/tests/test_prelabel_routes.py`

- [ ] **Step 1: Write failing route tests**

Create `test_prelabel_routes.py` using a fake handler object:

```python
import sys
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

TEST_DIR = Path(__file__).resolve().parent
ROBOT_MONITOR_DIR = TEST_DIR.parent
if str(ROBOT_MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(ROBOT_MONITOR_DIR))

from prelabel_pipeline import routes, run_state


class FakeHandler:
    def __init__(self, body=b"", headers=None):
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.headers = headers or {}
        self.status = None
        self.sent_headers = []

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.sent_headers.append((key, value))

    def end_headers(self):
        pass


class PrelabelRoutesTest(unittest.TestCase):
    def setUp(self):
        run_state.runs.clear()

    def test_runs_redacts_owner_token_and_sets_owned_by_client(self):
        run_state.runs["abcdef123456"] = {
            "status": "running",
            "task_prefix": "demo",
            "input_dirs": ["/root/images"],
            "created_at": "2026-04-29T12:00:00",
            "finished_at": None,
            "logs": [],
            "result": None,
            "owner_token": "token",
            "done": False,
        }
        handler = FakeHandler(headers={"X-Prelabel-Owner-Token": "token"})
        routes.handle(handler, SimpleNamespace(path="/prelabel/runs", query=""))
        payload = json.loads(handler.wfile.getvalue().decode("utf-8"))
        self.assertTrue(payload[0]["owned_by_client"])
        self.assertNotIn("owner_token", payload[0])

    def test_cancel_rejects_wrong_token(self):
        run_state.runs["abcdef123456"] = {
            "status": "running",
            "owner_token": "token",
            "cancel": False,
            "proc": None,
            "done": False,
        }
        body = json.dumps({"token": "wrong"}).encode("utf-8")
        handler = FakeHandler(body=body, headers={"Content-Length": str(len(body))})
        routes.handle(handler, SimpleNamespace(path="/prelabel/runs/abcdef123456/cancel", query=""))
        self.assertEqual(handler.status, 403)

    def test_sse_stream_writes_existing_logs_and_null(self):
        event = threading.Event()
        event.set()
        run_state.runs["abcdef123456"] = {
            "status": "success",
            "logs": [{"type": "log", "msg": "hello"}],
            "event": event,
            "done": True,
            "owner_token": "",
        }
        handler = FakeHandler()
        routes.handle(handler, SimpleNamespace(path="/prelabel/stream/abcdef123456", query=""))
        out = handler.wfile.getvalue().decode("utf-8")
        self.assertIn('"hello"', out)
        self.assertIn("data: null", out)
```

- [ ] **Step 2: Run route tests to verify they fail**

```bash
cd /media/sdc2/lhx/perception_process/perception_streaming
python3 -m unittest robot_monitor.tests.test_prelabel_routes -v
```

Expected: FAIL because routes are missing.

- [ ] **Step 3: Implement `routes.py` JSON helpers and route dispatch**

Implement:

- `handle(handler, parsed)` main dispatcher.
- `_send_json(handler, payload, status=200)`.
- `_read_json(handler)`.
- `_owner_token_from_header(handler)`.
- Route parsing for all `/prelabel` paths.
- Use `run_state.runs_lock` around shared state reads/writes.
- Never return or log `owner_token`.

- [ ] **Step 4: Implement upload route**

Because `BaseHTTPRequestHandler` has no Flask multipart parser, use stdlib `cgi.FieldStorage` for first implementation:

```python
form = cgi.FieldStorage(fp=handler.rfile, headers=handler.headers, environ={
    "REQUEST_METHOD": "POST",
    "CONTENT_TYPE": handler.headers.get("Content-Type", ""),
})
```

Rules:

- Require `owner_token`.
- Validate continuation `upload_id` with `validate_upload_id`.
- Store upload metadata in `.upload_meta.json`.
- Reject continuation token mismatch.
- Save files with `safe_filename` and `unique_path`.
- Return `count`, `total_count`, `skipped`.

- [ ] **Step 5: Implement run start route**

Implement background thread equivalent to source Flask `_pipeline_thread`:

- Build run id with `uuid.uuid4().hex[:12]`.
- Validate server dirs with `resolve_under`.
- Validate `upload_id` and owner token before using upload dir.
- Create run dict with `event`, `logs`, `done`, `cancel`, `proc`, `owner_token`.
- Start daemon thread calling `core.run_pipeline`.
- Inject:
  - `cancel_fn`
  - `set_proc_fn`
  - `clear_proc_fn`
  - `gpu_semaphore`
  - `pipeline_semaphore`
- Save run and clean upload dir in `finally`.

- [ ] **Step 6: Implement SSE route**

Implement per spec:

- Threaded server assumption.
- Copy pending logs under lock, release lock, write `data: ...\n\n`, flush.
- Catch `BrokenPipeError`, `ConnectionResetError`, `OSError`.
- Send `data: null\n\n` after done.
- Use `event.wait(timeout=25)`.
- Multiple clients use independent `sent` indexes.

- [ ] **Step 7: Implement remaining routes**

Implement:

- runs list/detail/delete with ownership header.
- cancel with token check and proc kill.
- container-status and restart-container with active run skip.
- cvat-users and cvat-servers.
- settings PATCH and cache clear.
- browse with `resolve_under`.

- [ ] **Step 8: Wire `offline_server.py` dispatch**

At imports:

```python
from prelabel_pipeline import routes as prelabel_routes
```

In `do_GET`, `do_POST`, `do_DELETE`, and `do_PATCH` support:

```python
if path.startswith("/prelabel/"):
    prelabel_routes.handle(self, parsed)
    return
```

If `OfflineHandler` does not yet implement `do_DELETE` or `do_PATCH`, add them with the same dispatch-first pattern and 404 fallback.

- [ ] **Step 9: Add Vite proxy for `/prelabel`**

In `perception_streaming/vite.config.ts`, add a proxy entry beside `/offline`:

```ts
'/prelabel': {
  target: 'http://localhost:8769',
  changeOrigin: true,
  timeout: 300000,
  proxyTimeout: 300000,
},
```

Expected: frontend calls to `http://localhost:5173/prelabel/...` reach `offline_server.py`. Do not manually call `res.writeHead()` or `proxyRes.pipe(res)` unless `selfHandleResponse: true` is also set and the implementation fully owns response forwarding; the normal proxy path should stream SSE without duplicate writes.

- [ ] **Step 10: Run route tests and compile**

```bash
cd /media/sdc2/lhx/perception_process/perception_streaming
python3 -m unittest robot_monitor.tests.test_prelabel_routes -v
python3 -m py_compile robot_monitor/offline_server.py robot_monitor/prelabel_pipeline/*.py
npm run build
```

Expected: PASS, compile exit 0, frontend build PASS.

- [ ] **Step 11: Commit Task 4**

```bash
cd /media/sdc2/lhx/perception_process
git add perception_streaming/robot_monitor/prelabel_pipeline/routes.py perception_streaming/robot_monitor/offline_server.py perception_streaming/vite.config.ts perception_streaming/robot_monitor/tests/test_prelabel_routes.py
git commit -m "feat: expose prelabel backend routes"
```

## Task 5: Migration Bug Fixes And Legacy Path Hardening

**Files:**
- Modify: `perception_streaming/robot_monitor/offline_server.py`
- Modify: `perception_streaming/robot_monitor/config_loader.py`
- Modify: `perception_streaming/restart_services.sh`
- Modify: `perception_streaming/src/composables/useObstacleMonitor.ts`
- Modify: `perception_streaming/src/components/PointCloudPanel.vue`
- Modify: `01_evb/run_evb_remote.sh`
- Test: `perception_streaming/robot_monitor/tests/test_offline_server.py`

- [ ] **Step 1: Add failing tests for legacy path hardening and stop state**

Extend `test_offline_server.py` with import-safe unit tests:

```python
class OfflineServerMigrationFixTest(unittest.TestCase):
    def test_build_file_tree_rejects_or_skips_hidden_and_build_dirs(self):
        # keep existing behavior covered before adding root validation helpers
        ...

    def test_legacy_allowed_roots_reject_outside_path(self):
        from offline_server import _resolve_legacy_path
        with tempfile.TemporaryDirectory() as root_tmp, tempfile.TemporaryDirectory() as other_tmp:
            with self.assertRaises(ValueError):
                _resolve_legacy_path(other_tmp, [Path(root_tmp)])
```

If `offline_server.py` helpers are awkward to test without request objects, create pure helper functions first and test those.

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /media/sdc2/lhx/perception_process/perception_streaming
python3 -m unittest robot_monitor.tests.test_offline_server -v
```

Expected: FAIL for missing helper or behavior.

- [ ] **Step 3: Fix `_current_proc` for offline Docker stop**

In `run_offline_test`:

- Declare `global _last_result, _running, _current_proc`.
- Set `_current_proc = proc` immediately after `subprocess.Popen`.
- In `finally`, clear `_current_proc` if it is this proc.
- In `/offline/stop`, if `_current_proc` exists terminate/kill; also run `docker stop perception_offline_runner` as fallback.

- [ ] **Step 4: Harden legacy local file routes**

Add pure helper:

```python
def _resolve_legacy_path(path: str, roots: list[str | Path]) -> Path:
    return resolve_under(path, [Path(root) for root in roots])
```

Use it for:

- `/offline/local_file`
- `/offline/extracted_image`
- `/ros2deploy/list_dir`
- `/ros2deploy/file_content`

Allowed roots match the spec table.

- [ ] **Step 5: Fix restart script path**

Update `perception_streaming/restart_services.sh`:

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
```

Remove old absolute `/home/youfeng/...` assumptions.

- [ ] **Step 6: Fix config loader relative SSH key resolution**

In `config_loader.py`, ensure relative `ssh_key_path` is resolved from `CONF_DIR`. Also allow env overrides:

```python
if os.environ.get("SSH_KEY"):
    config["ssh_key_path"] = os.environ["SSH_KEY"]
if os.environ.get("ROBOT_HOST"):
    config["ssh_host"] = os.environ["ROBOT_HOST"]
```

- [ ] **Step 7: Fix remote browser WebSocket URLs**

In `useObstacleMonitor.ts`, replace hard-coded localhost with:

```ts
const wsHost = location.hostname || 'localhost'
const ws = new WebSocket(`ws://${wsHost}:8765`)
```

In `PointCloudPanel.vue`, connect to `8766` proxy:

```ts
const wsHost = location.hostname || 'localhost'
const wsUrl = `ws://${wsHost}:8766`
```

- [ ] **Step 8: Fix EVB script path**

In `01_evb/run_evb_remote.sh`, compute root from script:

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
```

Use `$PROJECT_ROOT/01_evb/...` for volume sources.

- [ ] **Step 9: Run backend and frontend checks**

```bash
cd /media/sdc2/lhx/perception_process/perception_streaming
python3 -m unittest robot_monitor.tests.test_offline_server -v
python3 -m py_compile robot_monitor/offline_server.py robot_monitor/config_loader.py
npm run build
```

Expected: tests PASS, compile PASS, build PASS.

- [ ] **Step 10: Commit Task 5**

```bash
cd /media/sdc2/lhx/perception_process
git add perception_streaming/robot_monitor/offline_server.py perception_streaming/robot_monitor/config_loader.py perception_streaming/restart_services.sh perception_streaming/src/composables/useObstacleMonitor.ts perception_streaming/src/components/PointCloudPanel.vue perception_streaming/robot_monitor/tests/test_offline_server.py 01_evb/run_evb_remote.sh
git commit -m "fix: harden migrated paths and stop handling"
```

## Task 6: Frontend Prelabel Panel API Client And Tab Shell

**Files:**
- Create: `perception_streaming/src/components/PrelabelPipelinePanel.vue`
- Modify: `perception_streaming/src/App.vue`

- [ ] **Step 1: Add minimal panel and App tab**

In `App.vue`:

- Add `prelabel` to the union type.
- Import `PrelabelPipelinePanel`.
- Add tab button beside `双目分析`:

```vue
<button
  class="tab-btn"
  :class="{ active: activeTab === 'prelabel' }"
  @click="activeTab = 'prelabel'"
>预标注上传</button>
```

- Add content block:

```vue
<div v-show="activeTab === 'prelabel'" class="app-content bag-tab">
  <PrelabelPipelinePanel />
</div>
```

Create panel with a minimal template that renders toolbar, source controls, action buttons, log area, and history area.

- [ ] **Step 2: Run build to verify shell compiles**

```bash
cd /media/sdc2/lhx/perception_process/perception_streaming
npm run build
```

Expected: PASS.

- [ ] **Step 3: Implement API helpers and state**

Inside `PrelabelPipelinePanel.vue`, implement:

- `PRELABEL_CLIENT_TOKEN` generation in localStorage.
- `apiJson<T>(url, options)` helper.
  - Do not force `Content-Type: application/json` when `options.body` is `FormData`; let the browser set multipart boundaries.
- State refs:
  - `runStatus`
  - `taskPrefix`
  - `sourceMode`
  - `serverDirs`
  - `selectedFiles`
  - `uploadId`
  - `cvatServers`
  - `selectedServerId`
  - `cvatUsers`
  - `assigneeId`
  - `minArea`
  - `segmentSize`
  - `serialMode`
  - `runs`
  - `activeRunId`
  - `logs`
  - `steps`

- [ ] **Step 4: Implement server/user loading and settings**

Implement:

- `loadCvatServers()`
- `loadCvatUsers(force = false)`
- `saveServerSettings(server)`
- Watch `selectedServerId` and reload users.

- [ ] **Step 5: Implement run history and ownership**

Implement:

- `loadRuns()` sends `X-Prelabel-Owner-Token`.
- `loadRunDetail(runId)` sends `X-Prelabel-Owner-Token`.
- Hide Stop when `owned_by_client=false`.
- Auto reconnect to newest running owned run.

- [ ] **Step 6: Run build**

```bash
cd /media/sdc2/lhx/perception_process/perception_streaming
npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit Task 6**

```bash
cd /media/sdc2/lhx/perception_process
git add perception_streaming/src/App.vue perception_streaming/src/components/PrelabelPipelinePanel.vue
git commit -m "feat: add prelabel tab shell"
```

## Task 7: Frontend Upload, Run Control, SSE Timeline, And History UI

**Files:**
- Modify: `perception_streaming/src/components/PrelabelPipelinePanel.vue`

- [ ] **Step 1: Implement upload selection and batching**

Add template controls:

- Source mode segmented buttons.
- Server directory rows with add/remove.
- File input `multiple`.
- Folder input `webkitdirectory`.

Implement:

```ts
const BATCH_SIZE = 200

async function uploadSelectedFiles() {
  uploadId.value = ''
  let saved = 0
  for (let i = 0; i < selectedFiles.value.length; i += BATCH_SIZE) {
    const batch = selectedFiles.value.slice(i, i + BATCH_SIZE)
    const form = new FormData()
    for (const file of batch) form.append('files', file)
    form.append('owner_token', clientToken)
    if (uploadId.value) form.append('upload_id', uploadId.value)
    const result = await apiJson<UploadResponse>('/prelabel/upload', { method: 'POST', body: form })
    uploadId.value = result.upload_id
    saved = result.total_count
    uploadProgress.value = Math.round((Math.min(i + batch.length, selectedFiles.value.length) / selectedFiles.value.length) * 100)
  }
}
```

- [ ] **Step 2: Implement run start buttons**

Implement:

- `startRun('full')` sends no `skip_steps`.
- `startRun('uploadOnly')` sends `[2, 3, 4]`.
- Upload mode uploads first if `uploadId` is missing.
- Include `owner_token: clientToken`.
- Disable buttons while uploading/starting/running.

- [ ] **Step 3: Implement SSE connection**

Implement:

- `connectStream(runId)`
- On `step_start`, `step_done`, `step_skip`, update step state.
- On plain `log`, append log.
- On `pipeline_done`, refresh runs.
- On `data: null`, close stream and refresh run detail.

- [ ] **Step 4: Implement stop and delete**

Implement:

- `cancelRun(run)` sends `POST /prelabel/runs/<id>/cancel` with `{token: clientToken}`.
- Hide or disable Stop when not owned.
- Delete selected histories via `DELETE`.

- [ ] **Step 5: Implement container status and browse**

Implement:

- Poll `GET /prelabel/container-status` every 60 seconds while mounted.
- Manual restart calls `POST /prelabel/restart-container`.
- Browse dialog or compact path browser calls `/prelabel/browse?path=...`.

- [ ] **Step 6: Polish responsive dark UI**

Use existing `sa2-*` visual language where practical:

- Compact toolbar.
- Stable fixed-height log/history panels.
- Step indicator with pending/active/done/skipped/failed.
- No nested cards.
- Text must not overflow small controls.

- [ ] **Step 7: Run build**

```bash
cd /media/sdc2/lhx/perception_process/perception_streaming
npm run build
```

Expected: PASS.

- [ ] **Step 8: Commit Task 7**

```bash
cd /media/sdc2/lhx/perception_process
git add perception_streaming/src/components/PrelabelPipelinePanel.vue
git commit -m "feat: complete prelabel panel workflow"
```

## Task 8: Full Verification And Smoke Testing

**Files:**
- No planned source changes unless verification exposes bugs.

- [ ] **Step 1: Run full Python unit tests**

```bash
cd /media/sdc2/lhx/perception_process/perception_streaming
python3 -m unittest discover robot_monitor/tests -v
```

Expected: PASS.

- [ ] **Step 2: Run TypeScript/Vite build**

```bash
cd /media/sdc2/lhx/perception_process/perception_streaming
npm run build
```

Expected: PASS.

- [ ] **Step 3: Compile backend files**

```bash
cd /media/sdc2/lhx/perception_process/perception_streaming
python3 -m py_compile robot_monitor/offline_server.py robot_monitor/config_loader.py robot_monitor/prelabel_pipeline/*.py
```

Expected: PASS.

- [ ] **Step 4: Start dev server**

```bash
cd /media/sdc2/lhx/perception_process/perception_streaming
./start.sh
```

Expected:

- Vite starts on `http://localhost:5173`.
- Offline server starts on `localhost:8769`.
- Existing tabs still render.
- New `预标注上传` tab appears beside `双目分析`.

- [ ] **Step 5: Smoke `/prelabel` JSON endpoints**

In another shell:

```bash
curl -s http://localhost:5173/prelabel/cvat-servers
curl -s http://localhost:5173/prelabel/runs
curl -s http://localhost:5173/prelabel/container-status
```

Expected:

- CVAT servers return without credentials.
- Runs returns JSON list.
- Container status returns JSON even if Docker/GPU has an error.

- [ ] **Step 6: Smoke upload-only run**

Use a tiny image directory under `/media/sdc2/lhx/MPformer` or upload 1-2 local images through UI:

- Start upload-only.
- Verify steps 2-4 are marked skipped.
- Verify CVAT task URL appears.
- Cancel during a waiting/running state if safe to do so.

- [ ] **Step 7: Smoke full five-step run**

Use a small image directory:

- Start full pipeline.
- Verify Step 1-5 events in SSE.
- Verify CVAT task link opens.
- Verify run appears in history.

- [ ] **Step 8: Stop dev server cleanly**

Stop `./start.sh` session with Ctrl-C and confirm no needed sessions are left running.

- [ ] **Step 9: Final status check**

```bash
cd /media/sdc2/lhx/perception_process
git status --short
```

Expected:

- Only intentional source changes are present.
- Existing untracked data directories may still appear; do not stage them.

## Notes For Implementers

- Do not stage large debug data, `node_modules`, `dist`, `logs`, or `.omx`.
- Do not expose CVAT credentials or `owner_token` in API responses or logs.
- Preserve existing unrelated behavior in `offline_server.py`; keep prelabel code in the new package.
- When touching files that already have unrelated user changes, read the local diff first and avoid reverting them.
