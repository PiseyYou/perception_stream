<template>
  <div class="sa2-root">
    <div class="sa2-input-bar">
      <label>📁 nav包路径:</label>
      <input v-model="navPath" class="sa2-path-input" placeholder="输入nav包路径" :disabled="parsing" @keyup.enter="parseNavBag" />
      <button class="sa2-scan-btn" :disabled="parsing || !navPath" @click="parseNavBag">
        {{ parsing ? '⏳ 解析中...' : '🔍 解析nav包' }}
      </button>
      <span class="sa2-sep">|</span>
      <label>📂 单目文件夹输入目录:</label>
      <input
        v-model="inputDir"
        class="sa2-path-input"
        placeholder="选择或直接输入图片目录路径"
        :disabled="running"
        @keyup.enter="checkExistingResult"
        @blur="checkExistingResult"
      />
      <label>推理模式:</label>
      <select v-model="inferMode" class="sa2-label-input" :disabled="running">
        <option v-for="m in modes" :key="m.value" :value="m.value">{{ m.label }}</option>
      </select>
      <label>腐蚀像素:</label>
      <input v-model.number="erodePixel" type="number" class="sa2-label-input" :disabled="running" />
      <button class="sa2-dbg-btn" :disabled="running || !inputDir" @click="startTest">
        {{ running ? '⏳ 运行中...' : '▶ 离线测试' }}
      </button>
      <button v-if="running" class="sa2-arch-btn" @click="stopTest">■ 停止</button>

      <!-- Progress bar -->
      <div v-if="running" class="sa2-progress-container">
        <div class="sa2-progress-bar" :style="{ width: progressPercent + '%' }"></div>
        <span class="sa2-progress-text">{{ progressPercent }}% ({{ progressCurrent }}/{{ progressTotal }})</span>
      </div>
      <span v-else-if="outputDir" class="sa2-status">输出: {{ outputDir }}</span>
    </div>

    <!-- Preview section for extracted images -->
    <div v-if="extractedImages.length" class="sa2-legend">
      <span class="sa2-nav-info">解析预览</span>
      <span class="sa2-sep">|</span>
      <span class="sa2-li">图片: {{ extractedImages.length }}</span>
    </div>

    <div v-if="extractedImages.length" class="sa2-preview-section">
      <div class="sa2-preview-group">
        <div class="sa2-panel-label">图片预览 ({{ extractedImageDir }})</div>
        <div class="sa2-thumb-strip">
          <div
            v-for="(img, idx) in extractedImages.slice(0, 20)"
            :key="img"
            class="sa2-thumb-item"
            :class="{ active: isExtractedImageSelected(idx) }"
            @click="selectExtractedImage(idx)"
          >
            <img :src="getImageUrl(img)" loading="lazy" @error="onImageError" />
            <div class="sa2-thumb-name">{{ idx + 1 }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Terminal log -->
    <div class="sa2-log-section">
      <div class="sa2-panel-label">运行日志</div>
      <div class="sa2-log" ref="logRef">
        <div v-for="(line, i) in logs" :key="i" class="log-line" :class="logClass(line)">{{ line }}</div>
        <div v-if="!logs.length" class="log-empty">等待运行...</div>
      </div>
    </div>

    <!-- Result images section with navigation and point cloud -->
    <div v-if="resultImages.length" class="sa2-result-section">
      <div class="sa2-panel-label">
        处理结果 ({{ resultImages.length }} 张)
        <span v-if="selectedResultIdx >= 0" class="sa2-result-info">
          - 第 {{ selectedResultIdx + 1 }}/{{ resultImages.length }} 张
        </span>
      </div>
      <div class="sa2-result-nav">
        <button @click="prevResult" :disabled="selectedResultIdx <= 0">上一张</button>
        <button @click="nextResult" :disabled="selectedResultIdx >= resultImages.length - 1">下一张</button>
      </div>
      <div class="sa2-result-layout-split">
        <div class="sa2-result-left-panel">
          <div class="sa2-panel-sublabel">拼接结果图</div>
          <img
            v-if="selectedResultIdx >= 0"
            :src="getResultImageUrl(resultImages[selectedResultIdx])"
            class="sa2-result-img"
            @click="zoomUrl = getResultImageUrl(resultImages[selectedResultIdx])"
          />
          <div v-else class="sa2-placeholder">等待加载结果</div>
        </div>
        <div class="sa2-result-right-panel">
          <div class="sa2-panel-sublabel">原始点云 <span class="sa2-pcd-status">{{ pcdStatus }}</span></div>
          <div v-if="selectedResultIdx < 0" class="sa2-placeholder">等待选择</div>
          <canvas v-else ref="pcdCanvasRef" class="sa2-pcd-canvas" />
        </div>
      </div>
    </div>

    <div v-if="!extractedImages.length && !logs.length" class="sa2-empty">
      请输入nav包路径并点击解析
    </div>

    <!-- Zoom overlay -->
    <div v-if="zoomUrl" class="sa2-zoom-overlay" @click="zoomUrl = ''">
      <img :src="zoomUrl" class="sa2-zoom-img" @click.stop />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
// @ts-ignore
import * as THREE from 'three'
import {
  createThreeScene, attachOrbitControls, updateSphCamera,
  type SphState,
} from '../composables/usePcdRenderer'

// ─── Props & Emits ────────────────────────────────────────────
const props = withDefaults(defineProps<{
  inferMode?: number
  erodePixel?: number
  running?: boolean
}>(), {
  inferMode: 7,
  erodePixel: 205,
  running: false
})

const emit = defineEmits<{
  (e: 'update:inferMode', v: number): void
  (e: 'update:erodePixel', v: number): void
  (e: 'update:running', v: boolean): void
  (e: 'resultReady', map: Map<number, { imgStem: string; pcdStem: string }>): void
  (e: 'exportAndRun', frames: { idx: number; img_left: string | null; img_right: string | null }[]): void
}>()

// local bindings that sync to props via emit
const inferMode = ref(props.inferMode)
const erodePixel = ref(props.erodePixel)

// ─── State ───────────────────────────────────────────────────
const navPath = ref('data/single_debug/111/0327/rosbag_LK-MR6P1US000111_navigation_202603270322/')
const parsing = ref(false)
const inputDir = ref('data/single_debug/111/0327/rosbag_LK-MR6P1US000111_navigation_202603270322/bag_extract_nav/bag_extract_left/')
const modes = ref<{ value: number; label: string }[]>([])
const outputDir = ref('')
const logs = ref<string[]>([])
const extractedImages = ref<string[]>([])
const extractedPcds = ref<string[]>([])
const extractedImageDir = ref('')
const extractedPcdDir = ref('')
const resultImages = ref<string[]>([])
const selectedResultIdx = ref(-1)
const progressCurrent = ref(0)
const progressTotal = ref(0)
const progressPercent = ref(0)
const zoomUrl = ref('')
const logRef = ref<HTMLElement | null>(null)
let es: EventSource | null = null

// ─── Point Cloud State ───────────────────────────────────────
const pcdCanvasRef = ref<HTMLCanvasElement | null>(null)
const pcdStatus = ref('')
const pcdDir = ref('')

interface PcdCtx {
  renderer: THREE.WebGLRenderer
  scene: THREE.Scene
  cam: THREE.Camera
  animId: number
  points: THREE.Points | null
  sph: SphState
  orbitCleanup: () => void
}
let pcdCtx: PcdCtx | null = null

const PASSABLE_LABELS = new Set([2, 3])
function la2Color(label: number): [number, number, number] {
  const map: Record<number, [number, number, number]> = {
    0: [0, 0, 0],
    1: [0, 0, 200/255],
    2: [100/255, 255/255, 102/255],
    3: [118/255, 89/255, 0],
    4: [255/255, 255/255, 0],
    5: [255/255, 0, 0],
    6: [255/255, 165/255, 0],
    7: [255/255, 20/255, 147/255],
    8: [0, 255/255, 255/255],
    9: [245/255, 130/255, 48/255],
    10: [0, 64/255, 128/255],
    11: [34/255, 139/255, 34/255],
    12: [255/255, 192/255, 203/255],
    13: [138/255, 43/255, 226/255],
    100: [255/255, 0, 0],
    101: [255/255, 0, 0],
    102: [255/255, 0, 0],
    103: [255/255, 0, 255/255],
    104: [255/255, 0, 0],
    105: [255/255, 255/255, 0],
    106: [0, 255/255, 255/255],
    107: [0, 255/255, 0],
  }
  return map[label] || [0.5, 0.5, 0.5]
}

// ─── Helper Functions ────────────────────────────────────────
function getImageUrl(filename: string): string {
  return `/offline/extracted_image/${extractedImageDir.value}/${filename}`
}

function getResultImageUrl(filename: string): string {
  // Backend expects just the filename, it will look it up in _last_result
  return `/offline/result_image/${filename}`
}

function prevResult() {
  if (selectedResultIdx.value > 0) {
    selectedResultIdx.value--
  }
}

function nextResult() {
  if (selectedResultIdx.value < resultImages.value.length - 1) {
    selectedResultIdx.value++
  }
}

function selectExtractedImage(idx: number) {
  // When clicking on extracted image thumbnail, jump to corresponding result
  // The extracted images and result images should have the same order
  if (idx >= 0 && idx < resultImages.value.length) {
    selectedResultIdx.value = idx
  }
}

function isExtractedImageSelected(idx: number): boolean {
  // Check if this extracted image corresponds to the currently selected result
  return idx === selectedResultIdx.value
}

// ─── Point Cloud Functions ───────────────────────────────────
function initViewer(canvas: HTMLCanvasElement): PcdCtx {
  canvas.width = canvas.clientWidth || 640
  canvas.height = canvas.clientHeight || 400
  const { renderer, scene, camera } = createThreeScene(canvas, canvas.width, canvas.height)
  const sph: SphState = { theta: 0.5, phi: 0.8, radius: 3 }
  updateSphCamera(camera, sph)
  const orbitCleanup = attachOrbitControls(canvas, sph, () => updateSphCamera(camera, sph))
  const ctx: PcdCtx = { renderer, scene, cam: camera, animId: 0, points: null, sph, orbitCleanup }
  const loop = () => { ctx.animId = requestAnimationFrame(loop); renderer.render(scene, camera) }
  loop()
  return ctx
}

function parsePcd(text: string): { pos: Float32Array; col: Float32Array } {
  const lines = text.split('\n')
  let inData = false, labelCol = -1
  const pos: number[] = [], col: number[] = []
  for (const line of lines) {
    if (!inData) {
      if (line.startsWith('FIELDS')) {
        const cols = line.trim().split(/\s+/).slice(1)
        labelCol = cols.indexOf('label')
      } else if (line.startsWith('DATA')) { inData = true }
      continue
    }
    const parts = line.trim().split(/\s+/)
    if (parts.length < 4) continue
    const x = parseFloat(parts[0]), y = parseFloat(parts[1]), z = parseFloat(parts[2])
    if (!isFinite(x) || !isFinite(y) || !isFinite(z)) continue
    pos.push(x, z, -y)
    let label = 0
    if (labelCol >= 0 && labelCol < parts.length) {
      label = parseInt(parts[labelCol])
      if (!isFinite(label)) label = 0
    }
    const [r, g, b] = la2Color(label)
    const dim = PASSABLE_LABELS.has(label) ? 0.35 : 1.0
    col.push(r * dim, g * dim, b * dim)
  }
  return { pos: new Float32Array(pos), col: new Float32Array(col) }
}

function loadPcdIntoCtx(ctx: PcdCtx, text: string, statusRef: { value: string }) {
  if (ctx.points) {
    ctx.scene.remove(ctx.points)
    ctx.points.geometry.dispose()
    ;(ctx.points.material as THREE.Material).dispose()
    ctx.points = null
  }
  const { pos, col } = parsePcd(text)
  if (pos.length === 0) { statusRef.value = '无有效点'; return }
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
  const mat = new THREE.PointsMaterial({ size: 0.06, vertexColors: true, sizeAttenuation: true })
  ctx.points = new THREE.Points(geo, mat)
  ctx.scene.add(ctx.points)
  const n = pos.length / 3
  let cx = 0, cy = 0, cz = 0
  for (let i = 0; i < n; i++) { cx += pos[i*3]; cy += pos[i*3+1]; cz += pos[i*3+2] }
  updateSphCamera(ctx.cam, ctx.sph, new THREE.Vector3(cx/n, cy/n, cz/n))
  statusRef.value = `${n} pts`
}

async function loadPcdForResult(idx: number) {
  const canvas = pcdCanvasRef.value
  if (!canvas || !pcdDir.value) {
    pcdStatus.value = '无点云目录'
    return
  }

  if (!pcdCtx || pcdCtx.renderer.domElement !== canvas) {
    if (pcdCtx) {
      cancelAnimationFrame(pcdCtx.animId)
      pcdCtx.orbitCleanup()
      pcdCtx.renderer.dispose()
      pcdCtx = null
    }
    pcdCtx = initViewer(canvas)
  }

  pcdStatus.value = '加载中...'
  try {
    const imgName = resultImages.value[idx]
    const stem = imgName.replace(/\.[^.]+$/, '').replace(/_dsg$/, '')
    const pcdName = stem + '.pcd'
    const pcdPath = pcdDir.value + '/' + pcdName

    const res = await fetch(`/offline/local_file?path=${encodeURIComponent(pcdPath)}`)
    if (!res.ok) {
      pcdStatus.value = '❌ 点云文件不存在'
      return
    }
    const text = await res.text()
    loadPcdIntoCtx(pcdCtx, text, pcdStatus)
  } catch (e) {
    pcdStatus.value = `❌ ${e}`
  }
}

// Watch for result selection changes to load corresponding point cloud
watch(selectedResultIdx, async (idx) => {
  if (idx >= 0) {
    await nextTick()
    await loadPcdForResult(idx)
  }
})

function onImageError(e: Event) {
  const img = e.target as HTMLImageElement
  console.error('Failed to load image:', img.src)
  img.style.border = '2px solid red'
}

// ─── SSE ─────────────────────────────────────────────────────
function connectSSE() {
  if (es) es.close()
  es = new EventSource('/offline/events')
  es.onmessage = (e) => { handleMsg(JSON.parse(e.data)) }
}

function handleMsg(msg: any) {
  if (msg.type === 'start') {
    emit('update:running', true)
    outputDir.value = msg.output_dir
    logs.value = [
      `[开始] 输入: ${msg.input_dir}`,
      `[模式] ${msg.infer_mode}`,
      `[输出] ${msg.output_dir}`,
    ]
    resultImages.value = []
    selectedResultIdx.value = -1
    progressCurrent.value = 0
    progressTotal.value = 0
    progressPercent.value = 0
  } else if (msg.type === 'log') {
    logs.value.push(msg.text)
    nextTick(() => { if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight })

    // Parse progress from log messages
    const progressMatch = msg.text.match(/\[Image (\d+)\/(\d+)\]/)
    if (progressMatch) {
      progressCurrent.value = parseInt(progressMatch[1])
      progressTotal.value = parseInt(progressMatch[2])
      progressPercent.value = Math.round((progressCurrent.value / progressTotal.value) * 100)
    }
  } else if (msg.type === 'done') {
    emit('update:running', false)
    logs.value.push(`[完成] 退出码: ${msg.exit_code}`)
    progressPercent.value = 100

    // Load result images
    if (msg.images && msg.images.length > 0) {
      resultImages.value = msg.images
      selectedResultIdx.value = 0  // Auto-select first image

      // Set point cloud directory when processing completes
      if (inputDir.value) {
        const basePath = inputDir.value.replace(/bag_extract_left\/?$/, '')
        pcdDir.value = basePath + 'bag_extract_pcd'
        console.log('[SSE done] pcdDir set to:', pcdDir.value)
      }
    }

    if (msg.is_export_run && (msg.images?.length || msg.pcds?.length)) {
      const newMap = new Map<number, { imgStem: string; pcdStem: string }>()
      for (const imgName of (msg.images ?? [])) {
        const m = imgName.match(/frame_(\d+)/)
        if (m) {
          const idx = parseInt(m[1])
          const imgStem = imgName.replace(/\.[^.]+$/, '')
          const pcdName = (msg.pcds ?? []).find((p: string) => p.includes(`frame_${m[1]}`)) ?? ''
          const pcdStem = pcdName ? pcdName.replace(/\.[^.]+$/, '') : ''
          newMap.set(idx, { imgStem, pcdStem })
        }
      }
      emit('resultReady', newMap)
    }
  } else if (msg.type === 'error') {
    emit('update:running', false)
    logs.value.push(`[错误] ${msg.text}`)
  }
}

function logClass(line: string) {
  if (line.startsWith('[错误]') || line.includes('Error') || line.includes('error')) return 'log-err'
  if (line.startsWith('[完成]') || line.includes('✓') || line.includes('completed')) return 'log-ok'
  if (line.startsWith('[开始]') || line.startsWith('[模式]') || line.startsWith('[输出]')) return 'log-info'
  return ''
}

async function loadModes() {
  try {
    const res = await fetch('/offline/modes')
    if (!res.ok) return
    modes.value = (await res.json()).modes ?? []
  } catch { /* server not ready */ }
}

async function checkExistingResult() {
  if (!inputDir.value || props.running) return

  try {
    const checkRes = await fetch('/offline/check_result', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        input_dir: inputDir.value,
        infer_mode: inferMode.value,
        erode_pixel: erodePixel.value,
      }),
    })
    const checkData = await checkRes.json()

    if (checkData.ok && checkData.exists) {
      logs.value = []
      logs.value.push(`[发现] 已存在处理结果: ${checkData.image_count} 张图片`)
      logs.value.push(`[输出] ${checkData.output_dir}`)
      outputDir.value = checkData.output_dir
      resultImages.value = checkData.images || []
      selectedResultIdx.value = resultImages.value.length > 0 ? 0 : -1

      // Set point cloud directory based on input directory
      // Extract the base path and append bag_extract_pcd
      const basePath = inputDir.value.replace(/bag_extract_left\/?$/, '')
      pcdDir.value = basePath + 'bag_extract_pcd'
      console.log('[checkExistingResult] pcdDir set to:', pcdDir.value)

      // Set progress to 100%
      progressCurrent.value = checkData.image_count
      progressTotal.value = checkData.image_count
      progressPercent.value = 100
    } else {
      // Clear results if no existing result found
      if (logs.value.some(l => l.includes('[发现]'))) {
        logs.value = []
        resultImages.value = []
        selectedResultIdx.value = -1
        outputDir.value = ''
        progressPercent.value = 0
      }
    }
  } catch (err) {
    console.error('Failed to check existing result:', err)
  }
}

