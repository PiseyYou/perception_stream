# Prelabel Pipeline Integration Design

Date: 2026-04-29
Project: `/media/sdc2/lhx/perception_process`
Source module: `/media/sdc2/lhx/pipeline`
Target app: `/media/sdc2/lhx/perception_process/perception_streaming`

## Goal

Integrate the complete prelabel upload pipeline into `perception_process` as a native module. The migrated feature must preserve the existing `pipeline` capabilities:

- local image and folder upload with chunked upload progress
- server directory selection and browsing
- five-step flow: upload images to CVAT, AI prelabel in Docker, label rename, import annotations to CVAT, assign task
- "upload to CVAT only" mode via skipped steps
- CVAT server selection and host/port hot update
- CVAT user list loading
- run history, live SSE logs, cancellation, and deletion
- Docker container and GPU status, manual restart, and CUDA diagnostics

The new UI entry will be placed in the top tab bar beside `双目分析`, matching the empty slot shown in the current app screenshot.

## Current Context

`pipeline` is a Flask app with a single-page Bootstrap frontend and a mature Python backend:

- `app.py` owns HTTP routes, run threads, GPU/pipeline semaphores, upload handling, and SSE.
- `pipeline_core.py` owns the five pipeline steps and CVAT/Docker integration.
- `config_manager.py` injects CVAT credentials from environment variables.
- `run_state.py` persists run JSON files and cleans old run/upload data.
- `labels_mapping.yaml` is the label mapping source of truth.

`perception_process/perception_streaming` is a Vue 3 + TypeScript app backed by a custom Python `BaseHTTPRequestHandler` service:

- frontend entry: `src/App.vue`
- backend service: `robot_monitor/offline_server.py`, port `8769`
- Vite proxy routes `/offline`, `/api/extract`, and `/ros2deploy` to `8769`
- existing backend routes already use HTTP JSON and SSE without Flask

Because `perception_streaming` already centralizes backend work in `offline_server.py`, the integration should not add a second Flask service unless there is no practical alternative.

## Recommended Architecture

Use a native module under `robot_monitor` and a Vue panel under `src/components`.

New backend package:

```text
perception_streaming/robot_monitor/prelabel_pipeline/
├── __init__.py
├── config_manager.py
├── core.py
├── labels_mapping.yaml
├── prelabel_config.yaml
├── routes.py
└── run_state.py
```

Responsibilities:

- `core.py`: migrated and lightly adapted `pipeline_core.py`.
- `config_manager.py`: load/save `prelabel_config.yaml`, inject CVAT credentials.
- `run_state.py`: maintain run state, persist JSON history, clean old uploads.
- `routes.py`: expose handler functions used by `offline_server.py`.
- `labels_mapping.yaml`: keep label mapping local to the module.
- `prelabel_config.yaml`: prelabel-specific config, not mixed into unrelated SSH or offline-analysis config.

`offline_server.py` should only dispatch requests:

```python
if path.startswith("/prelabel/"):
    return prelabel_routes.handle(self, parsed)
```

This keeps the already-large `offline_server.py` from absorbing another several hundred lines of business logic.

## API Design

