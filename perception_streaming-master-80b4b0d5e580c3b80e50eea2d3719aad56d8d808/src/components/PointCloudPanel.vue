<template>
  <div class="panel point-cloud-panel">
    <div class="panel-header">
      <span class="panel-title">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="2"/><circle cx="4" cy="6" r="2"/><circle cx="20" cy="6" r="2"/>
          <circle cx="4" cy="18" r="2"/><circle cx="20" cy="18" r="2"/>
        </svg>
        点云可视化
      </span>
      <div class="pcl-actions">
        <span class="pcl-status">
          <span class="status-dot" :class="{ active: wsConnected }"></span>
          {{ statusText }}
        </span>
        <button v-if="pclEnabled" class="btn-pcl" @click="disconnectPcl" title="断开点云">断开</button>
        <button v-else class="btn-pcl btn-pcl-connect" @click="reconnectPcl" title="连接点云">连接</button>
        <button class="btn-pcl btn-pcl-collapse" @click="emit('collapse')" title="收缩点云面板">◀</button>
      </div>
    </div>
    <div v-if="pclEnabled" class="pcl-body">
      <canvas ref="canvasRef" class="pcl-canvas" />
    </div>
    <div v-else class="pcl-disabled">
      <span>点云已断开</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as THREE from 'three'

const WS_URL = 'ws://localhost:8767'

const emit = defineEmits<{ (e: 'collapse'): void }>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const wsConnected = ref(false)
const statusText = ref('连接中...')
const pclEnabled = ref(true)

// ─── Three.js ────────────────────────────────────────
let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let points: THREE.Points | null = null
let animFrameId = 0
let isDragging = false
let lastMouse = { x: 0, y: 0 }
let spherical = { theta: 0.5, phi: 1.0, radius: 10 }

function initThree(canvas: HTMLCanvasElement) {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
  renderer.setPixelRatio(window.devicePixelRatio)
  renderer.setClearColor(0x1e1e2e)

  scene = new THREE.Scene()
  scene.add(new THREE.AxesHelper(1))
  scene.add(new THREE.GridHelper(10, 10, 0x333355, 0x222244))

  const w = canvas.clientWidth || canvas.offsetWidth || 400
  const h = canvas.clientHeight || canvas.offsetHeight || 560
  camera = new THREE.PerspectiveCamera(60, w / h, 0.01, 1000)
  updateCamera()
  renderer.setSize(w, h, false)

  canvas.addEventListener('mousedown', (e) => { isDragging = true; lastMouse = { x: e.clientX, y: e.clientY } })
  canvas.addEventListener('mouseup', () => { isDragging = false })
  canvas.addEventListener('mouseleave', () => { isDragging = false })
  canvas.addEventListener('mousemove', (e) => {
    if (!isDragging) return
    spherical.theta -= (e.clientX - lastMouse.x) * 0.01
    spherical.phi = Math.max(0.1, Math.min(Math.PI - 0.1, spherical.phi + (e.clientY - lastMouse.y) * 0.01))
    lastMouse = { x: e.clientX, y: e.clientY }
    updateCamera()
  })
  canvas.addEventListener('wheel', (e) => {
    spherical.radius = Math.max(0.5, spherical.radius + e.deltaY * 0.01)
    updateCamera()
  })

  animate()
}