async function startTest() {
  if (!inputDir.value) return
  logs.value = []

  logs.value.push(`[调试] 使用路径: ${inputDir.value}`)

  // First check if result already exists
  try {
    const checkRes = await fetch('/offline/check_result', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        input_dir: inputDir.value,
        infer_mode: inferMode.value,
        erode_pixel: erodePixel.value,
      }),
    })
    const checkData = await checkRes.json()

    if (checkData.ok && checkData.exists) {
      logs.value.push(`[发现] 已存在处理结果: ${checkData.image_count} 张图片`)
      logs.value.push(`[输出] ${checkData.output_dir}`)
      outputDir.value = checkData.output_dir
      resultImages.value = checkData.images || []
      selectedResultIdx.value = resultImages.value.length > 0 ? 0 : -1

      // Set point cloud directory
      const basePath = inputDir.value.replace(/bag_extract_left\/?$/, '')
      pcdDir.value = basePath + 'bag_extract_pcd'
      console.log('[startTest] pcdDir set to:', pcdDir.value)

      // Set progress to 100%
      progressCurrent.value = checkData.image_count
      progressTotal.value = checkData.image_count
      progressPercent.value = 100

      return
    }
  } catch (err) {
    console.error('Failed to check existing result:', err)
  }

  // No existing result, run the test
  const res = await fetch('/offline/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      input_dir: inputDir.value,
      infer_mode: inferMode.value,
      erode_pixel: erodePixel.value,
    }),
  })
  const data = await res.json()
  if (!data.ok) logs.value.push(`[错误] ${data.error}`)
}