All migrated endpoints use the `/prelabel` namespace to avoid collisions with existing `/offline`, `/api`, and `/ros2deploy` routes.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/prelabel/upload` | Upload image batches. |
| POST | `/prelabel/run` | Start a pipeline run. |
| GET | `/prelabel/stream/<run_id>` | SSE live logs for one run. |
| GET | `/prelabel/runs` | List historical runs. |
| GET | `/prelabel/runs/<run_id>` | Get run detail and logs. |
| DELETE | `/prelabel/runs/<run_id>` | Delete a run record. |
| POST | `/prelabel/runs/<run_id>/cancel` | Cancel a running job and kill its subprocess. |
| GET | `/prelabel/container-status` | Check Docker container and GPU status. |
| POST | `/prelabel/restart-container` | Restart Docker container; `mode=auto` skips active runs. |
| GET | `/prelabel/cvat-users` | List CVAT users for selected server. |
| GET | `/prelabel/cvat-servers` | List configured CVAT servers without credentials. |
| PATCH | `/prelabel/settings/cvat-server/<id>` | Hot-update CVAT host/port. |
| GET | `/prelabel/browse?path=...` | Browse whitelisted server directories. |

Route behavior should match the existing Flask API payloads where possible so the current frontend logic can be ported with minimal semantic change.

### API Contract

Common JSON error response:

```json
{"ok": false, "error": "human readable message"}
```

Successful JSON responses include `ok: true` unless the legacy Flask response already has a stable shape, such as `{"run_id": "..."}`.

`POST /prelabel/upload`

- Request: `multipart/form-data`
- Fields:
  - `files`: one or more image files.
  - `folder_name`: optional folder-name hint from folder upload.
  - `upload_id`: optional existing upload id for chunk continuation.
  - `owner_token`: required for the first batch; required and must match for continuation batches.
- File handling:
  - Accept extensions: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff`, `.tif`.
  - Sanitize every basename with a `secure_filename` equivalent.
  - Ignore directory components from browser `webkitdirectory`; this module stores a flat image directory, matching the current pipeline.
  - If `upload_id` is present, append files into the existing upload directory.
  - `upload_id` is server-generated, opaque, and must match `^[a-zA-Z0-9_-]{16,64}$`.
  - Generate ids with random entropy, for example `<safe_hint>_<timestamp>_<uuid8>`, not a predictable folder name alone.
  - The upload directory is always `upload_dir / upload_id`; never join user-provided path fragments.
  - If a sanitized filename already exists, preserve both files by suffixing the new name, for example `image_2.jpg`.
- Response:

```json
{
  "upload_id": "folder_0429_153012_a1b2c3d4",
  "upload_dir": "/media/sdc2/lhx/MPformer/pipeline_uploads/folder_0429_153012_a1b2c3d4",
  "count": 200,
  "total_count": 400,
  "skipped": ["bad.txt"]
}
```

- `count` is the number of files saved in this request.
- `total_count` is the cumulative saved image count in the upload directory.
- `skipped` contains files rejected in this request only.
- Errors:
  - `400`: no files, missing owner token, invalid `upload_id`, token mismatch, no accepted image files.
  - `413`: request too large if server-level body limit is exceeded.

`POST /prelabel/run`

- Request JSON:

```json
{
  "task_prefix": "demo_305",
  "input_dirs": ["/media/sdc2/lhx/MPformer/..."],
  "upload_id": "folder_0429_153012",
  "assignee_id": 1,
  "min_area": 50,
  "segment_size": 1000,
  "cvat_server_id": "remote",
  "skip_steps": [2, 3, 4],
  "serial_mode": false,
  "owner_token": "client-token"
}
```

- Rules:
  - `task_prefix` is required and non-empty.
  - At least one validated `input_dirs` entry or a valid `upload_id` is required.
  - Server directory inputs must resolve under the configured browse roots.
  - `skip_steps: [2, 3, 4]` means upload-only mode; Step 1 and optional Step 5 still run.
  - `owner_token` is persisted with the run and required for cancellation when non-empty.
- Response: `{"run_id": "12hexchars"}`
- Errors:
  - `400`: invalid task prefix, no inputs, invalid upload id, path outside whitelist.

`GET /prelabel/stream/<run_id>`

- Response headers:
  - `Content-Type: text/event-stream`
  - `Cache-Control: no-cache`
  - `Connection: keep-alive`
  - `X-Accel-Buffering: no`
- Event format: one `data: <json>\n\n` per log item.
- Log event examples:

```json
{"time":"15:30:12","type":"log","level":"info","msg":"..."}
{"time":"15:30:13","type":"step_start","step":2,"msg":"开始 AI 预标注"}
{"time":"15:30:14","type":"step_done","step":2,"status":"success","msg":"..."}
{"time":"15:30:15","type":"step_skip","step":3,"msg":"已跳过标签转换"}
{"time":"15:30:16","type":"pipeline_done","status":"success","dir_count":1,"success_count":1,"msg":"..."}
```

