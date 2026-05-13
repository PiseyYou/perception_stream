import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const componentPath = path.resolve(__dirname, '../src/components/StereoAnalysis2Panel.vue')
const serverPath = path.resolve(__dirname, '../robot_monitor/offline_server.py')
const componentSource = fs.readFileSync(componentPath, 'utf8')
const serverSource = fs.readFileSync(serverPath, 'utf8')

assert.match(
  componentSource,
  /@click="doDownloadToLocal"/,
  'download button should call doDownloadToLocal',
)
assert.match(
  componentSource,
  /fetch\('\/offline\/download_to_local'/,
  'download button should post to the offline download_to_local endpoint',
)
assert.match(
  componentSource,
  /signal:\s*controller\.signal/,
  'download request should use the shared five-minute timeout controller',
)
assert.match(
  serverSource,
  /BOLUO_TRANSFER_HOST\s*=\s*os\.environ\.get\("BOLUO_TRANSFER_HOST",\s*"192\.168\.55\.239"\)/,
  'server should default to the requested target host',
)
assert.match(
  serverSource,
  /BOLUO_TRANSFER_BASE\s*=\s*os\.environ\.get\("BOLUO_TRANSFER_BASE",\s*"\/home\/youfeng\/debug\/boluo"\)/,
  'server should default to the requested target directory',
)
assert.match(
  serverSource,
  /BOLUO_TRANSFER_PASSWORD\s*=\s*os\.environ\.get\("BOLUO_TRANSFER_PASSWORD",\s*""\)/,
  'server should require the transfer password from the environment',
)
assert.match(
  serverSource,
  /未配置 BOLUO_TRANSFER_PASSWORD/,
  'server should fail clearly when the transfer password is not configured',
)
assert.match(
  serverSource,
  /if path == "\/offline\/download_to_local":/,
  'server should expose the download_to_local endpoint',
)
assert.match(
  serverSource,
  /"local_path":\s*f"\{ssh_target\}:\{base_dir\}\/"/,
  'download_to_local should report the remote boluo port directory, not a server-local cache path',
)
assert.match(
  serverSource,
  /base_dir\s*=\s*f"\{BOLUO_TRANSFER_BASE\.rstrip\('\/'\)\}\/\{port_suffix\}"/,
  'download_to_local should transfer into the port suffix directory, e.g. boluo/0286',
)
assert.match(
  serverSource,
  /def _remote_transfer_dir\(port_suffix:\s*str,\s*folder:\s*str\)[\s\S]*return f"\{BOLUO_TRANSFER_BASE\.rstrip\('\/'\)\}\/\{port_suffix\}\/\{folder\}"/,
  'download_to_local should copy each date folder under boluo/<port_suffix>/',
)

console.log('stereo-download-to-local test passed')
