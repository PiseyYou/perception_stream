import assert from 'assert'
import { readFileSync } from 'fs'

const source = readFileSync(new URL('../src/components/PrelabelPipelinePanel.vue', import.meta.url), 'utf8')
const viteSource = readFileSync(new URL('../vite.config.ts', import.meta.url), 'utf8')

for (const required of ['shadow_ab', '/prelabel/shadow-run', '/review/invites', 'review_token', '/review/assets/', 'X better', 'Y better']) {
  assert.ok(source.includes(required), `missing A/B review UI contract: ${required}`)
}
for (const forbidden of ['candidate_task_identity', 'alpha50-']) {
  assert.ok(!source.includes(forbidden), `anonymous review surface leaks identity: ${forbidden}`)
}

for (const required of [
  'class="file-input"\n              :disabled="uploading"',
  ':disabled="!selectedFiles.length || uploading" @click="clearUploadSelection"',
  ':disabled="!selectedFiles.length || uploading" @click="uploadSelectedFiles(true)"',
]) {
  assert.ok(source.includes(required), `background A/B run must not block staging another upload: ${required}`)
}

assert.ok(source.includes("pushLog({ type: 'log', level: 'info', msg: `已选择新的上传批次"),
  'choosing another folder must explicitly start a new upload batch')

console.log('Prelabel shadow mode UI static contract passed')

assert.ok(viteSource.includes("process.env.ENABLE_ROBOT_BRIDGE !== '0'"),
  'A/B service must be able to disable its conflicting robot bridge helpers')