- Completion sentinel: send `data: null\n\n` after the run is done.
- Heartbeat: if no logs arrive for 25 seconds, the handler may send `: heartbeat\n\n` or continue waiting; the frontend must tolerate either behavior.
- Errors:
  - `404`: unknown `run_id`.

`GET /prelabel/runs`

- Request header:
  - `X-Prelabel-Owner-Token`: optional client token used only to compute ownership.
- Response: list of run summaries sorted by `created_at` descending.
- Summaries redact full input paths to basenames by default.
- Each summary includes `owned_by_client: true|false`.
- `owner_token` is never returned.
- `owner_token` must not be written to logs, SSE events, error responses, or frontend-visible history.

`GET /prelabel/runs/<run_id>`

- Request header:
  - `X-Prelabel-Owner-Token`: optional client token used only to compute ownership.
- Response: run detail including logs, with path redaction for API clients.
- Detail includes `owned_by_client: true|false`.
- `owner_token` is never returned.
- Errors: `404` for unknown run.

`DELETE /prelabel/runs/<run_id>`

- Rules:
  - `run_id` must match `^[a-f0-9]{12}$` or a known persisted id.
  - Delete only `data/prelabel_runs/<run_id>.json`.
  - Never accept arbitrary path fragments.
- Response: `{"ok": true}`

`POST /prelabel/runs/<run_id>/cancel`

- Request JSON: `{"token": "client-token"}`
- Rules:
  - If the run has a non-empty `owner_token`, the token must match.
  - Set cancel flag and kill the active subprocess if present.
  - If no subprocess is active, cancellation must still interrupt semaphore waits and later steps.
- Responses:
  - `{"ok": true, "msg": "已立即终止当前步骤"}`
  - `{"ok": true, "msg": "已设置取消标志（无进行中的子进程）"}`
- Errors:
  - `400`: run is not running.
  - `403`: token mismatch.
  - `404`: unknown run.

`GET /prelabel/container-status`

- Response:

```json
{
  "container": "MPformer",
  "container_status": "running",
  "gpu_ok": true,
  "gpu_info": "NVIDIA GeForce RTX 3090, 1234 MiB, 24576 MiB"
}
```

`POST /prelabel/restart-container?mode=manual|auto`

- Rules:
  - `mode=auto` returns `409` and `skipped: true` when a run is active.
  - Manual mode runs CUDA diagnostics and `docker restart`.
- Response:

```json
{"ok": true, "skipped": false, "mode": "manual", "message": "diagnostic log"}
```

`GET /prelabel/cvat-users?server_id=remote`

- Response: `[{ "id": 1, "username": "user", "full_name": "Name" }]`
- Errors:
  - `503`: CVAT connection failure.
  - `500`: credential or API error.

`GET /prelabel/cvat-servers`

- Response: `[{ "id": "remote", "name": "远程服务器", "host": "192.168.55.246", "port": 8080 }]`
- Credentials are never returned.

`PATCH /prelabel/settings/cvat-server/<id>`

- Request JSON: `{"host": "192.168.55.246", "port": 8080}`
- Rules:
  - Only `host` and `port` are writable.
  - Save config without credentials.
  - Clear the CVAT session cache for that server.
- Errors:
  - `404`: unknown server id.

`GET /prelabel/browse?path=/media/sdc2/lhx/MPformer`

- Response: `{"path": "/resolved/path", "dirs": ["/resolved/path/subdir"]}`
- Rules:
  - Resolve symlinks before validation.
  - Only return directories below configured browse roots.
  - Do not return files.
- Errors:
  - `400`: not a directory.
  - `403`: path outside whitelist.

## Frontend Design

Add `src/components/PrelabelPipelinePanel.vue` and extend `src/App.vue`:

- Add `prelabel` to the `activeTab` union.
- Add a tab button labeled `预标注上传` beside `双目分析`.
- Render `<PrelabelPipelinePanel />` in the same `app-content bag-tab` container pattern used by the offline panels.

The panel should preserve the complete pipeline workflow, but use the existing app's visual language:

- compact dark toolbar controls rather than Bootstrap cards
- fixed-height log and history panes that fit under the header
- stable controls that do not resize while progress/status changes
- timeline or step indicators for the five pipeline steps
- local `CLIENT_TOKEN` in `localStorage` for per-device cancellation ownership

Expected frontend sections:

1. Status bar: Docker/GPU status, CVAT server selector, restart action.
2. Task form: task prefix, source mode, assignee, model overrides, segment size, serial mode.
3. Image source:
   - server directories with browse dialog
   - local upload or folder upload with chunked progress
4. Actions: full pipeline, upload-only, stop.
5. Live run view: SSE logs grouped by directory, five-step timeline, CVAT links.
6. History: recent runs, reconnect to active run, delete selected records.

### Frontend State And Field Mapping

Primary state:

```ts
type SourceMode = 'server' | 'upload'
type RunMode = 'full' | 'uploadOnly'
type RunStatus = 'idle' | 'uploading' | 'starting' | 'running' | 'success' | 'failed' | 'cancelled'
```

Form fields and defaults:

| UI field | Default | API mapping |
| --- | --- | --- |
| task prefix | empty or previous localStorage value | `task_prefix` |
| CVAT server | first `/prelabel/cvat-servers` result | `cvat_server_id` |
| CVAT host/port settings | server config | `PATCH /prelabel/settings/cvat-server/<id>` |
| assignee | `null` | `assignee_id` |
| min area | `50` | `min_area` |
| segment size | `1000` | `segment_size` |
| serial mode | `false` | `serial_mode` |
| server directories | one or more paths | `input_dirs` |
| upload id | response from upload | `upload_id` |
| client token | localStorage `PRELABEL_CLIENT_TOKEN` | `owner_token`, cancel `token` |

Button rules:

- Full pipeline button is enabled when `task_prefix` is non-empty and there is either at least one server directory or a completed upload id.
- Upload-only button sends `skip_steps: [2, 3, 4]`.
- Stop button is visible only for the active run when this browser owns the `owner_token`.
- During `uploading`, run buttons are disabled.
- During `running`, source fields and model fields are disabled for the active run.

Upload behavior:

- The frontend uploads files in batches of 200.
- The first batch omits `upload_id`; later batches pass the returned `upload_id`.
- Progress is `uploaded_files / total_files`.
- Browser folder uploads may expose relative paths, but only basenames are sent to the backend, matching current pipeline behavior.

CVAT server/user coupling:

- On server selection change, reload `/prelabel/cvat-users?server_id=<id>` with a cache bypass.
- Clear invalid `assignee_id` if the selected user no longer exists on the new server.
- Host/port edits call `PATCH`; after success, reload servers and users.

SSE to UI mapping:

- `step_start`: mark step active.
- `step_done` with success: mark step done.
- `step_done` with failed: mark step failed and mark run failed.
- `step_skip`: mark step skipped.
- `pipeline_done`: update summary and refresh history.
- plain `log`: append to the active directory log pane.
- `data: null`: close EventSource and refresh run detail.

History behavior:

- On panel mount, call `/prelabel/runs`.
- Send `X-Prelabel-Owner-Token: <PRELABEL_CLIENT_TOKEN>` when loading runs and run detail.
- If a run has `status=running` and `owned_by_client=true`, show Stop and automatically reconnect to the newest active run owned by this browser token.
- If a run has `status=running` and `owned_by_client=false`, allow viewing/reconnecting logs but hide Stop.
- Delete selected rows with `DELETE /prelabel/runs/<id>` and summarize partial failures.

Feature parity checklist from the old pipeline page:

- local file upload: required
- local folder upload: required
- drag/drop upload: preferred, but not blocking for first implementation if file/folder selectors work
- server directory browse: required
- full pipeline and upload-only buttons: required
- five-step visual progress: required
- grouped live logs: required
- active run cancellation: required
- CVAT server/user settings: required
- container status and restart: required
- run history and deletion: required

## Data Flow

