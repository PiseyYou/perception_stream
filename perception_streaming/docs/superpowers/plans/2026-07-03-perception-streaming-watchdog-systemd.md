# Perception Streaming Watchdog Systemd Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `http://192.168.55.247:5173/` available across reboots and recover automatically when the Vite dev service stops responding.

**Architecture:** systemd supervises the existing `watchdog.sh` process. The watchdog continues to supervise Vite by checking the process, port, and HTTP health endpoint, and restarts Vite when unhealthy.

**Tech Stack:** Bash, systemd, Vite, npm, curl, Linux service management.

---

## File Structure

- Modify: `watchdog.sh` — keep existing health-check/restart logic, but make paths and timing configurable through environment variables while preserving current defaults.
- Create: `script/perception-streaming-watchdog.service` — systemd unit that runs `watchdog.sh` at boot and restarts it on failure.
- Create: `script/install_perception_streaming_watchdog.sh` — idempotent installer for the systemd unit.
- Modify: `WATCHDOG.md` — document systemd as the recommended long-running deployment path.
- Modify: `README.md` — update the deployment section to point operators to the systemd workflow.
- Create: `tests/watchdog-systemd-config.test.mjs` — Node regression test for the service file, installer, and watchdog configurability.

---

### Task 1: Add regression coverage for systemd watchdog deployment

**Files:**
- Create: `tests/watchdog-systemd-config.test.mjs`
- Test: `tests/watchdog-systemd-config.test.mjs`

- [ ] **Step 1: Write the failing test**

Create `tests/watchdog-systemd-config.test.mjs` with this content:

```js
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const watchdog = readFileSync('watchdog.sh', 'utf8')
const servicePath = 'script/perception-streaming-watchdog.service'
const installerPath = 'script/install_perception_streaming_watchdog.sh'

let service = ''
let installer = ''
try {
  service = readFileSync(servicePath, 'utf8')
} catch {
  service = ''
}
try {
  installer = readFileSync(installerPath, 'utf8')
} catch {
  installer = ''
}

assert.match(
  watchdog,
  /PROJECT_DIR="\$\{PROJECT_DIR:-\/media\/sda1\/perception_process\/perception_streaming\}"/,
  'watchdog should allow PROJECT_DIR override while preserving the current default',
)
assert.match(
  watchdog,
  /LOG_FILE="\$\{VITE_WATCHDOG_LOG:-\/tmp\/vite-watchdog\.log\}"/,
  'watchdog should allow watchdog log path override',
)
assert.match(
  watchdog,
  /VITE_LOG="\$\{VITE_DEV_LOG:-\/tmp\/vite-dev\.log\}"/,
  'watchdog should allow Vite log path override',
)
assert.match(
  watchdog,
  /CHECK_INTERVAL="\$\{VITE_WATCHDOG_CHECK_INTERVAL:-10\}"/,
  'watchdog should allow check interval override',
)
assert.match(
  watchdog,
  /VITE_URL="\$\{VITE_WATCHDOG_URL:-http:\/\/127\.0\.0\.1:5173\/\}"/,
  'watchdog should default to the current HTTP health URL',
)
assert.match(
  watchdog,
  /npm run dev > "\$VITE_LOG" 2>&1 &/,
  'watchdog should keep writing Vite output to the configured Vite log file',
)

assert.match(service, /^\[Unit\]/m, 'service file should have a Unit section')
assert.match(service, /Description=Perception Streaming Vite Watchdog/, 'service should describe its purpose')
assert.match(service, /Wants=network-online\.target/, 'service should wait for network-online target')
assert.match(service, /After=network-online\.target/, 'service should start after network-online target')
assert.match(service, /WorkingDirectory=\/media\/sda1\/perception_process\/perception_streaming/, 'service should run from project root')
assert.match(service, /ExecStart=\/bin\/bash \/media\/sda1\/perception_process\/perception_streaming\/watchdog\.sh/, 'service should run watchdog.sh')
assert.match(service, /Restart=always/, 'service should restart the watchdog if it exits')
assert.match(service, /RestartSec=10/, 'service should use a short restart delay')
assert.match(service, /^\[Install\]/m, 'service file should have an Install section')
assert.match(service, /WantedBy=multi-user\.target/, 'service should be enabled for normal boot')

assert.match(installer, /set -euo pipefail/, 'installer should fail fast')
assert.match(installer, /systemctl daemon-reload/, 'installer should reload systemd')
assert.match(installer, /systemctl enable --now perception-streaming-watchdog\.service/, 'installer should enable and start the service')
assert.match(installer, /systemctl status perception-streaming-watchdog\.service --no-pager/, 'installer should print service status')

console.log('watchdog systemd config tests passed')
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
node tests/watchdog-systemd-config.test.mjs
```