function updateCamera() {
  if (!camera) return
  const { theta, phi, radius } = spherical
  camera.position.set(
    radius * Math.sin(phi) * Math.sin(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.cos(theta),
  )
  camera.lookAt(0, 0, 0)
}

function animate() {
  animFrameId = requestAnimationFrame(animate)
  if (renderer && scene && camera) renderer.render(scene, camera)
}

// ─── Label color LUT (BGR→RGB from C++ getColorLookupTable) ──
// label=1: deep blue (background), label=2: green (grass), label=3: brownish (road)
const LABEL_COLOR: Record<number, [number, number, number]> = {
  0:   [0,        0,        0       ],  // black
  1:   [0,        0,        200/255 ],  // background  → deep blue
  2:   [100/255,  255/255,  102/255 ],  // grass       → green
  3:   [118/255,  89/255,   0       ],  // road        → brownish
  4:   [255/255,  255/255,  0       ],  // dynamic     → yellow
  5:   [255/255,  0,        0       ],  // static_obstacle → red
  6:   [255/255,  165/255,  0       ],  // wall        → orange
  7:   [255/255,  20/255,   147/255 ],  // vehicle     → deep pink
  8:   [0,        255/255,  255/255 ],  // pole        → cyan
  9:   [245/255,  130/255,  48/255  ],  // impassable  → orange
  10:  [0,        64/255,   128/255 ],  // depression  → dark blue
  11:  [34/255,   139/255,  34/255  ],  // bush        → forest green
  12:  [255/255,  192/255,  203/255 ],  // limb_bush   → pink
  13:  [138/255,  43/255,   226/255 ],  // CES_arod    → violet
  100: [255/255,  0,        0       ],  // pole (100+) → red
  101: [255/255,  0,        0       ],  // obst
  102: [255/255,  0,        0       ],  // fixo
  103: [255/255,  0,        255/255 ],  // car         → magenta
  104: [255/255,  0,        0       ],  // stat
  105: [0,        255/255,  255/255 ],  // dyna        → cyan
  106: [255/255,  255/255,  0       ],  // charge_station → yellow
}
function labelToColor(label: number): [number, number, number] {
  return LABEL_COLOR[label] ?? [1.0, 0.0, 0.5]
}

// ─── Point cloud parser ───────────────────────────────
// Binary format from pcl_ws_bridge.py:
// height(4) + width(4) + point_step(4) + raw_data
// PointXYZRGBL layout: x(0) y(4) z(8) rgb(12) label(16), step=20
function updatePointCloud(buf: ArrayBuffer) {
  if (!scene || buf.byteLength < 16) return
  const view = new DataView(buf)
  const height = view.getUint32(0, true)
  const width = view.getUint32(4, true)
  const pointStep = view.getUint32(8, true)
  const labelOffset = view.getUint32(12, true)  // 0xFFFFFFFF = unknown
  const numPoints = height * width
  const dataOffset = 16

  if (pointStep < 12 || buf.byteLength < dataOffset + numPoints * pointStep) return

  const hasLabel = labelOffset !== 0xFFFFFFFF && labelOffset + 4 <= pointStep

  const positions = new Float32Array(numPoints * 3)
  const colors = new Float32Array(numPoints * 3)
  let valid = 0

  for (let i = 0; i < numPoints; i++) {
    const base = dataOffset + i * pointStep
    const x = view.getFloat32(base, true)
    const y = view.getFloat32(base + 4, true)
    const z = view.getFloat32(base + 8, true)
    if (!isFinite(x) || !isFinite(y) || !isFinite(z)) continue
    positions[valid * 3] = x
    positions[valid * 3 + 1] = z
    positions[valid * 3 + 2] = -y
    let r: number, g: number, b: number
    if (hasLabel) {
      const label = view.getUint32(base + labelOffset, true)
      ;[r, g, b] = labelToColor(label)
    } else {
      const t = Math.min(1, Math.max(0, (z + 1) / 3))
      r = t; g = 1 - Math.abs(t - 0.5) * 2; b = 1 - t
    }
    colors[valid * 3] = r
    colors[valid * 3 + 1] = g
    colors[valid * 3 + 2] = b
    valid++
  }

  if (!points) {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(numPoints * 3), 3))
    geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(numPoints * 3), 3))
    points = new THREE.Points(geo, new THREE.PointsMaterial({ size: 0.05, vertexColors: true }))
    scene.add(points)
  }
  const geo = points.geometry as THREE.BufferGeometry
  const posBuf = geo.attributes.position as THREE.BufferAttribute
  const colBuf = geo.attributes.color as THREE.BufferAttribute
  // Resize backing array if needed
  if (posBuf.array.length < valid * 3) {
    geo.setAttribute('position', new THREE.BufferAttribute(positions.slice(0, valid * 3), 3))
    geo.setAttribute('color', new THREE.BufferAttribute(colors.slice(0, valid * 3), 3))
  } else {
    (posBuf.array as Float32Array).set(positions.subarray(0, valid * 3))
    ;(colBuf.array as Float32Array).set(colors.subarray(0, valid * 3))
    posBuf.needsUpdate = true
    colBuf.needsUpdate = true
  }
  geo.setDrawRange(0, valid)
}

// ─── WebSocket ────────────────────────────────────────
let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let connectFails = 0
const MAX_CONNECT_FAILS = 3

function connect() {
  if (ws) return
  statusText.value = '连接中...'
  ws = new WebSocket(WS_URL)
  ws.binaryType = 'arraybuffer'

  ws.onopen = () => {
    wsConnected.value = true
    connectFails = 0
    statusText.value = 'WS 已连接'
  }
  ws.onmessage = (e) => updatePointCloud(e.data as ArrayBuffer)
  ws.onclose = () => {
    wsConnected.value = false
    ws = null
    connectFails++
    if (connectFails >= MAX_CONNECT_FAILS) {
      statusText.value = '连接失败，请点击「连接」按钮重试'
      return
    }
    statusText.value = `重连中 (${connectFails}/${MAX_CONNECT_FAILS})...`
    reconnectTimer = setTimeout(connect, 3000)
  }
  ws.onerror = () => {
    ws?.close()
  }
}

// ─── Resize ───────────────────────────────────────────
let resizeObserver: ResizeObserver | null = null

function disconnectPcl() {
  pclEnabled.value = false
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  ws?.close()
  ws = null
  wsConnected.value = false
  statusText.value = '已断开'
}

function reconnectPcl() {
  pclEnabled.value = true
  connectFails = 0
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  ws?.close()
  ws = null
  connect()
}

onMounted(async () => {
  await nextTick()
  const canvas = canvasRef.value!
  initThree(canvas)
  connect()
  resizeObserver = new ResizeObserver(() => {
    const w = canvas.clientWidth, h = canvas.clientHeight
    if (!w || !h) return
    renderer?.setSize(w, h, false)
    if (camera) { camera.aspect = w / h; camera.updateProjectionMatrix() }
  })
  resizeObserver.observe(canvas)
})

onBeforeUnmount(() => {
  cancelAnimationFrame(animFrameId)
  if (reconnectTimer) clearTimeout(reconnectTimer)
  ws?.close()
  resizeObserver?.disconnect()
  renderer?.dispose()
})
</script>
