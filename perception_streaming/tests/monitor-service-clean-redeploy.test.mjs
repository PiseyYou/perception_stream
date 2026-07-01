import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const bridgePath = path.resolve(__dirname, '../robot_monitor/ssh_bridge.py')
const source = fs.readFileSync(bridgePath, 'utf8')

const start = source.indexOf('async def _check_and_start_monitor_service(self):')
const end = source.indexOf('async def _stop_monitor_service(self):')
assert.notEqual(start, -1, 'ssh_bridge.py should define _check_and_start_monitor_service')
assert.notEqual(end, -1, 'ssh_bridge.py should define _stop_monitor_service')

const body = source.slice(start, end)

const stopNewService = 'systemctl stop {new_service} 2>/dev/null; systemctl disable {new_service} 2>/dev/null'
const cleanupSameNameFiles = '[ -f {remote_service} ] && rm -f {remote_service}; [ -f {remote_script} ] && rm -f {remote_script}'
const uploadStart = 'def _upload_files():'

assert.match(
  body,
  /systemctl stop \{new_service\} 2>\/dev\/null; systemctl disable \{new_service\} 2>\/dev\/null/,
  'starting monitor service should first stop and disable the same service name',
)
assert.match(
  body,
  /\[ -f \{remote_service\} \] && rm -f \{remote_service\}; \[ -f \{remote_script\} \] && rm -f \{remote_script\}/,
  'starting monitor service should delete existing same-name service and script before upload',
)

const stopIndex = body.indexOf(stopNewService)
const cleanupIndex = body.indexOf(cleanupSameNameFiles)
const uploadIndex = body.indexOf(uploadStart)

assert.ok(stopIndex >= 0, 'same-name service stop command should be present')
assert.ok(cleanupIndex >= 0, 'same-name cleanup command should be present')
assert.ok(uploadIndex >= 0, 'upload function should be present')
assert.ok(stopIndex < cleanupIndex, 'same-name service should be stopped before deleting its files')
assert.ok(cleanupIndex < uploadIndex, 'same-name files should be deleted before uploading replacements')

console.log('monitor-service-clean-redeploy test passed')
