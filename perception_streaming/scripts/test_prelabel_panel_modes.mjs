import assert from 'assert'
import { readFileSync } from 'fs'

const source = readFileSync(new URL('../src/components/PrelabelPipelinePanel.vue', import.meta.url), 'utf8')

for (const required of ['shadow_ab', '/prelabel/shadow-run', '/review/invites', 'review_token', '/review/assets/', 'X better', 'Y better']) {
  assert.ok(source.includes(required), `missing A/B review UI contract: ${required}`)
}
for (const forbidden of ['candidate_task_identity', 'alpha50-']) {
  assert.ok(!source.includes(forbidden), `anonymous review surface leaks identity: ${forbidden}`)
}

console.log('Prelabel shadow mode UI static contract passed')
