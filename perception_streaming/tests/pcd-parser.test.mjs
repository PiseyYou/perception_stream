import assert from 'node:assert/strict'

import { parsePcdBuffer } from '../src/utils/pcdParser.ts'

function makeBinaryPcd() {
  const header = [
    '# .PCD v0.7 - Point Cloud Data file format',
    'VERSION 0.7',
    'FIELDS x y z rgba label',
    'SIZE 4 4 4 4 4',
    'TYPE F F F U U',
    'COUNT 1 1 1 1 1',
    'WIDTH 2',
    'HEIGHT 1',
    'VIEWPOINT 0 0 0 1 0 0 0',
    'POINTS 2',
    'DATA binary',
    '',
  ].join('\n')
  const headerBytes = new TextEncoder().encode(header)
  const body = new ArrayBuffer(40)
  const view = new DataView(body)

  view.setFloat32(0, 1.25, true)
  view.setFloat32(4, -2.5, true)
  view.setFloat32(8, 3.75, true)
  view.setUint32(12, 0x11223344, true)
  view.setUint32(16, 5, true)

  view.setFloat32(20, -4, true)
  view.setFloat32(24, 5.5, true)
  view.setFloat32(28, 6.25, true)
  view.setUint32(32, 0x55667788, true)
  view.setUint32(36, 2, true)

  const bytes = new Uint8Array(headerBytes.length + body.byteLength)
  bytes.set(headerBytes)
  bytes.set(new Uint8Array(body), headerBytes.length)
  return bytes.buffer
}

const parsedBinary = parsePcdBuffer(makeBinaryPcd())
assert.equal(parsedBinary.pointCount, 2, 'binary PCD should expose valid points')
assert.deepEqual(
  Array.from(parsedBinary.pos.slice(0, 6)).map((value) => Number(value.toFixed(2))),
  [1.25, 3.75, 2.5, -4, 6.25, -5.5],
  'binary PCD should use the StereoAnalysis2 coordinate remap',
)

const asciiPcd = [
  'FIELDS x y z rgb label',
  'SIZE 4 4 4 4 4',
  'TYPE F F F F U',
  'COUNT 1 1 1 1 1',
  'WIDTH 1',
  'HEIGHT 1',
  'POINTS 1',
  'DATA ascii',
  '1 -2 3 0 5',
  '',
].join('\n')
const parsedAscii = parsePcdBuffer(new TextEncoder().encode(asciiPcd).buffer)
assert.equal(parsedAscii.pointCount, 1, 'ascii PCD behavior should stay intact')

console.log('pcd-parser test passed')
