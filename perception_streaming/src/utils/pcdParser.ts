export interface ParsedPcd {
  pos: Float32Array
  col: Float32Array
  pointCount: number
}

interface FieldSpec {
  name: string
  size: number
  type: string
  count: number
  offset: number
}

interface PcdHeader {
  fields: FieldSpec[]
  data: 'ascii' | 'binary'
  dataOffset: number
  points: number
  pointStep: number
}

const ASCII_DECODER = new TextDecoder('utf-8')

const DEFAULT_LABEL_COLOR: Record<number, [number, number, number]> = {
  0: [0, 0, 0],
  1: [0, 0, 200 / 255],
  2: [100 / 255, 255 / 255, 102 / 255],
  3: [118 / 255, 89 / 255, 0],
  4: [1, 1, 0],
  5: [1, 0, 0],
  6: [1, 165 / 255, 0],
  7: [1, 20 / 255, 147 / 255],
  8: [0, 1, 1],
  9: [245 / 255, 130 / 255, 48 / 255],
  10: [0, 64 / 255, 128 / 255],
  11: [34 / 255, 139 / 255, 34 / 255],
  12: [1, 192 / 255, 203 / 255],
  13: [138 / 255, 43 / 255, 226 / 255],
  100: [1, 0, 0],
  101: [1, 0, 0],
  102: [1, 0, 0],
  103: [1, 0, 1],
  104: [1, 0, 0],
  105: [1, 1, 0],
  106: [0, 1, 1],
  107: [0, 1, 0],
}
const DEFAULT_PASSABLE_LABELS = new Set([2, 3])

function defaultLabelColor(label: number): [number, number, number] {
  if (label === 7) return DEFAULT_LABEL_COLOR[5]
  return DEFAULT_LABEL_COLOR[label] ?? [0.5, 0.5, 0.5]
}

function decodeHeaderLine(bytes: Uint8Array, start: number, end: number) {
  let lineEnd = end
  if (lineEnd > start && bytes[lineEnd - 1] === 13) lineEnd -= 1
  return ASCII_DECODER.decode(bytes.subarray(start, lineEnd))
}

function numberList(raw: string | undefined, fallback: number) {
  if (!raw) return []
  return raw.trim().split(/\s+/).map((item) => {
    const value = Number(item)
    return Number.isFinite(value) ? value : fallback
  })
}

function parseHeader(buffer: ArrayBuffer): PcdHeader {
  const bytes = new Uint8Array(buffer)
  const headerValues = new Map<string, string>()
  let offset = 0

  while (offset < bytes.length) {
    const lineStart = offset
    while (offset < bytes.length && bytes[offset] !== 10) offset += 1
    const line = decodeHeaderLine(bytes, lineStart, offset).trim()
    const nextOffset = offset < bytes.length ? offset + 1 : offset
    offset = nextOffset

    if (!line || line.startsWith('#')) continue

    const firstSpace = line.search(/\s/)
    const key = (firstSpace >= 0 ? line.slice(0, firstSpace) : line).toUpperCase()
    const value = firstSpace >= 0 ? line.slice(firstSpace + 1).trim() : ''
    headerValues.set(key, value)

    if (key === 'DATA') {
      const data = value.toLowerCase()
      if (data !== 'ascii' && data !== 'binary') {
        throw new Error(`Unsupported PCD DATA format: ${value}`)
      }

      const fieldNames = (headerValues.get('FIELDS') || '').trim().split(/\s+/).filter(Boolean)
      const sizes = numberList(headerValues.get('SIZE'), 4)
      const types = (headerValues.get('TYPE') || '').trim().split(/\s+/).filter(Boolean)
      const counts = numberList(headerValues.get('COUNT'), 1)
      let fieldOffset = 0
      const fields = fieldNames.map((name, index) => {
        const size = sizes[index] || 4
        const count = counts[index] || 1
        const spec = {
          name,
          size,
          type: (types[index] || 'F').toUpperCase(),
          count,
          offset: fieldOffset,
        }
        fieldOffset += size * count
        return spec
      })
      const width = Number(headerValues.get('WIDTH') || 0)
      const height = Number(headerValues.get('HEIGHT') || 1)
      const points = Number(headerValues.get('POINTS') || width * height || 0)
      return { fields, data, dataOffset: nextOffset, points, pointStep: fieldOffset }
    }
  }

  throw new Error('Invalid PCD: missing DATA header')
}

