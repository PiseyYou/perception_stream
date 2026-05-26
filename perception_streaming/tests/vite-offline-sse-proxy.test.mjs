import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viteConfigPath = path.resolve(__dirname, '../vite.config.ts')
const source = fs.readFileSync(viteConfigPath, 'utf8')

const offlineProxyMatch = source.match(/'\/offline':\s*\{[\s\S]*?\n\s*\},\n\s*'\/ros2deploy':/)
assert.ok(offlineProxyMatch, 'offline proxy config should exist')

const offlineProxy = offlineProxyMatch[0]
assert.doesNotMatch(
  offlineProxy,
  /proxyRes[\s\S]*text\/event-stream[\s\S]*proxyRes\.pipe\(res\)/,
  'offline proxy should let Vite stream SSE once instead of manually piping the same response twice',
)
assert.doesNotMatch(
  offlineProxy,
  /res\.writeHead\(proxyRes\.statusCode \|\| 200, proxyRes\.headers\)/,
  'offline proxy should not write SSE headers manually before Vite proxy writes them',
)

console.log('vite-offline-sse-proxy test passed')
