import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const configPath = path.join(root, 'stereo_perception_multi2_offline_test/include/offline_config.hpp')
const config = fs.readFileSync(configPath, 'utf8')

const modelMatch = config.match(/mul_sub_model_name\s*=\s*"([^"]+)"/)
assert.ok(modelMatch, 'day offline debug should configure a Model 6 default model')

const modelName = modelMatch[1]
const modelPath = path.join(root, 'stereo_perception_multi2_offline_test/models', modelName)
assert.ok(
  fs.existsSync(modelPath),
  `day offline debug default model should exist in stereo offline model dir: ${modelName}`,
)

console.log('stereo-offline-day-debug-model test passed')
