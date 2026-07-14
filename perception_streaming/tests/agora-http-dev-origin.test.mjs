import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const source = fs.readFileSync(path.resolve(__dirname, '../src/App.vue'), 'utf8')

assert.match(
  source,
  /--unsafely-treat-insecure-origin-as-secure=\$\{location\.origin\}/,
  'HTTP insecure-context guidance should include a Chrome dev origin allowlist command for the current origin',
)

assert.match(
  source,
  /Chrome HTTP 开发白名单/,
  'HTTP insecure-context guidance should label the Chrome allowlist as a development-only option',
)

assert.doesNotMatch(
  source,
  /Agora 视频支持普通 HTTP/,
  'guidance should not imply Agora video supports ordinary HTTP pages',
)

console.log('agora-http-dev-origin test passed')
