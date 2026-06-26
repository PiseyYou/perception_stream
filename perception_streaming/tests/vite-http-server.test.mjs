import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viteConfigPath = path.resolve(__dirname, '../vite.config.ts')
const source = fs.readFileSync(viteConfigPath, 'utf8')

assert.match(
  source,
  /open:\s*`http:\/\/\$\{DEV_SERVER_HOST\}:5173\/`/,
  'dev server open URL should match the HTTP entrypoint users open in the browser',
)
assert.doesNotMatch(
  source,
  /https:\s*command === 'serve' \? ensureDevCertificate\(\) : undefined/,
  'dev server should not make port 5173 HTTPS-only because HTTP users get ERR_EMPTY_RESPONSE',
)

console.log('vite-http-server test passed')
