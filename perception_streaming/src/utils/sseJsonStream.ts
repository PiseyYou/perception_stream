export interface SseJsonParseError {
  payload: string
  message: string
}

export interface SseJsonChunkResult {
  remainder: string
  events: unknown[]
  errors: SseJsonParseError[]
}

export function consumeSseJsonChunk(remainder: string, chunk: string): SseJsonChunkResult {
  const normalized = `${remainder}${chunk}`.replace(/\r\n/g, '\n')
  const parts = normalized.split('\n\n')
  const nextRemainder = parts.pop() ?? ''
  const events: unknown[] = []
  const errors: SseJsonParseError[] = []

  for (const part of parts) {
    if (!part.trim()) continue

    const payload = part
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n')
      .trim()

    if (!payload) continue

    try {
      events.push(JSON.parse(payload))
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      errors.push({ payload, message })
    }
  }

  return {
    remainder: nextRemainder,
    events,
    errors,
  }
}