Expected: FAIL because `script/perception-streaming-watchdog.service` and `script/install_perception_streaming_watchdog.sh` do not exist yet, and `watchdog.sh` still hardcodes several values.

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/watchdog-systemd-config.test.mjs
git commit -m "test: cover perception streaming watchdog systemd config"
```

---

### Task 2: Make watchdog.sh configurable without changing default behavior

**Files:**
- Modify: `watchdog.sh`
- Test: `tests/watchdog-systemd-config.test.mjs`

- [ ] **Step 1: Replace the watchdog configuration block**

In `watchdog.sh`, replace lines 5-13 with:

```bash
PROJECT_DIR="${PROJECT_DIR:-/media/sda1/perception_process/perception_streaming}"
LOG_FILE="${VITE_WATCHDOG_LOG:-/tmp/vite-watchdog.log}"
VITE_LOG="${VITE_DEV_LOG:-/tmp/vite-dev.log}"
CHECK_INTERVAL="${VITE_WATCHDOG_CHECK_INTERVAL:-10}"  # 检查间隔（秒）
MAX_RESTART_ATTEMPTS="${VITE_WATCHDOG_MAX_RESTART_ATTEMPTS:-3}"  # 最大连续重启次数
RESTART_COOLDOWN="${VITE_WATCHDOG_RESTART_COOLDOWN:-60}"  # 重启冷却时间（秒）
VITE_URL="${VITE_WATCHDOG_URL:-http://127.0.0.1:5173/}"
STARTUP_TIMEOUT="${VITE_WATCHDOG_STARTUP_TIMEOUT:-120}"
STARTUP_CHECK_INTERVAL="${VITE_WATCHDOG_STARTUP_CHECK_INTERVAL:-2}"
```

This preserves all current default values while allowing systemd or shell users to override them.

- [ ] **Step 2: Run the focused test**

Run:

```bash
node tests/watchdog-systemd-config.test.mjs
```

Expected: still FAIL because the systemd service and installer have not been added yet. The previous failures about `watchdog.sh` configurability should be gone.

- [ ] **Step 3: Run shell syntax check**

Run:

```bash
bash -n watchdog.sh
```

Expected: no output and exit code 0.

- [ ] **Step 4: Commit watchdog hardening**

```bash
git add watchdog.sh
git commit -m "fix: make vite watchdog configuration overridable"
```

---

### Task 3: Add the systemd service unit

**Files:**
- Create: `script/perception-streaming-watchdog.service`
- Test: `tests/watchdog-systemd-config.test.mjs`

- [ ] **Step 1: Create the service file**

Create `script/perception-streaming-watchdog.service` with this content:

```ini
[Unit]
Description=Perception Streaming Vite Watchdog
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/media/sda1/perception_process/perception_streaming
ExecStart=/bin/bash /media/sda1/perception_process/perception_streaming/watchdog.sh
Restart=always
RestartSec=10

# Keep the existing service endpoint and logs unless explicitly overridden.
Environment=PROJECT_DIR=/media/sda1/perception_process/perception_streaming
Environment=VITE_WATCHDOG_URL=http://127.0.0.1:5173/
Environment=VITE_WATCHDOG_LOG=/tmp/vite-watchdog.log
Environment=VITE_DEV_LOG=/tmp/vite-dev.log
Environment=VITE_WATCHDOG_STARTUP_TIMEOUT=120
Environment=VITE_WATCHDOG_STARTUP_CHECK_INTERVAL=2

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Run the focused test**

