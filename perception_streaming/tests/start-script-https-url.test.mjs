import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const startScriptPath = path.resolve(__dirname, '../start.sh')
const source = fs.readFileSync(startScriptPath, 'utf8')

assert.match(
  source,
  /http:\/\/\$\{VITE_DEV_SERVER_HOST:-192\.168\.55\.247\}:5173\//,
  'start.sh should print the HTTP URL that works on the dev server',
)
assert.doesNotMatch(
  source,
  /https:\/\/\$\{VITE_DEV_SERVER_HOST:-192\.168\.55\.247\}:5173\//,
  'start.sh should not advertise HTTPS when the dev server is HTTP',
)

console.log('start-script-http-url test passed')
