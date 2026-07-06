import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const watchdogPath = path.resolve(__dirname, '../watchdog.sh')
const source = fs.readFileSync(watchdogPath, 'utf8')

assert.match(
  source,
  /VITE_URL="\$\{VITE_WATCHDOG_URL:-http:\/\/127\.0\.0\.1:5173\/\}"/,
  'watchdog should check the same HTTP dev URL that users open',
)
assert.doesNotMatch(
  source,
  /curl -k -s -o \/dev\/null -w "%\{http_code\}" --connect-timeout 3 "\$VITE_URL"/,
  'watchdog should not use TLS flags for the HTTP health check',
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

console.log('watchdog-http-url test passed')