function readNumber(view: DataView, offset: number, field: FieldSpec) {
  if (field.type === 'F') {
    if (field.size === 8) return view.getFloat64(offset, true)
    return view.getFloat32(offset, true)
  }
  if (field.type === 'I') {
    if (field.size === 1) return view.getInt8(offset)
    if (field.size === 2) return view.getInt16(offset, true)
    return view.getInt32(offset, true)
  }
  if (field.size === 1) return view.getUint8(offset)
  if (field.size === 2) return view.getUint16(offset, true)
  return view.getUint32(offset, true)
}

function packedFloatToUint(value: number) {
  const temp = new ArrayBuffer(4)
  const view = new DataView(temp)
  view.setFloat32(0, value, true)
  return view.getUint32(0, true)
}

function colorFromPackedRgb(value: number) {
  const rgb = value > 255 ? value : packedFloatToUint(value)
  return [
    ((rgb >> 16) & 0xff) / 255,
    ((rgb >> 8) & 0xff) / 255,
    (rgb & 0xff) / 255,
  ] as [number, number, number]
}

function pushPoint(
  pos: number[],
  col: number[],
  x: number,
  y: number,
  z: number,
  label: number,
  packedColor: number | undefined,
) {
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return
  pos.push(x, z, -y)
  const [r, g, b] = Number.isFinite(label)
    ? defaultLabelColor(label)
    : packedColor === undefined
      ? [0.5, 0.5, 0.5]
      : colorFromPackedRgb(packedColor)
  const dim = DEFAULT_PASSABLE_LABELS.has(label) ? 0.35 : 1.0
  col.push(r * dim, g * dim, b * dim)
}

function parseAscii(buffer: ArrayBuffer, header: PcdHeader): ParsedPcd {
  const body = ASCII_DECODER.decode(new Uint8Array(buffer, header.dataOffset))
  const xIndex = header.fields.findIndex((field) => field.name === 'x')
  const yIndex = header.fields.findIndex((field) => field.name === 'y')
  const zIndex = header.fields.findIndex((field) => field.name === 'z')
  const labelIndex = header.fields.findIndex((field) => field.name === 'label')
  const colorIndex = header.fields.findIndex((field) => field.name === 'rgb' || field.name === 'rgba')
  const pos: number[] = []
  const col: number[] = []

  for (const line of body.split('\n')) {
    const parts = line.trim().split(/\s+/)
    if (parts.length <= Math.max(xIndex, yIndex, zIndex)) continue
    const label = labelIndex >= 0 ? Number.parseInt(parts[labelIndex], 10) : Number.NaN
    const packedColor = colorIndex >= 0 ? Number.parseFloat(parts[colorIndex]) : undefined
    pushPoint(
      pos,
      col,
      Number.parseFloat(parts[xIndex]),
      Number.parseFloat(parts[yIndex]),
      Number.parseFloat(parts[zIndex]),
      label,
      packedColor,
    )
  }

  return { pos: new Float32Array(pos), col: new Float32Array(col), pointCount: pos.length / 3 }
}

function parseBinary(buffer: ArrayBuffer, header: PcdHeader): ParsedPcd {
  const xField = header.fields.find((field) => field.name === 'x')
  const yField = header.fields.find((field) => field.name === 'y')
  const zField = header.fields.find((field) => field.name === 'z')
  if (!xField || !yField || !zField || header.pointStep <= 0) {
    return { pos: new Float32Array(), col: new Float32Array(), pointCount: 0 }
  }

  const labelField = header.fields.find((field) => field.name === 'label')
  const colorField = header.fields.find((field) => field.name === 'rgb' || field.name === 'rgba')
  const availablePoints = Math.floor((buffer.byteLength - header.dataOffset) / header.pointStep)
  const pointCount = Math.min(header.points || availablePoints, availablePoints)
  const view = new DataView(buffer)
  const pos: number[] = []
  const col: number[] = []

  for (let pointIndex = 0; pointIndex < pointCount; pointIndex += 1) {
    const base = header.dataOffset + pointIndex * header.pointStep
    const label = labelField ? Math.trunc(readNumber(view, base + labelField.offset, labelField)) : Number.NaN
    const packedColor = colorField ? readNumber(view, base + colorField.offset, colorField) : undefined
    pushPoint(
      pos,
      col,
      readNumber(view, base + xField.offset, xField),
      readNumber(view, base + yField.offset, yField),
      readNumber(view, base + zField.offset, zField),
      label,
      packedColor,
    )
  }

  return { pos: new Float32Array(pos), col: new Float32Array(col), pointCount: pos.length / 3 }
}

export function parsePcdBuffer(buffer: ArrayBuffer): ParsedPcd {
  const header = parseHeader(buffer)
  return header.data === 'binary' ? parseBinary(buffer, header) : parseAscii(buffer, header)
}
