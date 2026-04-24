import assert from 'node:assert/strict'

import { consumeSseJsonChunk } from '../src/utils/sseJsonStream.js'

function runParser(chunks: string[]) {
  let remainder = ''
  const events: unknown[] = []
  const errors: string[] = []

  for (const chunk of chunks) {
    const result = consumeSseJsonChunk(remainder, chunk)
    remainder = result.remainder
    events.push(...result.events)
    errors.push(...result.errors.map((error) => error.payload))
  }

  return { remainder, events, errors }
}

const largeEvent = JSON.stringify({
  category: 'images',
  items: Array.from({ length: 120 }, (_, index) => ({
    id: index,
    path: `/tmp/perception_stereo_20260413_0424${String(index).padStart(2, '0')}.jpg`,
  })),
})

const chunks = [
  `data: ${JSON.stringify({ step: 'start', percent: 0 })}\n\n`,
  `data: ${largeEvent.slice(0, 1700)}`,
  largeEvent.slice(1700, 3300),
  `${largeEvent.slice(3300)}\n\n`,
  'data: {"broken": true\n\n',
  `data: ${JSON.stringify({ done: true })}\n\n`,
]

const parsed = runParser(chunks)

assert.equal(parsed.remainder, '', 'complete SSE stream should not leave buffered text')
assert.deepEqual(
  parsed.events,
  [
    { step: 'start', percent: 0 },
    JSON.parse(largeEvent),
    { done: true },
  ],
  'parser should recover chunked JSON events and keep later valid events reachable',
)
assert.equal(parsed.errors.length, 1, 'parser should surface exactly one malformed SSE payload')
assert.match(parsed.errors[0], /"broken": true/, 'malformed payload should be reported for diagnostics')

console.log('sse-json-stream test passed')
