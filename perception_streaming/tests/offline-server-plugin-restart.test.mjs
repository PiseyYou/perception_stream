import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viteConfigPath = path.resolve(__dirname, '../vite.config.ts')
const source = fs.readFileSync(viteConfigPath, 'utf8')

assert.match(
  source,
  /let restartTimer: ReturnType<typeof setTimeout> \| null = null/,
  'offline server plugin should keep restart timer state',
)
assert.match(
  source,
  /function scheduleRestart\(start: \(\) => void\)[\s\S]*restartDelayMs = Math\.min\(restartDelayMs \* 2, 30000\)/,
  'offline server plugin should schedule bounded backoff restarts',
)
assert.match(
  source,
  /proc\.on\('error',[\s\S]*scheduleRestart\(start\)/,
  'offline server plugin should retry when the child process fails to start',
)
assert.match(
  source,
  /proc\.on\('exit',[\s\S]*scheduleRestart\(start\)/,
  'offline server plugin should retry when offline_server.py exits',
)
assert.match(
  source,
  /process\.once\('exit', stop\)/,
  'offline server plugin should avoid stacking duplicate process exit handlers',
)

console.log('offline-server-plugin-restart test passed')
