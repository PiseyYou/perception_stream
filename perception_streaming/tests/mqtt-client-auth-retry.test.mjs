import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const mqttClientPath = path.resolve(__dirname, '../src/utils/mqttClient.ts')
const source = fs.readFileSync(mqttClientPath, 'utf8')

assert.match(
  source,
  /private connectionFailed = false/,
  'MQTT client should track failed auth state explicitly',
)
assert.match(
  source,
  /if \(error\.message\?\.includes\('Connection refused: Not authorized'\)\) \{[\s\S]*?this\.client\?\.end\(true\)[\s\S]*?this\.client = null[\s\S]*?\}/,
  'MQTT client should tear down the socket after auth rejection so the next connect can use new credentials',
)
assert.match(
  source,
  /disconnect\(\): string \{[\s\S]*?if \(this\.client\) \{[\s\S]*?this\.client\.end\(true, \(\) => \{[\s\S]*?this\.client = null[\s\S]*?this\.connectionFailed = false[\s\S]*?\}\)/,
  'Disconnect should clear stale client state even when the broker already rejected the session',
)
assert.match(
  source,
  /if \(!this\.client \|\| !this\.client\.connected\) return 'MQTT Not Connected'/,
  'Publish should reject sends until the MQTT socket is actually connected',
)

console.log('mqtt-client-auth-retry test passed')