```text
Vue PrelabelPipelinePanel
  -> POST /prelabel/upload
  -> POST /prelabel/run
  -> EventSource /prelabel/stream/<run_id>

offline_server.py
  -> prelabel_pipeline.routes
  -> run_state.runs + background Thread
  -> core.run_pipeline
  -> CVAT SDK / CVAT REST / docker exec MPformer

outputs:
  -> CVAT task URL
  -> run JSON history
  -> SSE logs and step events
```

## Path And Migration Rules

The migrated module must not depend on `/media/sdc2/lhx/pipeline` at runtime.

Allowed external runtime roots:

- `/media/sdc2/lhx/perception_process/perception_streaming`: current project root.
- `/media/sdc2/lhx/MPformer`: MPformer assets and Docker-mounted image/upload/output paths.
- CVAT server addresses from `prelabel_config.yaml`.

Important path decisions:

- Keep upload temp dirs under `/media/sdc2/lhx/MPformer/pipeline_uploads`, because the MPformer Docker container can read that mount.
- Keep model paths under `/media/sdc2/lhx/MPformer/MP-Former/...` as configurable values.
- Copy or wrap label conversion logic locally so `core.py` does not rely on `sys.path.insert(0, "/media/sdc2/lhx")`.
- Store prelabel run history under `perception_streaming/data/prelabel_runs` or `perception_streaming/robot_monitor/prelabel_pipeline/runs`; prefer `data/prelabel_runs` so runtime state is outside source code.
- Browse roots must be whitelisted, initially `/media/sdc2/lhx/MPformer`.

### Prelabel Config Schema

`prelabel_config.yaml`:

```yaml
cvat_servers:
  - id: "remote"
    name: "远程服务器"
    host: "192.168.55.246"
    port: 8080
    # credentials from CVAT_REMOTE_USER / CVAT_REMOTE_PASSWORD
  - id: "local"
    name: "本机服务器"
    host: "localhost"
    port: 8080
    # credentials from CVAT_LOCAL_USER / CVAT_LOCAL_PASSWORD

docker:
  container: "MPformer"

model:
  demo_dir: "/media/sdc2/lhx/MPformer/MP-Former/demo"
  config: "/media/sdc2/lhx/MPformer/MP-Former/output/config.yaml"
  weights: "/media/sdc2/lhx/MPformer/MP-Former/output/model_1884999.pth"
  min_area: 50
  smooth_contours: true
  fill_holes: true

labels_csv: "/media/sdc2/lhx/MPformer/MP-Former/demo/lhx/labels.csv"
output_base: "/media/sdc2/lhx/MPformer/MP-Former/demo/output"
upload_dir: "/media/sdc2/lhx/MPformer/pipeline_uploads"
runs_dir: "/media/sdc2/lhx/perception_process/perception_streaming/data/prelabel_runs"
browse_roots:
  - "/media/sdc2/lhx/MPformer"
segment_size: 1000
```

Credential environment variables:

- `CVAT_REMOTE_USER`
- `CVAT_REMOTE_PASSWORD`
- `CVAT_LOCAL_USER`
- `CVAT_LOCAL_PASSWORD`

Docker and MPformer details:

- GPU status command: `docker exec MPformer nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader`
- Container status command: `docker inspect --format {{.State.Status}} MPformer`
- Restart command: `docker restart MPformer`
- Inference command template:

```bash
docker exec MPformer bash -c 'cd <model.demo_dir> && python demo_xml_1.py \
  --config-file <model.config> \
  --input <input_dir> \
  --output <output_dir> \
  --job-id <job_id> \
  --min-area <model.min_area> \
  [--smooth-contours] [--fill-holes] \
  --opts MODEL.WEIGHTS <model.weights>'
```

`--opts` must remain last because `demo_xml_1.py` uses `argparse.REMAINDER`.

Host/container path rule:

- Input directories and upload directories must be readable inside the `MPformer` container.
- The supported root is `/media/sdc2/lhx/MPformer`, because that is the known mounted host path.
- Any server directory outside `browse_roots` must be rejected before a run starts.

Five-step file flow:

