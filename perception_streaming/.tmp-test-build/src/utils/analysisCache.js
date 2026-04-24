const STORAGE_PREFIX = 'analysis_cache_';
const MAX_PERSIST_CHARS = 180_000;
const memoryCache = new Map();
function getStorage() {
    if (typeof window === 'undefined' || !window.sessionStorage)
        return null;
    return window.sessionStorage;
}
function getStorageKey(cacheKey) {
    return `${STORAGE_PREFIX}${cacheKey}`;
}
function buildSummary(data) {
    return {
        avoiding_count: Number(data?.avoiding_count || 0),
        image_count: Number(data?.image_count || 0),
        time_range: String(data?.time_range || ''),
        cached_at: new Date().toISOString(),
    };
}
function safeReplace(storage, key, value) {
    try {
        storage.removeItem(key);
        storage.setItem(key, value);
        return true;
    }
    catch {
        return false;
    }
}
export function writeAnalysisCache(cacheKey, data) {
    memoryCache.set(cacheKey, data);
    const storage = getStorage();
    if (!storage)
        return 'memory-only';
    const storageKey = getStorageKey(cacheKey);
    const fullEnvelope = { version: 1, mode: 'full', data };
    const fullText = JSON.stringify(fullEnvelope);
    if (fullText.length <= MAX_PERSIST_CHARS && safeReplace(storage, storageKey, fullText)) {
        return 'full';
    }
    const summaryEnvelope = {
        version: 1,
        mode: 'summary',
        data: buildSummary(data),
    };
    if (safeReplace(storage, storageKey, JSON.stringify(summaryEnvelope))) {
        return 'summary';
    }
    storage.removeItem(storageKey);
    return 'memory-only';
}
export function readAnalysisCache(cacheKey) {
    if (memoryCache.has(cacheKey)) {
        return { kind: 'full', data: memoryCache.get(cacheKey) };
    }
    const storage = getStorage();
    if (!storage)
        return null;
    const raw = storage.getItem(getStorageKey(cacheKey));
    if (!raw)
        return null;
    try {
        const parsed = JSON.parse(raw);
        if (parsed?.version === 1 && parsed?.mode === 'full') {
            return { kind: 'full', data: parsed.data };
        }
        if (parsed?.version === 1 && parsed?.mode === 'summary') {
            return { kind: 'summary', summary: parsed.data };
        }
        return { kind: 'full', data: parsed };
    }
    catch {
        storage.removeItem(getStorageKey(cacheKey));
        return null;
    }
}
export function clearAnalysisCache(cacheKey) {
    memoryCache.delete(cacheKey);
    const storage = getStorage();
    storage?.removeItem(getStorageKey(cacheKey));
}
export function clearAnalysisMemoryCache(cacheKey) {
    memoryCache.delete(cacheKey);
}