Run:

```bash
node tests/watchdog-systemd-config.test.mjs
```

Expected: still FAIL because the installer has not been added yet. Service-file assertions should pass.

- [ ] **Step 3: Verify service syntax when systemd-analyze is available**

Run:

```bash
if command -v systemd-analyze >/dev/null 2>&1; then systemd-analyze verify script/perception-streaming-watchdog.service; else echo "systemd-analyze not available; skipped"; fi
```

Expected: no output from `systemd-analyze verify`, or the skip message if the command is not available.

- [ ] **Step 4: Commit service file**

```bash
git add script/perception-streaming-watchdog.service
git commit -m "feat: add systemd unit for perception streaming watchdog"
```

---

### Task 4: Add an idempotent systemd installer

**Files:**
- Create: `script/install_perception_streaming_watchdog.sh`
- Test: `tests/watchdog-systemd-config.test.mjs`

- [ ] **Step 1: Create the installer script**

Create `script/install_perception_streaming_watchdog.sh` with this content:

```bash
#!/bin/bash
set -euo pipefail

SERVICE_NAME="perception-streaming-watchdog.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_SERVICE="$SCRIPT_DIR/$SERVICE_NAME"
TARGET_SERVICE="/etc/systemd/system/$SERVICE_NAME"

if [ "$(id -u)" -ne 0 ]; then
    echo "请使用 sudo 运行: sudo $0"
    exit 1
fi

if [ ! -f "$SOURCE_SERVICE" ]; then
    echo "找不到服务文件: $SOURCE_SERVICE"
    exit 1
fi

install -m 0644 "$SOURCE_SERVICE" "$TARGET_SERVICE"
systemctl daemon-reload
systemctl enable --now perception-streaming-watchdog.service

echo "已安装并启动 perception-streaming-watchdog.service"
echo ""
echo "常用命令:"
echo "  sudo systemctl status perception-streaming-watchdog.service"
echo "  sudo systemctl restart perception-streaming-watchdog.service"
echo "  sudo journalctl -u perception-streaming-watchdog.service -f"
echo "  tail -f /tmp/vite-watchdog.log"
echo "  tail -f /tmp/vite-dev.log"
echo ""
systemctl status perception-streaming-watchdog.service --no-pager
```

- [ ] **Step 2: Mark installer executable**

Run:

```bash
chmod +x script/install_perception_streaming_watchdog.sh
```

Expected: no output and exit code 0.

- [ ] **Step 3: Run the focused test**

Run:

```bash
node tests/watchdog-systemd-config.test.mjs
```

Expected: PASS and output `watchdog systemd config tests passed`.

- [ ] **Step 4: Run shell syntax check**

Run:

```bash
bash -n script/install_perception_streaming_watchdog.sh
```

Expected: no output and exit code 0.

- [ ] **Step 5: Commit installer**

```bash
git add script/install_perception_streaming_watchdog.sh tests/watchdog-systemd-config.test.mjs
git commit -m "feat: add perception streaming watchdog installer"
```

---

### Task 5: Update operator documentation

**Files:**
- Modify: `WATCHDOG.md`
- Modify: `README.md`
- Test: documentation inspection plus existing Node test

- [ ] **Step 1: Update `WATCHDOG.md` long-running deployment section**

Replace the current `## 开机自启动（可选）` section in `WATCHDOG.md` with:

```markdown
## 开机自启动（推荐 systemd）

长期运行请使用 systemd 管理看门狗。systemd 负责开机启动和守护 `watchdog.sh`，`watchdog.sh` 负责检查并重启 Vite。

### 安装并启动

```bash
sudo ./script/install_perception_streaming_watchdog.sh
```

### 查看状态

```bash
sudo systemctl status perception-streaming-watchdog.service
```

### 重启服务

```bash
sudo systemctl restart perception-streaming-watchdog.service
```

### 查看 systemd 日志

```bash
sudo journalctl -u perception-streaming-watchdog.service -f
```

### 查看 watchdog / Vite 日志

```bash
tail -f /tmp/vite-watchdog.log
tail -f /tmp/vite-dev.log
```

### 停止开机自启动

```bash
sudo systemctl disable --now perception-streaming-watchdog.service
```

### 临时调试方式

如果只是当前登录会话里临时调试，也可以继续使用：

```bash
./start-watchdog.sh
./stop-watchdog.sh
```

不建议用 `crontab @reboot` 作为长期方案，因为它不能在 watchdog 进程异常退出后继续守护该进程。
```

