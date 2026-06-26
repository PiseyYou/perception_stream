import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const appPath = path.resolve(__dirname, '../src/App.vue')
const source = fs.readFileSync(appPath, 'utf8')

assert.match(
  source,
  /const LEGACY_STORAGE_KEY = 'perception_streaming_mqtt_creds'/,
  'App should keep the legacy MQTT credential key only for cleanup, not active reads',
)
assert.match(
  source,
  /const STORAGE_KEY_PREFIX = 'perception_streaming_mqtt_creds_v2'/,
  'App should version the MQTT credential storage key after the broker migration',
)
assert.match(
  source,
  /function getCredentialStorageKey\(broker: string\) \{\s*return `\$\{STORAGE_KEY_PREFIX\}:\$\{broker\}`\s*\}/,
  'App should scope saved MQTT credentials by broker host',
)
assert.match(
  source,
  /const savedCreds = loadSavedCredentials\(DEFAULT_MQTT_BROKER\)/,
  'App should load saved credentials for the current default broker only',
)
assert.match(
  source,
  /\(\) => \[connectionForm\.value\.broker, connectionForm\.value\.username, connectionForm\.value\.password\] as const/,
  'App should watch broker changes when persisting MQTT credentials',
)
assert.match(
  source,
  /saveCredentials\(c\.broker, c\.username, c\.password\)/,
  'Manual connect should persist credentials under the selected broker key',
)
assert.doesNotMatch(
  source,
  /const saved = localStorage\.getItem\(LEGACY_STORAGE_KEY\)/,
  'App should not keep loading credentials from the legacy cross-broker cache key',
)

console.log('mqtt-credential-storage test passed')