1. Step 1 creates a CVAT task from validated image files and returns `(client, task_id, job_id)`.
2. Step 2 writes `<output_base>/<dir_name>/annotations.xml`.
3. Step 3 converts labels into `<output_base>/<dir_name>/annotations_cvat.xml` using the module-local `labels_mapping.yaml`.
4. Step 4 imports `annotations_cvat.xml` into CVAT using format `CVAT 1.1`.
5. Step 5 patches task and job assignees through CVAT REST.

CVAT task URL:

```text
http://<selected_server.host>:<selected_server.port>/tasks/<task_id>
```

## Security And Hardening

The integration should include path-hardening fixes found during the GPT-5.5 migration audit.

High-priority fixes to include in implementation:

- Restrict local file serving and directory browsing to explicit roots using `Path.resolve()` or `os.path.realpath()`.
- Reject `..` traversal and unexpected absolute paths in `/offline/local_file`, `/offline/extracted_image`, `/ros2deploy/list_dir`, and `/ros2deploy/file_content`.
- Ensure `/prelabel/browse` follows the same whitelist pattern.
- Do not expose CVAT credentials through any API response or config file write.
- Keep `requests.Session.trust_env = False` for CVAT REST calls to avoid host proxy interference.

Legacy endpoint hardening scope:

| Endpoint | Allowed roots | Reject examples | Expected rejection |
| --- | --- | --- | --- |
| `/offline/local_file?path=...` | `PROJECT_ROOT/data`, `PROJECT_ROOT/select`, current `BAG_DATA_DIR` | `/etc/passwd`, `../../data/conf/bestmow_rsa_202604`, symlink escaping root | `403` |
| `/offline/extracted_image/<dir>/<file>` | `PROJECT_ROOT/data`, current `BAG_DATA_DIR` | absolute dir outside roots, `..`, symlink escaping root | `403` |
| `/ros2deploy/list_dir` | `/media/sdc2/lhx/perception_process`, `/media/sdc2/lhx/MPformer` | `/`, `/home`, `/etc`, `..` outside roots | `403` |
| `/ros2deploy/file_content` | same as `/ros2deploy/list_dir` plus existing file-size cap | SSH private key outside allowed roots, large file, `..` outside roots | `403` for path, existing large-file error for size |

If an existing UI depends on a path outside these roots, implementation should add a named allowed root in config rather than weakening validation.

### Path Safety Helper

Implement a shared helper in `prelabel_pipeline.routes` or a small `path_utils.py`:

```python
def resolve_under(path: str | Path, roots: list[Path]) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not any(resolved == root.resolve() or root.resolve() in resolved.parents for root in roots):
        raise ValueError("path outside allowed roots")
    return resolved
```

Rules:

- Apply `resolve_under` to browse paths, server input directories, local file serving, and extracted image paths.
- For upload filenames, keep only the basename and sanitize it.
- Reject upload names whose sanitized basename is empty.
- Do not follow symlinks that resolve outside allowed roots.
- Validate `run_id` before building any path; run JSON paths must be `runs_dir / f"{run_id}.json"` only.
- `DELETE /prelabel/runs/<run_id>` must not accept slashes or suffixes.
- Directory listings should return directories only and may cap entries at a reasonable limit, such as 1000.

## Path Bug Remediation Scope

Alongside prelabel integration, fix low-risk migration bugs discovered in `perception_process`. These are in scope for this implementation because they affect the same UI shell or local deployment reliability:

1. `/offline/stop` cannot stop the Docker process because `_current_proc` is never assigned. Assign it in `run_offline_test`, clear it in `finally`, and stop the fixed Docker container name as fallback.
2. `restart_services.sh` still assumes an old `/home/youfeng/...` project path. Compute project root from the script location.
3. Frontend WebSocket URLs use `localhost`, which breaks when opened from another machine. Use `location.hostname` and the correct proxy port.
4. `machine_config.json` relative SSH key paths are interpreted inconsistently. Resolve relative paths from the config file directory or standardize them to project-root-relative paths.
5. `01_evb/run_evb_remote.sh` still uses `/media/sda1/perception_process`. Compute root from the script location.

Items that need user confirmation or separate handling:

