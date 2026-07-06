import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const componentSource = fs.readFileSync(path.resolve(__dirname, '../src/components/DevicePanel.vue'), 'utf8')
const appSource = fs.readFileSync(path.resolve(__dirname, '../src/App.vue'), 'utf8')
const monitorSource = fs.readFileSync(path.resolve(__dirname, '../src/composables/useObstacleMonitor.ts'), 'utf8')

assert.match(
  componentSource,
  /const CUSTOM_DEVICE_SN_OPTIONS_STORAGE_KEY = 'perception_streaming\.customDeviceSnOptions'/,
  'DevicePanel should use a stable localStorage key for custom device SN choices',
)
assert.match(
  componentSource,
  /const DEFAULT_DEVICE_SN_OPTIONS = \[[\s\S]*\]/,
  'DevicePanel should keep the built-in device SN choices separate from persisted custom choices',
)
assert.match(
  componentSource,
  /function loadCustomDeviceSnOptions\(\)[\s\S]*localStorage\.getItem\(CUSTOM_DEVICE_SN_OPTIONS_STORAGE_KEY\)[\s\S]*JSON\.parse\(stored\)/,
  'DevicePanel should load custom device SN choices from localStorage',
)
assert.match(
  componentSource,
  /function saveCustomDeviceSnOptions\(options: string\[\]\)[\s\S]*localStorage\.setItem\(CUSTOM_DEVICE_SN_OPTIONS_STORAGE_KEY, JSON\.stringify\(options\)\)/,
  'DevicePanel should save custom device SN choices to localStorage',
)
assert.match(
  componentSource,
  /const deviceSnOptions = ref\(\[\.\.\.new Set\(\[\.\.\.DEFAULT_DEVICE_SN_OPTIONS, \.\.\.loadCustomDeviceSnOptions\(\)\]\)\]\.sort\(compareDeviceSn\)\)/,
  'DevicePanel should initialize the dropdown by merging default and saved custom choices, then sorting by trailing four digits',
)
assert.match(
  componentSource,
  /function getDeviceSnSuffix\(sn: string\)[\s\S]*sn\.match\(\/\\d\{4\}\$\/\)/,
  'DevicePanel should extract the trailing four digits when sorting device SN choices',
)
assert.match(
  componentSource,
  /function compareDeviceSn\(left: string, right: string\)[\s\S]*getDeviceSnSuffix\(left\) - getDeviceSnSuffix\(right\)/,
  'DevicePanel should compare device SN choices by their trailing four-digit suffix',
)
assert.match(
  componentSource,
  /<input[\s\S]*@input="handleSnInput/,
  'Device SN should stay editable through a text input',
)
assert.match(
  componentSource,
  /<div v-if="snDropdownOpen" class="sn-dropdown"[\s\S]*<button[\s\S]*v-for="sn in deviceSnOptions"/,
  'DevicePanel should preserve the full SN dropdown list instead of using filtered browser datalist behavior',
)
assert.match(
  componentSource,
  /@click="addCurrentSnToOptions"/,
  'DevicePanel should expose an add button for saving the current device SN into the dropdown choices',
)
assert.match(
  componentSource,
  /'snAdded': \[sn: string\]/,
  'DevicePanel should emit the SN that was added so the parent can synchronize dependent fields',
)
assert.match(
  componentSource,
  /function addCurrentSnToOptions\(\)[\s\S]*const sn = props\.modelValue\.sn\.trim\(\)[\s\S]*if \(!sn \|\| deviceSnOptions\.value\.includes\(sn\)\) return[\s\S]*deviceSnOptions\.value = \[\.\.\.deviceSnOptions\.value, sn\]\.sort\(compareDeviceSn\)[\s\S]*saveCustomDeviceSnOptions\(\[\.\.\.new Set\(\[\.\.\.loadCustomDeviceSnOptions\(\), sn\]\)\]\.sort\(compareDeviceSn\)\)[\s\S]*emit\('snAdded', sn\)/,
  'DevicePanel should trim, de-duplicate, re-sort, persist, and emit the current SN after adding it',
)
assert.match(
  appSource,
  /<DevicePanel v-model="deviceForm" @snAdded="handleDeviceSnAdded" \/>/,
  'App should listen for SN additions from DevicePanel',
)
assert.match(
  appSource,
  /function handleDeviceSnAdded\(sn: string\)[\s\S]*updateSshPortForSN\(sn\)/,
  'App should update the obstacle monitor SSH port when a new SN is added',
)
assert.doesNotMatch(
  componentSource,
  /<datalist/,
  'DevicePanel should not rely on datalist because it hides previous choices when the input already has a value',
)
assert.match(
  componentSource,
  /'LK-MR641US000337'/,
  'DevicePanel should include LK-MR641US000337 in the SN dropdown choices',
)
assert.match(
  componentSource,
  /'LK-MR641US000339'/,
  'DevicePanel should include LK-MR641US000339 in the SN dropdown choices',
)
assert.match(
  monitorSource,
  /'LK-MR641US000337': 10337/,
  'Obstacle monitor should map LK-MR641US000337 to SSH port 10337',
)
assert.match(
  monitorSource,
  /'LK-MR641US000339': 10339/,
  'Obstacle monitor should map LK-MR641US000339 to SSH port 10339',
)
assert.match(
  monitorSource,
  /export function defaultSshPortForSN\(sn: string\)[\s\S]*sn\.match\(\/\\d\{4\}\$\/\)[\s\S]*return match \? Number\(`1\$\{match\[0\]\}`\) : null/,
  'Obstacle monitor should derive unknown SN ports as 1 plus the trailing four digits',
)
assert.match(
  monitorSource,
  /export function updateSshPortForSN\(sn: string\)[\s\S]*const port = SN_PORT_MAP\[sn\] \?\? defaultSshPortForSN\(sn\)/,
  'Obstacle monitor should update SSH port from explicit mappings or the SN trailing-four default',
)

console.log('device-sn-options test passed')
