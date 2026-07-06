import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const source = fs.readFileSync(path.resolve(__dirname, '../src/composables/useAgoraRTC.ts'), 'utf8')

assert.doesNotMatch(
  source,
  /import\s+AgoraRTC[^\n]*from\s+['"]agora-rtc-sdk-ng['"]/,
  'useAgoraRTC should not statically import Agora SDK during app bootstrap on HTTP pages',
)

assert.match(
  source,
  /await\s+import\(['"]agora-rtc-sdk-ng['"]\)/,
  'useAgoraRTC should load Agora SDK only when joining a video channel',
)

console.log('agora-secure-context test passed')
