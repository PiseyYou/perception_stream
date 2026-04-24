export function consumeSseJsonChunk(remainder, chunk) {
    const normalized = `${remainder}${chunk}`.replace(/\r\n/g, '\n');
    const parts = normalized.split('\n\n');
    const nextRemainder = parts.pop() ?? '';
    const events = [];
    const errors = [];
    for (const part of parts) {
        if (!part.trim())
            continue;
        const payload = part
            .split('\n')
            .filter((line) => line.startsWith('data:'))
            .map((line) => line.slice(5).trimStart())
            .join('\n')
            .trim();
        if (!payload)
            continue;
        try {
            events.push(JSON.parse(payload));
        }
        catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            errors.push({ payload, message });
        }
    }
    return {
        remainder: nextRemainder,
        events,
        errors,
    };
}