- [ ] **Step 2: Update `README.md` deployment notes**

In `README.md`, replace the `### Vite 开发服务器看门狗` command block and the paragraph immediately after it with:

```markdown
### Vite 开发服务器看门狗
自动监控 Vite 开发服务器状态，一旦检测到服务掉线，自动重启服务。长期运行推荐使用 systemd：

```bash
# 安装、开机启用并立即启动看门狗
sudo ./script/install_perception_streaming_watchdog.sh

# 查看服务状态
sudo systemctl status perception-streaming-watchdog.service

# 查看日志
sudo journalctl -u perception-streaming-watchdog.service -f
tail -f /tmp/vite-watchdog.log
tail -f /tmp/vite-dev.log
```

临时调试仍可使用 `./start-watchdog.sh` 和 `./stop-watchdog.sh`。看门狗默认检查 `http://127.0.0.1:5173/`。由于当前项目冷启动通常需要 50 秒以上，看门狗会轮询等待 Vite 就绪，可通过 `VITE_WATCHDOG_URL`、`VITE_WATCHDOG_STARTUP_TIMEOUT` 和 `VITE_WATCHDOG_STARTUP_CHECK_INTERVAL` 覆盖检测地址与启动等待策略。
```

- [ ] **Step 3: Run focused regression test**

Run:

```bash
node tests/watchdog-systemd-config.test.mjs
```

Expected: PASS.

- [ ] **Step 4: Commit docs**

```bash
git add WATCHDOG.md README.md
git commit -m "docs: document systemd watchdog deployment"
```

---

### Task 6: Install and verify the service on the host

**Files:**
- Runtime install target: `/etc/systemd/system/perception-streaming-watchdog.service`
- No repository file changes expected after this task.

- [ ] **Step 1: Install service**

Run:

```bash
sudo ./script/install_perception_streaming_watchdog.sh
```

Expected:

- Output includes `已安装并启动 perception-streaming-watchdog.service`.
- `systemctl status` output shows the service as loaded and active or activating.

- [ ] **Step 2: Verify service is enabled**

Run:

```bash
systemctl is-enabled perception-streaming-watchdog.service
```

Expected:

```text
enabled
```

- [ ] **Step 3: Verify service is active**

Run:

```bash
systemctl is-active perception-streaming-watchdog.service
```

Expected:

```text
active
```

- [ ] **Step 4: Verify health endpoint**

Run:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5173/
```

Expected:

```text
200
```

- [ ] **Step 5: Verify LAN page in browser**

Open `http://192.168.55.247:5173/`.

Expected: the Perception Streaming UI renders; it is not a white screen.

- [ ] **Step 6: Simulate Vite process failure**

Run:

```bash
pkill -f "node_modules/.bin/vite" || true
sleep 20
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5173/
```

Expected:

```text
200
```

Also check:

```bash
tail -40 /tmp/vite-watchdog.log
```

Expected: log includes a detected outage and restart, such as `检测到服务掉线` and `Vite服务器启动成功`.

- [ ] **Step 7: Commit final verification note if docs changed during install**

If no files changed, do not commit. If a verification note is added to docs, commit it with:

```bash
git add WATCHDOG.md README.md
git commit -m "docs: add watchdog verification notes"
```

---

## Self-Review

- Spec coverage: systemd service, installer, watchdog configurability, docs, and host verification are all covered by Tasks 1-6.
- Placeholder scan: no TBD/TODO/fill-in placeholders remain.
- Type/name consistency: service name is consistently `perception-streaming-watchdog.service`; installer and docs use the same name; logs use `/tmp/vite-watchdog.log` and `/tmp/vite-dev.log` consistently.
