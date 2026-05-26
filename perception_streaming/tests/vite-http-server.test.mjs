import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viteConfigPath = path.resolve(__dirname, '../vite.config.ts')
const source = fs.readFileSync(viteConfigPath, 'utf8')

assert.match(
  source,
  /https:\s*command === 'serve' \? ensureDevCertificate\(\) : undefined/,
  'dev server should enable HTTPS on port 5173 so Agora keeps a secure context',
)
assert.match(
  source,
  /ensureDevCertificate\(/,
  'dev server should generate a self-signed certificate for the HTTPS entrypoint',
)
assert.match(
  source,
  /open:\s*`https:\/\/\$\{DEV_SERVER_HOST\}:5173\/`/,
  'dev server open URL should match the documented HTTPS entrypoint',
)

console.log('vite-http-server test passed')
