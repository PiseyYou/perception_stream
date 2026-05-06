import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const componentPath = path.resolve(__dirname, '../src/components/StereoAnalysis2Panel.vue')
const source = fs.readFileSync(componentPath, 'utf8')

assert.match(
  source,
  /@click="stopOfflineDebug"/,
  'K100 controls should expose a stop button next to the checkbox',
)

assert.match(
  source,
  /fetch\(['"]\/offline\/stop['"]\s*,\s*\{\s*method:\s*['"]POST['"]/s,
  'stop button should call the backend stop endpoint with POST',
)

assert.match(
  source,
  /offlineRunning\s*\?\s*'停止中\.\.\.'\s*:\s*'停止'/,
  'stop button label should reflect the current running state',
)

console.log('stereo-stop-button test passed')
