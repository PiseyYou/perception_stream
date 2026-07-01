import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const scriptPath = path.resolve(__dirname, '../script/monitor_mow_obstacle.sh')
const servicePath = path.resolve(__dirname, '../script/monitor_mow_obstacle.service')

const script = fs.readFileSync(scriptPath, 'utf8')
const service = fs.readFileSync(servicePath, 'utf8')

assert.match(
  script,
  /MONITOR_LOG_MAX_BYTES="\$\{MONITOR_LOG_MAX_BYTES:-1048576\}"/,
  'monitor_mow_obstacle.sh should default to a 1MB active log limit',
)
assert.match(
  script,
  /MONITOR_LOG_MAX_FILES="\$\{MONITOR_LOG_MAX_FILES:-3\}"/,
  'monitor_mow_obstacle.sh should keep at most 3 total log files including the active log',
)
assert.match(
  script,
  /rotate_monitor_log\(\)/,
  'monitor_mow_obstacle.sh should rotate its own output log',
)
assert.match(
  script,
  /exec >> "\$MONITOR_LOG_FILE" 2>&1/,
  'monitor_mow_obstacle.sh should own stdout and stderr so it can reopen logs after rotation',
)
assert.doesNotMatch(
  service,
  /Standard(?:Output|Error)=append:/,
  'systemd should not append directly to monitor_mow_obstacle.log because that bypasses script rotation',
)
assert.match(
  service,
  /StandardOutput=null/,
  'systemd stdout should be disabled after the script takes over file logging',
)
assert.match(
  service,
  /StandardError=null/,
  'systemd stderr should be disabled after the script takes over file logging',
)

console.log('monitor-mow-obstacle-log-rotation test passed')
