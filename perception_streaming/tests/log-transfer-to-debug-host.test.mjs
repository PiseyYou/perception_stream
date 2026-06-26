import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const componentPath = path.resolve(__dirname, '../src/components/LogFetchPanel.vue')
const serverPath = path.resolve(__dirname, '../robot_monitor/offline_server.py')
const componentSource = fs.readFileSync(componentPath, 'utf8')
const serverSource = fs.readFileSync(serverPath, 'utf8')

assert.match(
  componentSource,
  /v-model="logTransferHost"/,
  'log transfer target host should be editable in the log analysis UI',
)
assert.match(
  componentSource,
  /192\.168\.55\.239/,
  'log transfer target host should default to 192.168.55.239',
)
assert.match(
  componentSource,
  /fetch\('\/offline\/transfer_logs_to_debug_host'/,
  'one-click transfer should call the dedicated log transfer endpoint',
)
assert.match(
  serverSource,
  /LOG_TRANSFER_HOST\s*=\s*os\.environ\.get\("LOG_TRANSFER_HOST",\s*"192\.168\.55\.239"\)/,
  'server should default the log transfer host to 192.168.55.239',
)
assert.match(
  serverSource,
  /LOG_TRANSFER_USER\s*=\s*os\.environ\.get\("LOG_TRANSFER_USER",\s*"youfeng"\)/,
  'server should default the log transfer user to youfeng',
)
assert.match(
  serverSource,
  /LOG_TRANSFER_PASSWORD\s*=\s*os\.environ\.get\("LOG_TRANSFER_PASSWORD",\s*"youfeng"\)/,
  'server should default the log transfer password to youfeng',
)
assert.match(
  serverSource,
  /LOG_TRANSFER_BASE\s*=\s*os\.environ\.get\("LOG_TRANSFER_BASE",\s*"\/home\/youfeng\/debug\/log"\)/,
  'server should default the log transfer directory to /home/youfeng/debug/log',
)
assert.match(
  serverSource,
  /def transfer_logs_to_debug_host\(local_dir: str, port: int, host: str = LOG_TRANSFER_HOST\) -> dict:/,
  'server should expose a log transfer helper that accepts local dir, port and host',
)
assert.match(
  serverSource,
  /remote_dir\s*=\s*f"\{LOG_TRANSFER_BASE\.rstrip\('\/'\)\}\/\{port_suffix\}\/\{date_folder\}"/,
  'logs should transfer under /home/youfeng/debug/log/<port_suffix>/<date>',
)
assert.match(
  serverSource,
  /if path == "\/offline\/transfer_logs_to_debug_host":/,
  'server should expose the transfer_logs_to_debug_host endpoint',
)

console.log('log-transfer-to-debug-host test passed')
