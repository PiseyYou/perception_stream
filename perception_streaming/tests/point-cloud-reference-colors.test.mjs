import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')

const rendererSource = fs.readFileSync(path.join(root, 'src/composables/usePcdRenderer.ts'), 'utf8')
const parserSource = fs.readFileSync(path.join(root, 'src/utils/pcdParser.ts'), 'utf8')
const pointCloudPanelSource = fs.readFileSync(path.join(root, 'src/components/PointCloudPanel.vue'), 'utf8')
const logAnalysisSource = fs.readFileSync(path.join(root, 'src/components/LogAnalysis2Panel.vue'), 'utf8')

for (const [label, rgbPattern] of [
  [0, String.raw`\[0,\s*0,\s*0`],
  [1, String.raw`\[0,\s*0,\s*200\s*/\s*255`],
  [6, String.raw`\[255\s*/\s*255,\s*165\s*/\s*255,\s*0`],
  [9, String.raw`\[245\s*/\s*255,\s*130\s*/\s*255,\s*48\s*/\s*255`],
  [13, String.raw`\[138\s*/\s*255,\s*43\s*/\s*255,\s*226\s*/\s*255`],
  [107, String.raw`\[0,\s*255\s*/\s*255,\s*0`],
]) {
  assert.match(
    rendererSource,
    new RegExp(`${label}:\\s*${rgbPattern}`),
    `usePcdRenderer should expose reference RGB color for label ${label}`,
  )
}

assert.doesNotMatch(
  rendererSource,
  /OTP_LABEL_COLOR[\s\S]*0:\s*\[0\.1,\s*0\.1,\s*0\.1\]/,
  'offline-test point cloud renderer should not keep the old custom OTP palette for label 0',
)
assert.match(
  parserSource,
  /0:\s*\[0,\s*0,\s*0\s*\]/,
  'binary PCD parser should use the reference black color for label 0',
)
assert.match(
  pointCloudPanelSource,
  /0:\s*\[0,\s*0,\s*0\s*\]/,
  'live point cloud panel should use the reference black color for label 0',
)
assert.match(
  logAnalysisSource,
  /0:\s*\[0,\s*0,\s*0\s*\]/,
  'log-analysis point cloud viewer should use the reference black color for label 0',
)

console.log('point-cloud-reference-colors test passed')
