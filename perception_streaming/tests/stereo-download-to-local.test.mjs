import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const componentPath = path.resolve(__dirname, '../src/components/StereoAnalysis2Panel.vue')
const serverPath = path.resolve(__dirname, '../robot_monitor/offline_server.py')
const componentSource = fs.readFileSync(componentPath, 'utf8')
const serverSource = fs.readFileSync(serverPath, 'utf8')
const downloadFunctionMatch = componentSource.match(/async function doDownloadToLocal\(\)[\s\S]*?function selectPair/)
assert.ok(downloadFunctionMatch, 'doDownloadToLocal function should exist')
const downloadFunction = downloadFunctionMatch[0]
const testConnectionFunctionMatch = componentSource.match(/async function doTestDownloadTransfer\(\)[\s\S]*?async function doDownloadToLocal/)
assert.ok(testConnectionFunctionMatch, 'doTestDownloadTransfer function should exist')
const testConnectionFunction = testConnectionFunctionMatch[0]
const configLoadMatch = componentSource.match(/onMounted\(async \(\) => \{[\s\S]*?\n\}\)/)
assert.ok(configLoadMatch, 'stereo panel should load server config on mount')
const configLoadBlock = configLoadMatch[0]

assert.match(
  componentSource,
  /function defaultStereoFolderSuffix\(port:[\s\S]*dateStr = today\)[\s\S]*return `\$\{portSuffix\}\/\$\{dateStr\}`/,
  'stereo folder defaults should be derived from the port suffix and current date',
)
assert.match(
  componentSource,
  /const nightFolderInput = ref\(defaultStereoFolderSuffix\(\)\)/,
  'night stereo folder should default to <port last four digits>/<today>',
)
assert.match(
  componentSource,
  /const dayFolderInput = ref\(defaultStereoFolderSuffix\(\)\)/,
  'day stereo folder should default to <port last four digits>/<today>',
)
assert.doesNotMatch(
  componentSource,
  /ref\('0115\/20260421'\)|ref\('0016\/20260420'\)/,
  'stereo folder defaults should not be hard-coded to stale sample dates',
)
assert.match(
  configLoadBlock,
  /applyDefaultStereoFolders\(data\.default_ports\.stereo_analysis\)/,
  'loading the default stereo port should refresh both stereo folder defaults',
)

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
  /v-model="downloadTransferHost"/,
  'download transfer host should be editable in the stereo analysis UI',
)
assert.match(
  componentSource,
  /class="sa2-transfer-row"/,
  'download transfer config should be shown on its own row',
)
assert.match(
  componentSource,
  /const downloadTransferHost = ref\('192\.168\.55\.239'\)/,
  'download transfer host should default to 192.168.55.239',
)
assert.match(
  componentSource,
  /const downloadTransferUser = ref\('youfeng'\)/,
  'download transfer user should default to youfeng',
)
assert.match(
  componentSource,
  /<input v-model="downloadTransferPassword" type="password"/,
  'download transfer password input should mask the password',
)
assert.match(
  componentSource,
  /placeholder="\*\*\*\*"/,
  'download transfer password placeholder should show masked text',
)
assert.match(
  componentSource,
  /const downloadTransferPassword = ref\('youfeng'\)/,
  'download transfer password should default to youfeng',
)
assert.match(
  componentSource,
  /const downloadTransferBase = ref\('\/home\/youfeng\/debug\/boluo'\)/,
  'download transfer base path should default to /home/youfeng/debug/boluo',
)
assert.match(
  componentSource,
  /@click="doTestDownloadTransfer"/,
  'download transfer UI should include a test connection button',
)
assert.match(
  componentSource,
  /:class="\{ ok: downloadTransferTestOk === true, error: downloadTransferTestOk === false \}"/,
  'download transfer test status should render green for success and red for failure',
)
assert.match(
  testConnectionFunction,
  /fetch\('\/offline\/test_boluo_transfer_connection'/,
  'test connection button should call the dedicated endpoint',
)
assert.match(
  testConnectionFunction,
  /downloadTransferTestOk\.value = true/,
  'successful connection test should set green status',
)
assert.match(
  testConnectionFunction,
  /downloadTransferTestOk\.value = false/,
  'failed connection test should set red status',
)
assert.match(
  downloadFunction,
  /transfer_host:\s*downloadTransferHost\.value\.trim\(\)/,
  'download request should send the transfer host',
)
assert.match(
  downloadFunction,
  /transfer_user:\s*downloadTransferUser\.value\.trim\(\)/,
  'download request should send the transfer user',
)
assert.match(
  downloadFunction,
  /transfer_password:\s*downloadTransferPassword\.value/,
  'download request should send the transfer password',
)
assert.match(
  downloadFunction,
  /transfer_base:\s*downloadTransferBase\.value\.trim\(\)/,
  'download request should send the transfer base path',
)
assert.match(
  downloadFunction,
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
  /BOLUO_TRANSFER_PASSWORD\s*=\s*os\.environ\.get\("BOLUO_TRANSFER_PASSWORD",\s*"youfeng"\)/,
  'server should default the transfer password to youfeng',
)
assert.match(
  serverSource,
  /def download_to_local\(port: int, date_start: str, date_end: str, host: str = BOLUO_TRANSFER_HOST, user: str = BOLUO_TRANSFER_USER, password: str = BOLUO_TRANSFER_PASSWORD, base: str = BOLUO_TRANSFER_BASE\) -> dict:/,
  'download_to_local should accept transfer config overrides from the UI',
)
assert.match(
  serverSource,
  /if path == "\/offline\/download_to_local":/,
  'server should expose the download_to_local endpoint',
)
assert.match(
  serverSource,
  /def test_boluo_transfer_connection\(host: str = BOLUO_TRANSFER_HOST, user: str = BOLUO_TRANSFER_USER, password: str = BOLUO_TRANSFER_PASSWORD\) -> dict:/,
  'server should expose a helper for testing the transfer SSH credentials',
)
assert.match(
  serverSource,
  /if path == "\/offline\/test_boluo_transfer_connection":/,
  'server should expose the transfer connection test endpoint',
)
assert.match(
  serverSource,
  /"local_path":\s*f"\{ssh_target\}:\{base_dir\}\/"/,
  'download_to_local should report the remote boluo port directory, not a server-local cache path',
)
assert.match(
  serverSource,
  /base_dir\s*=\s*f"\{base\.rstrip\('\/'\)\}\/\{port_suffix\}"/,
  'download_to_local should transfer into the port suffix directory, e.g. boluo/0286',
)
assert.match(
  serverSource,
  /def _remote_transfer_dir\(port_suffix:\s*str,\s*folder:\s*str,\s*base:\s*str = BOLUO_TRANSFER_BASE\)[\s\S]*return f"\{base\.rstrip\('\/'\)\}\/\{port_suffix\}\/\{folder\}"/,
  'download_to_local should copy each date folder under boluo/<port_suffix>/',
)
assert.match(
  serverSource,
  /host = body\.get\("transfer_host", BOLUO_TRANSFER_HOST\)/,
  'download route should accept the UI transfer host',
)
assert.match(
  serverSource,
  /user = body\.get\("transfer_user", BOLUO_TRANSFER_USER\)/,
  'download route should accept the UI transfer user',
)
assert.match(
  serverSource,
  /password = body\.get\("transfer_password", BOLUO_TRANSFER_PASSWORD\)/,
  'download route should accept the UI transfer password',
)
assert.match(
  serverSource,
  /base = body\.get\("transfer_base", BOLUO_TRANSFER_BASE\)/,
  'download route should accept the UI transfer base path',
)

console.log('stereo-download-to-local test passed')
