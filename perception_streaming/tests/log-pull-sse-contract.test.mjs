import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const serverPath = path.resolve(__dirname, '../robot_monitor/offline_server.py')
const source = fs.readFileSync(serverPath, 'utf8')

const routeMatch = source.match(/if path == "\/offline\/pull_robot_logs":[\s\S]*?if path == "\/offline\/check_local_logs":/)
assert.ok(routeMatch, 'pull_robot_logs route should exist')

const route = routeMatch[0]
const componentPath = path.resolve(__dirname, '../src/components/LogFetchPanel.vue')
const componentSource = fs.readFileSync(componentPath, 'utf8')

assert.match(
  componentSource,
  /const moduleKeyword = ref\('stereo_perception'\)/,
  'log pull UI should default the module keyword to stereo_perception',
)
assert.match(
  componentSource,
  /module_keyword:\s*moduleKeyword\.value\.trim\(\)/,
  'log pull request should send the selected module keyword to the server',
)
assert.match(
  route,
  /module_keyword = body\.get\("module_keyword", "stereo_perception"\)/,
  'pull-log route should read the module keyword from the request body',
)
assert.match(
  route,
  /pull_robot_logs\(port, local_save_dir, progress_callback, module_keyword\)/,
  'pull-log route should pass the module keyword into pull_robot_logs',
)
assert.match(
  route,
  /self\.send_header\("Connection", "close"\)/,
  'finite pull-log SSE responses should close explicitly so Vite proxy and fetch finish cleanly',
)
assert.match(
  route,
  /self\.close_connection = True/,
  'pull-log SSE route should ask BaseHTTPRequestHandler to close after the done event',
)
assert.doesNotMatch(
  route,
  /\{'done': True, \*\*result\}/,
  'done event should not include the full logs array because it bloats the final SSE chunk',
)
assert.match(
  route,
  /"file_count": result\.get\("file_count", 0\)/,
  'done event should still include the fields the frontend needs for status text',
)

console.log('log-pull-sse-contract test passed')