- Dockerfile and `docker-compose.yml` config source mismatch for SSH keys and env.
- `deploy_offline_test.sh` source resources under old `/home/youfeng/CLionProjects`.
- C++ night/offline debug default paths under old `/home/youfeng`.

These should be documented or guarded, but not blindly changed unless the expected runtime source paths are confirmed.

## Error Handling

Prelabel pipeline errors should be surfaced consistently:

- Per-step failures emit structured SSE entries with `type`, `step`, `status`, and `msg`.
- A failed directory should not prevent later input directories from running.
- Cancellation sets run status to `cancelled`, kills the current subprocess, and releases semaphores.
- CUDA errors run diagnostics and attempt one container restart/retry.
- Auto container restart must skip when any prelabel run is active.

## Concurrency

Preserve the existing concurrency model:

- `gpu_semaphore`: only one Step 2 inference runs at a time.
- `pipeline_semaphore`: optional full-pipeline serialization when `serial_mode` is true.
- `cancel_fn`: checked while waiting for semaphores and while reading subprocess output.
- CVAT REST session cache remains protected by a lock.

Runtime state model:

- `runs: dict[str, RunState]` holds active and recently loaded historical runs.
- `runs_lock: threading.RLock` guards modifications to `runs`, run logs, and active subprocess references.
- Each run has:
  - `event: threading.Event`
  - `logs: list[dict]`
  - `done: bool`
  - `cancel: bool`
  - `proc: subprocess.Popen | None`
  - `owner_token: str`
- SSE reads logs by index. It does not remove logs while streaming.
- SSE disconnects must not cancel the run.
- Background thread `finally` always:
  - sets `finished_at`
  - sets `done`
  - sets `event`
  - clears `proc`
  - releases any acquired semaphore
  - saves run JSON
  - removes upload temp dir when appropriate
- Active-run detection for auto container restart checks `status == "running" and not done`.

BaseHTTPRequestHandler and SSE requirements:

- `offline_server.py` must continue to use `ThreadingHTTPServer` or an equivalent threaded request server. A single-threaded `HTTPServer` is not acceptable because SSE connections would block cancel/status/upload requests.
- The SSE handler must never hold `runs_lock` while writing to `wfile`.
- The SSE loop copies pending log entries under lock, releases the lock, writes each event, then calls `flush()`.
- The SSE loop handles `BrokenPipeError`, `ConnectionResetError`, and `OSError` as normal disconnects.
- Multiple clients may connect to the same run stream. Each client maintains its own `sent` index and receives the same retained logs from index 0.
- SSE disconnect does not mutate run status and does not cancel subprocesses.
- Waiting uses `run["event"].wait(timeout=25)` or an equivalent timeout so the connection can send heartbeats and notice completion.

## Testing Plan

Backend verification:

```bash
python3 -m py_compile robot_monitor/offline_server.py robot_monitor/prelabel_pipeline/*.py
python3 -m unittest robot_monitor/tests/test_offline_server.py
python3 -m unittest discover robot_monitor/tests
```

New tests:

- config loading with environment-injected CVAT credentials
- run serialization and path redaction
- prelabel route dispatch for `/prelabel/runs` and `/prelabel/cvat-servers`
- browse whitelist accepts MPformer paths and rejects outside paths
- cancellation path assigns and clears current subprocess where testable

Endpoint acceptance matrix:

