import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viteConfigPath = path.resolve(__dirname, '../vite.config.ts')
const source = fs.readFileSync(viteConfigPath, 'utf8')

assert.match(
  source,
  /open:\s*`https:\/\/\$\{DEV_SERVER_HOST\}:5173\/`/,
  'dev server open URL should match the HTTPS entrypoint users open in the browser',
)
assert.match(
  source,
  /https:\s*command === 'serve' \? ensureDevCertificate\(\) : undefined/,
  'dev server should enable HTTPS with the generated development certificate',
)
assert.match(
  source,
  /function ensureDevCertificate\(\)/,
  'vite config should generate or load the development HTTPS certificate',
)

console.log('vite-https-server test passed')
