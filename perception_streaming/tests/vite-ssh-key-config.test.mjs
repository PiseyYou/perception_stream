import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viteConfigPath = path.resolve(__dirname, '../vite.config.ts')
const source = fs.readFileSync(viteConfigPath, 'utf8')

assert.match(
  source,
  /data\/conf\/bestmow_rsa_202609/,
  'vite SSH commands should use the 202609 robot private key',
)
assert.doesNotMatch(
  source,
  /data\/conf\/bestmow_rsa_202608/,
  'vite SSH commands should not keep using the previous 202608 private key',
)

assert.match(source, /const REMOTE_PORT = '10080'/, 'vite SSH commands should use port 10080')

console.log('vite-ssh-key-config test passed')
