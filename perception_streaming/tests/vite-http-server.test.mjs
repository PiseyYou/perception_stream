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
  'dev server should not enable HTTPS on the HTTP entrypoint',
)
assert.doesNotMatch(
  source,
  /function ensureDevCertificate\(\)/,
  'vite config should not require a development HTTPS certificate',
)

console.log('vite-http-server test passed')
