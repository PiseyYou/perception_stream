const sourceMeta = {
    robot_decision: { sourceLabel: 'robot_decision', sourceTone: 'decision', order: 0 },
    nav: { sourceLabel: 'nav', sourceTone: 'nav', order: 1 },
    stereo: { sourceLabel: 'stereo', sourceTone: 'stereo', order: 2 },
};
function parseTs(ts) {
    const match = /^(\d{2}):(\d{2}):(\d{2})$/.exec(ts);
    if (!match)
        return Number.POSITIVE_INFINITY;
    const [, hh, mm, ss] = match;
    return Number(hh) * 3600 + Number(mm) * 60 + Number(ss);
}
export function buildMergedTimeline(categories) {
    const rows = [];
    ['robot_decision', 'nav', 'stereo'].forEach((source) => {
        const list = categories[source] || [];
        const meta = sourceMeta[source];
        for (const row of list) {
            rows.push({
                source,
                ts: row.ts,
                text: row.text,
                sourceLabel: meta.sourceLabel,
                sourceTone: meta.sourceTone,
            });
        }
    });
    return rows.sort((a, b) => {
        const timeDiff = parseTs(a.ts) - parseTs(b.ts);
        if (timeDiff !== 0)
            return timeDiff;
        return sourceMeta[a.source].order - sourceMeta[b.source].order;
    });
}