async function stopTest() {
  await fetch('/offline/stop', { method: 'POST' })
}

async function parseNavBag() {
  if (!navPath.value) return
  parsing.value = true
  logs.value = []
  logs.value.push(`[解析] 开始解析nav包: ${navPath.value}`)
  try {
    const res = await fetch('/offline/parse_nav_bag', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nav_path: navPath.value }),
    })

    if (!res.ok) {
      const text = await res.text()
      logs.value.push(`[错误] HTTP ${res.status}: ${text || res.statusText}`)
      return
    }

    const text = await res.text()
    if (!text) {
      logs.value.push(`[错误] 服务器返回空响应`)
      return
    }

    const data = JSON.parse(text)
    if (data.ok) {
      logs.value.push(`[完成] 解析图片成功: ${data.image_count} 张`)
      logs.value.push(`[完成] 解析点云成功: ${data.pcd_count} 个`)
      logs.value.push(`[输出] 图片目录: ${data.image_dir}`)
      logs.value.push(`[输出] 点云目录: ${data.pcd_dir}`)
      inputDir.value = data.image_dir || ''
      extractedImageDir.value = data.image_dir || ''
      extractedPcdDir.value = data.pcd_dir || ''
      extractedImages.value = data.images || []
      extractedPcds.value = data.pcds || []
    } else {
      logs.value.push(`[错误] ${data.error || '未知错误'}`)
    }
  } catch (err) {
    logs.value.push(`[错误] 解析失败: ${err}`)
  } finally {
    parsing.value = false
  }
}

