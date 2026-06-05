import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viteConfigPath = path.resolve(__dirname, '../vite.config.ts')
const source = fs.readFileSync(viteConfigPath, 'utf8')

assert.match(
  source,
  /data\/conf\/bestmow_rsa_202606/,
  'vite SSH commands should use the 202606 robot private key',
)
assert.doesNotMatch(
  source,
  /data\/conf\/bestmow_rsa_202605/,
  'vite SSH commands should not keep using the expired 202605 private key',
)

console.log('vite-ssh-key-config test passed')
