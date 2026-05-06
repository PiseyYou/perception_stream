import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const componentPath = path.resolve(__dirname, '../src/components/StereoAnalysis2Panel.vue')
const source = fs.readFileSync(componentPath, 'utf8')

assert.match(
  source,
  /const\s+UPLOAD_IMAGES_TIMEOUT_MS\s*=\s*5\s*\*\s*60\s*\*\s*1000/,
  'stereo image upload should allow the same 5 minute window as the offline proxy',
)
assert.doesNotMatch(
  source,
  /请求超时（60秒）|},\s*60000\)/,
  'stereo image upload should not abort long robot downloads after 60 seconds',
)

console.log('stereo-upload-timeout test passed')
