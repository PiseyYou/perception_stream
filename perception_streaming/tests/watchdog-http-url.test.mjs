import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const watchdogPath = path.resolve(__dirname, '../watchdog.sh')
const source = fs.readFileSync(watchdogPath, 'utf8')

assert.match(
  source,
  /VITE_URL="\$\{VITE_WATCHDOG_URL:-https:\/\/127\.0\.0\.1:5173\/\}"/,
  'watchdog should check the same HTTPS dev URL that users open',
)
assert.match(
  source,
  /curl -k -s -o \/dev\/null -w "%\{http_code\}" --connect-timeout 3 "\$VITE_URL"/,
  'watchdog should allow the local self-signed development certificate during health checks',
)
assert.match(
  source,
  /STARTUP_TIMEOUT="\$\{VITE_WATCHDOG_STARTUP_TIMEOUT:-120\}"/,
  'watchdog should expose a configurable cold-start timeout',
)
assert.match(
  source,
  /while \[ "\$waited" -lt "\$STARTUP_TIMEOUT" \]; do/,
  'watchdog should poll for readiness instead of assuming Vite is up after a fixed sleep',
)
assert.doesNotMatch(
  source,
  /\n\s*sleep 8\n/,
  'watchdog should not use a fixed 8 second startup wait because dev-server cold starts can take longer',
)
assert.match(
  source,
  /自动重启已禁用/,
  'watchdog should report a failed health check without restarting Vite',
)

console.log('watchdog-http-url test passed')
