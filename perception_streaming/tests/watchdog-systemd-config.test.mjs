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
  /VITE_URL="\$\{VITE_WATCHDOG_URL:-https:\/\/127\.0\.0\.1:5173\/\}"/,
  'watchdog should default to the HTTPS health URL that matches the dev server',
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
assert.match(service, /LogsDirectory=perception-streaming/, 'service should let systemd create a writable log directory')
assert.match(service, /Environment=VITE_WATCHDOG_URL=https:\/\/127\.0\.0\.1:5173\//, 'service should health-check the HTTPS dev server')
assert.match(service, /Environment=VITE_WATCHDOG_LOG=\/var\/log\/perception-streaming\/vite-watchdog\.log/, 'service should avoid appending to stale /tmp watchdog logs')
assert.match(service, /Environment=VITE_DEV_LOG=\/var\/log\/perception-streaming\/vite-dev\.log/, 'service should avoid appending to stale /tmp Vite logs')
assert.match(service, /^\[Install\]/m, 'service file should have an Install section')
assert.match(service, /WantedBy=multi-user\.target/, 'service should be enabled for normal boot')

assert.match(installer, /set -euo pipefail/, 'installer should fail fast')
assert.match(installer, /systemctl daemon-reload/, 'installer should reload systemd')
assert.match(installer, /systemctl enable --now perception-streaming-watchdog\.service/, 'installer should enable and start the service')
assert.match(installer, /systemctl status perception-streaming-watchdog\.service --no-pager/, 'installer should print service status')

console.log('watchdog systemd config tests passed')
