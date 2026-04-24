export interface AnalysisTimelineRow {
  source: 'robot_decision' | 'nav' | 'stereo'
  ts: string
  text: string
  sourceLabel: string
  sourceTone: 'decision' | 'nav' | 'stereo'
}

interface RowInput {
  ts: string
  text: string
}

interface CategoryInput {
  robot_decision?: RowInput[]
  nav?: RowInput[]
  stereo?: RowInput[]
}

const sourceMeta = {
  robot_decision: { sourceLabel: 'robot_decision', sourceTone: 'decision' as const, order: 0 },
  nav: { sourceLabel: 'nav', sourceTone: 'nav' as const, order: 1 },
  stereo: { sourceLabel: 'stereo', sourceTone: 'stereo' as const, order: 2 },
}

function parseTs(ts: string) {
  const match = /^(\d{2}):(\d{2}):(\d{2})$/.exec(ts)
  if (!match) return Number.POSITIVE_INFINITY
  const [, hh, mm, ss] = match
  return Number(hh) * 3600 + Number(mm) * 60 + Number(ss)
}

export function buildMergedTimeline(categories: CategoryInput): AnalysisTimelineRow[] {
  const rows: AnalysisTimelineRow[] = []

  ;(['robot_decision', 'nav', 'stereo'] as const).forEach((source) => {
    const list = categories[source] || []
    const meta = sourceMeta[source]
    for (const row of list) {
      rows.push({
        source,
        ts: row.ts,
        text: row.text,
        sourceLabel: meta.sourceLabel,
        sourceTone: meta.sourceTone,
      })
    }
  })

  return rows.sort((a, b) => {
    const timeDiff = parseTs(a.ts) - parseTs(b.ts)
    if (timeDiff !== 0) return timeDiff
    return sourceMeta[a.source].order - sourceMeta[b.source].order
  })
}