| Endpoint | Success coverage | Failure coverage |
| --- | --- | --- |
| `POST /prelabel/upload` | accepts image batch, appends second batch with same `upload_id` | rejects no files, invalid upload id, non-image-only batch |
| `POST /prelabel/run` | creates run with server dir, creates run with upload id, creates upload-only run | rejects empty task prefix, no inputs, outside-root path |
| `GET /prelabel/stream/<id>` | emits JSON log events and final `null` | unknown run returns 404 |
| `GET /prelabel/runs` | returns sorted summaries with redacted paths | malformed persisted JSON is skipped |
| `GET /prelabel/runs` | `X-Prelabel-Owner-Token` yields `owned_by_client` without returning token | token mismatch gives `owned_by_client=false` |
| `GET /prelabel/runs/<id>` | returns logs and `owned_by_client` | unknown run returns 404 |
| `DELETE /prelabel/runs/<id>` | removes only matching run JSON | rejects invalid id/path traversal |
| `POST /prelabel/runs/<id>/cancel` | sets cancel and kills mock proc | rejects token mismatch and non-running runs |
| `GET /prelabel/container-status` | parses docker/gpu success | handles docker failure |
| `POST /prelabel/restart-container` | manual restart calls diagnostics/restart | auto mode skips active run |
| `GET /prelabel/cvat-users` | returns users from mocked CVAT session | handles connection failure |
| `GET /prelabel/cvat-servers` | redacts credentials | no credentials in response |
| `PATCH /prelabel/settings/cvat-server/<id>` | updates host/port and clears cache | unknown id and invalid port |
| `GET /prelabel/browse` | lists whitelisted subdirs | rejects outside root and non-directory |
| legacy `/offline/local_file` | serves allowed project data file | rejects `..`, `/etc/passwd`, symlink escape |
| legacy `/offline/extracted_image` | serves allowed extracted image | rejects absolute outside-root dir and symlink escape |
| legacy `/ros2deploy/list_dir` | lists allowed project directory | rejects `/`, `/etc`, outside-root path |
| legacy `/ros2deploy/file_content` | reads allowed small file | rejects outside-root path and keeps large-file cap |

Core behavior tests:

- Step 2 command keeps `--opts` last.
- Upload-only mode emits skipped events for steps 2, 3, and 4.
- Cancellation while waiting for GPU semaphore exits without acquiring it.
- Subprocess clear and semaphore release happen in `finally`.
- CUDA error detection triggers diagnostics and one restart retry when mocked.
- Label conversion uses module-local mapping and does not import from `/media/sdc2/lhx/pipeline`.
- Upload continuation requires matching owner token and rejects token mismatch.
- Duplicate upload filenames are preserved with deterministic suffixing.
- `upload_id` validation rejects slashes, dots, and overly long ids.
- SSE long connection does not block `/prelabel/container-status`, `/prelabel/runs`, or cancellation requests under threaded server tests.
- Two SSE clients connected to the same run both receive retained logs.
- SSE disconnect does not cancel the run.
- Legacy path hardening tests cover `..`, absolute outside-root paths, and symlink escape for each hardened endpoint.

Frontend verification:

```bash
npm run build
```

Frontend interaction checks:

- `PrelabelPipelinePanel.vue` compiles under `vue-tsc` via `npm run build`.
- Full pipeline button sends no `skip_steps`.
- Upload-only button sends `skip_steps: [2, 3, 4]`.
- CVAT server change reloads users.
- SSE events update step states.
- Stop sends the local `PRELABEL_CLIENT_TOKEN`.
- Remote browser WebSocket fixes continue to work after adding the new tab.

Manual smoke checks after implementation:

- `GET /prelabel/cvat-servers`
- `GET /prelabel/runs`
- `GET /prelabel/container-status`
- open the new `预标注上传` tab beside `双目分析`
- start and cancel a small upload-only run
- run one full five-step pipeline on a small image directory and verify the CVAT task link opens
- run upload-only mode and verify steps 2-4 are visibly skipped

## Rollout Plan

1. Add prelabel backend package and route dispatch.
2. Port backend tests and verify core API responses.
3. Add Vue `PrelabelPipelinePanel.vue` and top-tab entry.
4. Wire frontend API calls to `/prelabel/*`.
5. Apply low-risk path/stop/WebSocket fixes from the migration audit.
6. Run Python compile/tests and `npm run build`.
7. Start the dev server and provide the local URL for validation.

## Open Questions

- CVAT credentials must be available in the runtime environment as `CVAT_REMOTE_USER`, `CVAT_REMOTE_PASSWORD`, `CVAT_LOCAL_USER`, and `CVAT_LOCAL_PASSWORD`.
- Docker and compose deployment cleanup needs confirmation before changing old SSH key and resource-copy assumptions.
- C++ default path cleanup should be handled separately unless those binaries are part of this immediate UI workflow.
