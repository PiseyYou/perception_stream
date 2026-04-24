import assert from 'node:assert/strict'

import { clearAnalysisMemoryCache, readAnalysisCache, writeAnalysisCache } from '../src/utils/analysisCache.js'

class FakeStorage {
  private map = new Map<string, string>()

  constructor(private readonly maxChars = Number.POSITIVE_INFINITY) {}

  getItem(key: string) {
    return this.map.get(key) ?? null
  }

  setItem(key: string, value: string) {
    if (value.length > this.maxChars) {
      throw new Error('quota exceeded')
    }
    this.map.set(key, value)
  }

  removeItem(key: string) {
    this.map.delete(key)
  }
}

function installStorage(storage: Storage) {
  Object.defineProperty(globalThis, 'window', {
    value: { sessionStorage: storage },
    configurable: true,
  })
}

const cacheKey = 'data/log_debug/0286|data/stereo_debug/0286'
const hugeData = {
  avoiding_count: 44,
  image_count: 67,
  time_range: '03:17:00 ~ 23:08:10',
  categories: {
    stereo: Array.from({ length: 4000 }, (_, index) => ({
      ts: '22:48:21',
      text: `stereo line ${index} ${'x'.repeat(80)}`,
    })),
  },
}

const tinyStorage = new FakeStorage(600)
installStorage(tinyStorage as unknown as Storage)

const writeMode = writeAnalysisCache(cacheKey, hugeData)
assert.equal(writeMode, 'summary', 'large payloads should fall back to summary persistence')

const firstRead = readAnalysisCache(cacheKey)
assert.equal(firstRead?.kind, 'full', 'memory cache should still return the full payload in-page')

clearAnalysisMemoryCache(cacheKey)

const secondRead = readAnalysisCache(cacheKey)
assert.equal(secondRead?.kind, 'summary', 'persisted cache should degrade to summary when storage is small')
assert.equal(secondRead?.summary.avoiding_count, 44)
assert.equal(secondRead?.summary.image_count, 67)

console.log('analysis-cache test passed')
