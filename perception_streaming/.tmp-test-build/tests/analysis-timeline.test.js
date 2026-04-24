import assert from 'node:assert/strict';
import { buildMergedTimeline } from '../src/utils/analysisTimeline.js';
const merged = buildMergedTimeline({
    nav: [
        { ts: '03:17:02', text: 'nav later' },
        { ts: '??:??:??', text: 'nav unknown' },
    ],
    stereo: [
        { ts: '03:17:01', text: 'stereo first' },
    ],
    robot_decision: [
        { ts: '03:17:01', text: 'decision first same time' },
        { ts: '03:17:03', text: 'decision last' },
    ],
});
assert.deepEqual(merged.map((row) => `${row.ts}|${row.source}|${row.text}`), [
    '03:17:01|robot_decision|decision first same time',
    '03:17:01|stereo|stereo first',
    '03:17:02|nav|nav later',
    '03:17:03|robot_decision|decision last',
    '??:??:??|nav|nav unknown',
], 'timeline rows should interleave by timestamp and place unknown timestamps last');
console.log('analysis-timeline test passed');