// Exposed so parent can call exportAndRun
export type { }
defineExpose({ logs, outputDir })

onMounted(() => {
  connectSSE()
  loadModes()
})

onBeforeUnmount(() => {
  es?.close()
  if (pcdCtx) {
    cancelAnimationFrame(pcdCtx.animId)
    pcdCtx.orbitCleanup()
    pcdCtx.renderer.dispose()
    pcdCtx = null
  }
})
</script>

<style scoped>
.sa2-root { display:flex; flex-direction:column; height:100%; background:#1a1a2e; color:#e0e0e0; font-size:13px; overflow:hidden; }
.sa2-input-bar { background:#0d1117; border-bottom:1px solid #1e2a3a; padding:6px 14px; display:flex; align-items:center; gap:8px; flex-wrap:wrap; flex-shrink:0; }
.sa2-input-bar label { font-size:11px; color:#888; white-space:nowrap; }
.sa2-path-input { flex:1; min-width:260px; background:#1a1a2e; border:1px solid #333; border-radius:4px; padding:4px 8px; color:#e0e0e0; font-size:11px; font-family:monospace; }
.sa2-path-input:focus { outline:none; border-color:#4fc3f7; }
.sa2-label-input { width:80px; background:#1a1a2e; border:1px solid #333; border-radius:4px; padding:4px 6px; color:#e0e0e0; font-size:11px; }
.sa2-sep { color:#444; margin:0 2px; }
.sa2-scan-btn { padding:4px 12px; background:#1b5e20; border:1px solid #388e3c; border-radius:4px; color:#a5d6a7; font-size:11px; cursor:pointer; white-space:nowrap; }
.sa2-scan-btn:hover:not(:disabled) { background:#2e7d32; }
.sa2-scan-btn:disabled { opacity:.5; cursor:not-allowed; }
.sa2-arch-btn { padding:4px 12px; background:#1a237e; border:1px solid #3949ab; border-radius:4px; color:#9fa8da; font-size:11px; cursor:pointer; white-space:nowrap; }
.sa2-arch-btn:hover:not(:disabled) { background:#283593; }
.sa2-arch-btn:disabled { opacity:.5; cursor:not-allowed; }
.sa2-dbg-btn { padding:4px 12px; background:#4a148c; border:1px solid #7b1fa2; border-radius:4px; color:#ce93d8; font-size:11px; cursor:pointer; white-space:nowrap; }
.sa2-dbg-btn:hover:not(:disabled) { background:#6a1b9a; }
.sa2-dbg-btn:disabled { opacity:.5; cursor:not-allowed; }
.sa2-status { font-size:11px; color:#69f0ae; font-family:monospace; }
.sa2-progress-container { width:180px; height:18px; background:#222; border-radius:9px; position:relative; overflow:hidden; border:1px solid #444; margin-left:8px; }
.sa2-progress-bar { height:100%; background:linear-gradient(90deg, #4f46e5, #9333ea); transition:width 0.3s ease; }
.sa2-progress-text { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-size:9px; color:#fff; text-shadow:0 0 2px #000; font-weight:bold; pointer-events:none; }
.sa2-legend { display:flex; align-items:center; gap:10px; flex-wrap:wrap; font-size:11px; padding:4px 14px; background:#12192a; border-bottom:1px solid #1e2a3a; flex-shrink:0; }
.sa2-li { display:flex; align-items:center; gap:4px; }
.sa2-nav-info { font-size:11px; color:#90caf9; font-family:monospace; }
.sa2-preview-section { background:#080c14; border-bottom:1px solid #1e2a3a; padding:8px 14px; flex-shrink:0; }
.sa2-preview-group { margin-bottom:8px; }
.sa2-preview-group:last-child { margin-bottom:0; }
.sa2-panel-label { font-size:10px; color:#4fc3f7; padding:2px 4px; flex-shrink:0; margin-bottom:4px; }
.sa2-result-info { font-size:10px; color:#888; margin-left:6px; }
.sa2-thumb-strip { display:flex; gap:4px; overflow-x:auto; overflow-y:hidden; background:#080c14; flex-shrink:0; align-items:center; padding:2px 0; }
.sa2-thumb-item { flex-shrink:0; width:76px; border:2px solid #333; border-radius:3px; overflow:hidden; cursor:pointer; transition:border-color .2s; }
.sa2-thumb-item:hover { border-color:#90caf9; }
.sa2-thumb-item.active { border-color:#4fc3f7; box-shadow:0 0 8px rgba(79, 195, 247, 0.5); }
.sa2-thumb-item img { width:100%; height:46px; object-fit:cover; display:block; background:#222; }
.sa2-thumb-name { font-size:9px; color:#555; text-align:center; padding:1px 0; background:#0a0e15; }
.sa2-log-section { background:#0d0d1a; border-bottom:1px solid #1e2a3a; padding:8px 14px; flex-shrink:0; max-height:300px; display:flex; flex-direction:column; }
.sa2-log { flex:1; overflow-y:auto; background:#0d0d1a; border-radius:4px; padding:6px 8px; font-family:monospace; font-size:11px; min-height:200px; }
.log-line { line-height:1.5; color:#c9d1d9; }
.log-line.log-err { color:#f87171; }
.log-line.log-ok { color:#4ade80; }
.log-line.log-info { color:#60a5fa; }
.log-empty { color:#555; font-size:11px; }
.sa2-result-section { flex:1; display:flex; flex-direction:column; padding:8px 14px; min-height:0; overflow:hidden; }
.sa2-result-nav { display:flex; gap:8px; margin-bottom:8px; }
.sa2-result-nav button { padding:6px 16px; background:#1e3a5f; color:#fff; border:1px solid #2563eb; border-radius:4px; cursor:pointer; font-size:13px; transition:all .2s; }
.sa2-result-nav button:hover:not(:disabled) { background:#2563eb; }
.sa2-result-nav button:disabled { opacity:0.4; cursor:not-allowed; }
.sa2-result-layout-split { flex:1; display:flex; gap:12px; min-height:0; }
.sa2-result-left-panel { flex:1; display:flex; flex-direction:column; min-width:0; }
.sa2-result-right-panel { flex:1; display:flex; flex-direction:column; min-width:0; }
.sa2-panel-sublabel { font-size:10px; color:#4fc3f7; padding:2px 4px; margin-bottom:6px; }
.sa2-result-left-panel > img, .sa2-result-left-panel > .sa2-placeholder { flex:1; display:flex; align-items:center; justify-content:center; background:#050810; border-radius:4px; }
.sa2-pcd-canvas { width:100%; flex:1; background:#050810; border-radius:4px; cursor:grab; }
.sa2-pcd-canvas:active { cursor:grabbing; }
.sa2-pcd-status { font-size:9px; color:#888; margin-left:6px; }
.sa2-result-detail-full { flex:1; display:flex; align-items:center; justify-content:center; overflow:auto; background:#050810; border-radius:4px; min-height:400px; }
.sa2-result-img { max-width:100%; max-height:100%; object-fit:contain; cursor:zoom-in; }
.sa2-placeholder { color:#444; font-size:13px; }
.sa2-empty { flex:1; display:flex; align-items:center; justify-content:center; color:#444; font-size:14px; }
.sa2-zoom-overlay { position:fixed; inset:0; background:rgba(0,0,0,.93); z-index:9999; display:flex; align-items:center; justify-content:center; cursor:zoom-out; }
.sa2-zoom-img { max-width:92vw; max-height:92vh; object-fit:contain; border:2px solid #4fc3f7; border-radius:4px; cursor:default; }
</style>
