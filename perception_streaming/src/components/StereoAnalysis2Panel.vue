<template>
  <div class="sa2-root">
    <div class="sa2-input-bar">
      <label>SN末尾4位:</label>
      <input v-model="snLast4" class="sa2-sn-input" placeholder="0015" maxlength="4" @input="onSnInput" />
      <label>📁 夜晚双目文件目录:</label>
      <input v-model="folderPath" class="sa2-path-input" placeholder="含 images/ pointclouds/ 子目录的文件夹路径" @keyup.enter="doScanNight" />
      <button class="sa2-dbg-btn" style="background:#4c1d95;margin-right:8px" :disabled="offlineRunning || !folderPath.trim() || pairs.length === 0" @click="() => { console.log('[Button Click] Night Debug clicked'); runNightOfflineDebug(); }">{{ offlineRunning ? '⏳ 运行中...' : '🌙 夜间离线debug' }}</button>
      <label>📁 白天双目文件目录:</label>
      <input v-model="dayFolderPath" class="sa2-path-input" placeholder="data/stereo_debug/0016/20260420" @keyup.enter="doScanDay" />
      <button class="sa2-dbg-btn" style="background:#fb923c;color:#000;margin-right:8px" :disabled="offlineRunning || !dayFolderPath.trim()" @click="runDayOfflineDebug">{{ offlineRunning ? '⏳ 运行中...' : '☀️ 白天离线debug' }}</button>
      <label>标签:</label>
      <input v-model.number="filterLabel" type="number" class="sa2-label-input" />
      <button class="sa2-scan-btn" :disabled="scanning || !folderPath" @click="() => doScan()">{{ scanning ? '⏳ 扫描中...' : '🔍 扫描障碍帧' }}</button>
      <span v-if="scanStatus" class="sa2-status" :class="{ error: scanError }">{{ scanStatus }}</span>
      <span class="sa2-sep">|</span>
      <label>归档目录:</label>
      <input v-model="archiveDir" class="sa2-path-input-sm" placeholder="归档输出目录（默认 select/）" />
      <button class="sa2-arch-btn" :disabled="selectedIdx < 0 || !archiveDir" @click="archiveFrame">📦 障碍物归档</button>
      <span v-if="archiveStatus" class="sa2-arch-status" :class="{ error: archiveError }">{{ archiveStatus }}</span>
      <span class="sa2-sep">|</span>
      <button class="sa2-dbg-btn" style="background:#065f46;margin-left:4px" :disabled="offlineRunning || !folderPath" @click="resumeOfflineDebug">{{ offlineRunning ? '⏳ 运行中...' : '▶ 继续执行' }}</button>
      <div v-if="offlineRunning && pairs.length > 0" class="sa2-progress-container">
        <div class="sa2-progress-bar" :style="{ width: progressPercent + '%' }"></div>
        <span class="sa2-progress-text">{{ progressPercent }}% ({{ progressCurrent }}/{{ progressTotal }})</span>
      </div>
      <div v-else-if="offlineRunning && pairs.length === 0" class="sa2-progress-container">
        <div class="sa2-progress-bar" style="width: 100%; animation: pulse 1.5s ease-in-out infinite;"></div>
        <span class="sa2-progress-text">等待扫描数据...</span>
      </div>
      <span v-else-if="offlineStatus" class="sa2-dbg-status" :class="{ error: offlineError }">{{ offlineStatus }}</span>
      <span class="sa2-sep">|</span>
      <label>端口:</label>
      <input v-model.number="uploadPort" type="number" class="sa2-port-input" placeholder="10123" />
      <label>开始:</label>
      <input v-model="uploadDateStart" class="sa2-date-input" placeholder="20260321" maxlength="8" />
      <label>截止:</label>
      <input v-model="uploadDateEnd" class="sa2-date-input" placeholder="20260331" maxlength="8" />
      <button class="sa2-upload-btn" :disabled="uploadRunning || !uploadDateStart || !uploadDateEnd || !uploadPort" @click="doUploadImages">{{ uploadRunning ? '⏳ 上传中...' : '📤 上传图片' }}</button>
      <span v-if="uploadStatus" class="sa2-upload-status" :class="{ error: uploadError }">{{ uploadStatus }}</span>
    </div>
    <div v-if="pairs.length" class="sa2-legend">
      <span class="sa2-li"><span class="sa2-dot" style="background:#6464ff"></span>bg</span>
      <span class="sa2-li"><span class="sa2-dot" style="background:#64ff64"></span>grass</span>
      <span class="sa2-li"><span class="sa2-dot" style="background:#765900"></span>road</span>
      <span class="sa2-li"><span class="sa2-dot" style="background:#ffff00"></span>dynamic</span>
      <span class="sa2-li"><span class="sa2-dot" style="background:#ff0000"></span>static_obstacle</span>
      <span class="sa2-li"><span class="sa2-dot" style="background:#ffa500"></span>wall</span>
      <span class="sa2-nav-info" v-if="selectedIdx >= 0">{{ selectedIdx + 1 }} / {{ pairs.length }}</span>
      <button class="sa2-nav-btn" :disabled="selectedIdx <= 0" @click="selectPair(selectedIdx - 1)">◀</button>
      <button class="sa2-nav-btn" :disabled="selectedIdx >= pairs.length - 1" @click="selectPair(selectedIdx + 1)">▶</button>
    </div>
    <div v-if="pairs.length" class="sa2-body">
      <div class="sa2-top">
        <div class="sa2-thumb-strip">
          <div v-for="(pair, i) in pairs" :key="pair.pcd" class="sa2-thumb-item" :class="{ active: selectedIdx === i }" @click="selectPair(i)">
            <img v-if="pair.img" :src="imgUrl(pair.img)" loading="lazy" @error="(e) => onThumbError(e, i)" />
            <div v-else class="sa2-thumb-noimag">无图</div>
            <div class="sa2-thumb-name">第{{ i + 1 }}/{{ pairs.length }}张</div>
          </div>
        </div>
        <div class="sa2-main">
          <div class="sa2-left">
            <div class="sa2-panel-label">双目图像</div>
            <div v-if="selectedIdx < 0" class="sa2-placeholder">点击缩略图选择帧</div>
            <img v-else-if="pairs[selectedIdx].img" :src="imgUrl(pairs[selectedIdx].img!)" class="sa2-stereo-img" @click="zoomUrl = imgUrl(pairs[selectedIdx].img!)" />
            <div v-else class="sa2-placeholder">无对应图片</div>
            <div class="sa2-frame-info" v-if="selectedIdx >= 0">第{{ selectedIdx + 1 }}/{{ pairs.length }}张 | {{ pairs[selectedIdx].pcd }}</div>
          </div>
          <div class="sa2-right">
            <div class="sa2-panel-label">处理结果图 <span class="sa2-result-dir">{{ resultDirLabel }}</span></div>
            <div v-if="selectedIdx < 0" class="sa2-placeholder">点击缩略图选择帧</div>
            <img v-else-if="linkedResultImg" :src="linkedResultImg" class="sa2-stereo-img" @dblclick="zoomUrl = linkedResultImg" />
            <div v-else class="sa2-placeholder">无对应结果图</div>
          </div>
        </div>
      </div>
      <div class="sa2-bottom">
        <div class="sa2-result-left">
          <div class="sa2-panel-label">原始点云 <span class="sa2-pcd-status">{{ pcdStatus }}</span></div>
          <div v-if="selectedIdx < 0" class="sa2-placeholder">点击缩略图选择帧</div>
          <canvas v-else ref="pcdCanvasRef" class="sa2-pcd-canvas" />
        </div>
        <div class="sa2-result-right">
          <div class="sa2-panel-label">结果点云 <span class="sa2-pcd-status">{{ resultPcdStatus }}</span></div>
          <div v-if="selectedIdx < 0" class="sa2-placeholder">点击缩略图选择帧</div>
          <div v-else-if="!resultPcdDir" class="sa2-placeholder">暂无结果点云目录</div>
          <canvas v-else ref="resultPcdCanvasRef" class="sa2-pcd-canvas" />
        </div>
      </div>
    </div>
    <div v-else-if="!scanning" class="sa2-empty">{{ folderPath ? '未找到含障碍物的点云帧' : '请输入文件夹路径并点击扫描' }}</div>
    <div v-if="zoomUrl" class="sa2-zoom-overlay" @click="zoomUrl = ''">
      <img :src="zoomUrl" class="sa2-zoom-img" @click.stop />
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref, watch, onBeforeUnmount, nextTick, computed, onMounted } from 'vue'
// @ts-ignore
import * as THREE from 'three'
import {
  createThreeScene, attachOrbitControls, updateSphCamera,
  type SphState,
} from '../composables/usePcdRenderer'

const folderPath = ref('data/stereo_debug/0115/20260421')
const dayFolderPath = ref('data/stereo_debug/0016/20260420')
const snLast4 = ref('0115')
const filterLabel = ref(0)
const scanning = ref(false)
const scanStatus = ref('')
const scanError = ref(false)
const archiveDir = ref('')
watch(folderPath, (p) => { if (p) archiveDir.value = p.replace(/\/+$/, '') + '/select' })
const archiveStatus = ref('')
const archiveError = ref(false)
const offlineRunning = ref(false)
const offlineStatus = ref('')
const offlineError = ref(false)
const progressCurrent = ref(0)
const progressTotal = ref(0)
const progressPercent = computed(() => progressTotal.value > 0 ? Math.round((progressCurrent.value / progressTotal.value) * 100) : 0)

const uploadPort = ref<number>(10115)
const today = new Date().toISOString().slice(0, 10).replace(/-/g, '')
const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10).replace(/-/g, '')
const uploadDateStart = ref(threeDaysAgo)
const uploadDateEnd = ref(today)
const uploadRunning = ref(false)
const uploadStatus = ref('')
const uploadError = ref(false)

// 当输入SN末尾4位时，自动拼接路径和端口号
function onSnInput() {
  const sn = snLast4.value.trim()
  if (sn.length === 4 && /^\d{4}$/.test(sn)) {
    const today = new Date().toISOString().slice(0, 10).replace(/-/g, '')
    folderPath.value = `data/stereo_debug/${sn}/${today}`
    uploadPort.value = parseInt('1' + sn)
  }
}

interface Pair { pcd: string; img: string | null }
const pairs = ref<Pair[]>([])
const imagesDir = ref('')
const pcdsDir = ref('')
const selectedIdx = ref(-1)
const pcdStatus = ref('')
const zoomUrl = ref('')

const resultImages = ref<string[]>([])
const resultPcds = ref<string[]>([])
const resultDir = ref('')
const resultPcdDir = ref('')
const resultSelectedIdx = ref(-1)
const resultPcdStatus = ref('')
const resultDirLabel = ref('')
const lastOfflineInferMode = ref(99)
let offlineEventSource: EventSource | null = null
let offlineReconnectTimer: ReturnType<typeof setTimeout> | null = null
let offlineStatusPollTimer: ReturnType<typeof setInterval> | null = null
let offlineRunToken = 0

async function readJsonResponse<T>(res: Response, action: string): Promise<T> {
  const text = await res.text()
  if (!text.trim()) {
    throw new Error(`${action}返回空响应 (HTTP ${res.status})`)
  }
  try {
    return JSON.parse(text) as T
  } catch (error) {
    throw new Error(`${action}返回非 JSON 响应 (HTTP ${res.status}): ${error}`)
  }
}

// Load default port from server config on mount
onMounted(async () => {
  try {
    const res = await fetch('/offline/config')
    const data = await readJsonResponse<any>(res, '加载配置')
    if (data.ok && data.default_ports?.stereo_analysis) {
      uploadPort.value = data.default_ports.stereo_analysis
    }
  } catch (e) {
    console.warn('Failed to load config:', e)
  }
})

function resetResultState() {
  resultImages.value = []
  resultPcds.value = []
  resultDir.value = ''
  resultPcdDir.value = ''
  resultSelectedIdx.value = -1
  resultDirLabel.value = ''
  resultPcdStatus.value = ''
}

function expectedResultDir(mode: number, inputDir: string) {
  const base = inputDir.replace(/\/+$/, '')
  if (mode === 6) return `${base}/sub_6_205_432`
  if (mode === 99) return `${base}/dsg_7_205_432`
  if (mode === 7) return `${base}/dsg_7_205_432`
  return `${base}/output_${mode}_205`
}

function expectedResultPcdDir(mode: number, inputDir: string) {
  const base = inputDir.replace(/\/+$/, '')
  if (mode === 6) return `${base}/pcd_6_205_432`
  if (mode === 99 || mode === 7) return `${base}/pcd_7_205_432`
  return `${base}/pcd_${mode}_205_432`
}

function applyInferredResultDirs(mode: number, inputDir: string) {
  resultDir.value = expectedResultDir(mode, inputDir)
  resultPcdDir.value = expectedResultPcdDir(mode, inputDir)
  resultDirLabel.value = resultDir.value.split('/').pop() || ''
  console.log('[doScan] Inferred resultDir:', resultDir.value)
  console.log('[doScan] Inferred resultPcdDir:', resultPcdDir.value)
}

function baseName(path: string) {
  return path.split('/').pop() || path
}

function stemName(path: string) {
  return baseName(path).replace(/\.[^.]+$/, '')
}

function clearOfflineReconnectTimer() {
  if (offlineReconnectTimer) {
    clearTimeout(offlineReconnectTimer)
    offlineReconnectTimer = null
  }
}

function clearOfflineStatusPollTimer() {
  if (offlineStatusPollTimer) {
    clearInterval(offlineStatusPollTimer)
    offlineStatusPollTimer = null
  }
}

function closeOfflineEventStream() {
  if (offlineEventSource) {
    offlineEventSource.close()
    offlineEventSource = null
  }
}

function applyOfflineCompletion(payload: {
  output_dir?: string
  pcd_dir?: string
  images?: string[]
  pcds?: string[]
  image_count?: number
  pcd_count?: number
}) {
  closeOfflineEventStream()
  clearOfflineReconnectTimer()
  clearOfflineStatusPollTimer()
  offlineRunning.value = false
  progressCurrent.value = progressTotal.value || pairs.value.length

  const images = payload.images || []
  const pcds = payload.pcds || []
  if (images.length > 0 && payload.output_dir) {
    resultDir.value = payload.output_dir
    resultImages.value = images
    resultDirLabel.value = payload.output_dir.split('/').pop() || ''
    resultPcdDir.value = payload.pcd_dir || ''
    resultPcds.value = pcds
    offlineStatus.value = `✓ 完成 ${payload.image_count ?? images.length}/${pairs.value.length} (点云: ${payload.pcd_count ?? pcds.length})`
    nextTick().then(() => {
      if (resultPcdCanvasRef.value && !resultPcdCtx)
        resultPcdCtx = initViewer(resultPcdCanvasRef.value)
      if (pairs.value.length > 0) {
        selectPair(pairs.value.length - 1)
      }
    })
  } else {
    offlineStatus.value = '完成 (无输出图片)'
  }
}

function applyOfflineFailure(message: string) {
  closeOfflineEventStream()
  clearOfflineReconnectTimer()
  clearOfflineStatusPollTimer()
  offlineRunning.value = false
  offlineStatus.value = `✗ ${message}`
  offlineError.value = true
}

function syncProgressFromStatus(progress?: {
  current?: number
  total?: number
  status?: string
  last_log?: string
}) {
  if (!progress) return
  if (typeof progress.total === 'number' && progress.total > 0) {
    progressTotal.value = progress.total
  }
  if (typeof progress.current === 'number' && progress.current >= 0) {
    progressCurrent.value = progress.current
  }
  if (typeof progress.status === 'string' && progress.status) {
    offlineStatus.value = progress.status
  } else if (typeof progress.last_log === 'string' && progress.last_log) {
    offlineStatus.value = progress.last_log
  }
}

function scheduleOfflineEventReconnect(runToken: number, inputDir: string, delayMs = 1000) {
  clearOfflineReconnectTimer()
  if (runToken !== offlineRunToken || !offlineRunning.value) return
  offlineReconnectTimer = setTimeout(() => {
    if (runToken !== offlineRunToken || !offlineRunning.value) return
    connectOfflineEventStream(runToken, inputDir)
  }, delayMs)
}

async function reconcileOfflineRunState(runToken: number, inputDir: string) {
  if (runToken !== offlineRunToken) return
  try {
    const res = await fetch('/offline/status')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await readJsonResponse<any>(res, '查询离线状态')
    if (runToken !== offlineRunToken) return
    syncProgressFromStatus(data.progress)

    if (data.running) {
      offlineRunning.value = true
      offlineError.value = false
      if (!offlineStatus.value) {
        offlineStatus.value = progressCurrent.value > 0
          ? `正在运行第 ${progressCurrent.value}/${progressTotal.value || pairs.value.length} 张`
          : '连接重试中...'
      }
      scheduleOfflineEventReconnect(runToken, inputDir, 600)
      return
    }

    const result = data.result || {}
    const resultImages = Array.isArray(result.images) ? result.images : []
    const resultPcds = Array.isArray(result.pcds) ? result.pcds : []
    if (result.output_dir || resultImages.length > 0 || resultPcds.length > 0) {
      applyOfflineCompletion({
        output_dir: result.output_dir,
        pcd_dir: result.pcd_dir,
        images: resultImages,
        pcds: resultPcds,
        image_count: resultImages.length,
        pcd_count: resultPcds.length,
      })
      return
    }

    offlineRunning.value = false
    offlineStatus.value = '运行已结束'
  } catch (error) {
    if (runToken !== offlineRunToken) return
    offlineRunning.value = true
    offlineError.value = false
    offlineStatus.value = '连接重试中...'
    scheduleOfflineEventReconnect(runToken, inputDir, 1200)
  }
}

function startOfflineStatusPolling(runToken: number, inputDir: string) {
  clearOfflineStatusPollTimer()
  offlineStatusPollTimer = setInterval(() => {
    if (runToken !== offlineRunToken || !offlineRunning.value) {
      clearOfflineStatusPollTimer()
      return
    }
    void reconcileOfflineRunState(runToken, inputDir)
  }, 1000)
}

function connectOfflineEventStream(runToken: number, inputDir: string) {
  if (runToken !== offlineRunToken || !offlineRunning.value) return
  closeOfflineEventStream()

  const evtSrc = new EventSource('/offline/events')
  offlineEventSource = evtSrc

  evtSrc.onmessage = async (e) => {
    if (runToken !== offlineRunToken || evtSrc !== offlineEventSource) return
    const msg = JSON.parse(e.data)
    if (msg.type === 'log') {
      console.log('[OfflineLog]', msg.text)
      const matchProgress = msg.text.match(/\((\d+)\/(\d+)\)/)
      const matchSeq = msg.text.match(/sequence_num:\s*(\d+)/)
      const matchSkip = msg.text.match(/Skip existing file:\s*(.+)/)
      const matchSkipNight = msg.text.match(/Skip\s+(.+)\s+as it already exists/)
      const matchProcessing = msg.text.match(/Processing\s+\d+\/\d+:\s+(.+)/)
      const matchAnyProgress = msg.text.match(/(\d+)\s*\/\s*(\d+)/)

      if (matchProgress) {
        progressCurrent.value = parseInt(matchProgress[1])
        progressTotal.value = parseInt(matchProgress[2])
        offlineStatus.value = `正在运行第 ${progressCurrent.value}/${progressTotal.value} 张`
      } else if (matchSeq) {
        progressCurrent.value = parseInt(matchSeq[1]) + 1
        offlineStatus.value = `正在运行第 ${progressCurrent.value}/${pairs.value.length} 张`
      } else if (matchSkip || matchSkipNight) {
        if (progressCurrent.value < progressTotal.value) progressCurrent.value++
        const skippedFile = matchSkip ? matchSkip[1] : matchSkipNight[1]
        offlineStatus.value = `跳过已存在: ${skippedFile.split('/').pop()}`
      } else if (matchProcessing) {
        const parts = msg.text.match(/Processing\s+(\d+)\/(\d+)/)
        if (parts) {
          progressCurrent.value = parseInt(parts[1])
          progressTotal.value = parseInt(parts[2])
        }
        offlineStatus.value = `正在处理: ${matchProcessing[1].split('/').pop()}`
      } else if (matchAnyProgress) {
        progressCurrent.value = parseInt(matchAnyProgress[1])
        progressTotal.value = parseInt(matchAnyProgress[2])
        offlineStatus.value = `运行中 ${progressCurrent.value}/${progressTotal.value}`
      } else {
        offlineStatus.value = msg.text.length > 30 ? msg.text.slice(-30) : msg.text
      }
    } else if (msg.type === 'done') {
      applyOfflineCompletion(msg)
    } else if (msg.type === 'error') {
      applyOfflineFailure(msg.text)
    } else if (msg.type === 'hello') {
      syncProgressFromStatus(msg.progress)
    }
  }

  evtSrc.onerror = () => {
    if (runToken !== offlineRunToken || evtSrc !== offlineEventSource) return
    closeOfflineEventStream()
    reconcileOfflineRunState(runToken, inputDir)
  }
}

const linkedResultImg = computed(() => {
  if (selectedIdx.value < 0 || !pairs.value[selectedIdx.value] || !resultDir.value) return ''
  const stem = stemName(pairs.value[selectedIdx.value].pcd).toLowerCase()

  const match = resultImages.value.find((img) => {
    const candidate = stemName(img).toLowerCase()
    return candidate === stem || candidate.startsWith(stem + '_') || candidate.includes(stem + '_')
  })

  return match ? resultImgUrl(match) : ''
})

async function doScan(preferMode?: number) {
  if (!folderPath.value || scanning.value) return
  scanning.value = true
  scanStatus.value = ''
  scanError.value = false
  pairs.value = []
  selectedIdx.value = -1
  resetResultState()
  try {
    const url = `/offline/scan_nav_folder?folder=${encodeURIComponent(folderPath.value)}&filter_label=${filterLabel.value}`
    const res = await fetch(url)
    const data = await readJsonResponse<any>(res, '扫描双目目录')
    if (!data.ok) { scanStatus.value = data.error || '扫描失败'; scanError.value = true; return }
    imagesDir.value = data.images_dir || ''
    pcdsDir.value = data.pcds_dir || ''
    if (data.filtered) {
      pairs.value = (data.pairs as Pair[]) || []
      scanStatus.value = `找到 ${pairs.value.length} 帧含 label=${filterLabel.value} 障碍物点云`
    } else {
      const imgs: string[] = data.images || []
      const pcds: string[] = data.pcds || []
      if (pcds.length > 0) {
        const imgMap = new Map(imgs.map(f => [f.replace(/\.[^.]+$/, ''), f]))
        pairs.value = pcds.map(pcd => ({ pcd, img: imgMap.get(pcd.replace(/\.[^.]+$/, '')) ?? null }))
        scanStatus.value = `共 ${pairs.value.length} 帧`
      } else if (imgs.length > 0) {
        // 没有点云，只有图片时，创建只有图片的 pairs
        pairs.value = imgs.map(img => ({ pcd: img.replace(/\.[^.]+$/, '') + '.pcd', img }))
        scanStatus.value = `共 ${pairs.value.length} 张图片（无点云）`
      } else {
        scanStatus.value = '未找到图片或点云'; scanError.value = true
      }
    }
    if (pairs.value.length > 0) {
      await nextTick(); selectPair(0)
      // 检查是否已有结果输出
      const query = new URLSearchParams({ folder: folderPath.value })
      if (typeof preferMode === 'number') query.set('prefer_mode', String(preferMode))
      const mode = typeof preferMode === 'number' ? preferMode : lastOfflineInferMode.value
      try {
        const checkRes = await fetch(`/offline/check_existing_result?${query.toString()}`)
        const checkData = await readJsonResponse<any>(checkRes, '检查已有结果')
        console.log('[doScan] check_existing_result response:', checkData)
        if (checkData.ok && checkData.output_dir) {
          resultDir.value = checkData.output_dir
          resultImages.value = checkData.images || []
          resultDirLabel.value = checkData.output_dir.split('/').pop() || ''
          resultPcdDir.value = checkData.pcd_dir || ''
          resultPcds.value = checkData.pcds || []
          console.log('[doScan] resultPcdDir set to:', resultPcdDir.value)
          console.log('[doScan] resultImages count:', resultImages.value.length)
          offlineStatus.value = `✓ 已加载现有结果 (${resultImages.value.length} 张)`
        } else {
          console.log('[doScan] No existing result found, will infer pcd_dir after processing')
          applyInferredResultDirs(mode, folderPath.value)
        }
      } catch (error) {
        console.warn('[doScan] check_existing_result failed, continuing with inferred result dirs:', error)
        applyInferredResultDirs(mode, folderPath.value)
      }
      await nextTick()
      if (resultPcdCanvasRef.value && !resultPcdCtx)
        resultPcdCtx = initViewer(resultPcdCanvasRef.value)
      await selectPair(0)
      if (!offlineStatus.value && resultDir.value) {
        offlineStatus.value = '已加载原始预览'
      }
    }
  } catch (e) {
    scanStatus.value = `错误: ${e}`; scanError.value = true
  } finally { scanning.value = false }
}

async function doScanDay() {
  // 白天模式：扫描白天文件夹，使用 mode=6 (Sub)
  if (!dayFolderPath.value || !dayFolderPath.value.trim()) {
    console.warn('[doScanDay] dayFolderPath is empty')
    return
  }
  folderPath.value = dayFolderPath.value
  lastOfflineInferMode.value = 6
  // 扫描时指定 preferMode=6，这样会查找 sub_6_205_432 和 pcd_6_205_432
  await doScan(6)
}

async function doScanNight() {
  // 夜晚模式：扫描夜晚文件夹，使用 mode=99/7 (DSG)
  if (!folderPath.value || !folderPath.value.trim()) {
    console.warn('[doScanNight] folderPath is empty')
    return
  }
  lastOfflineInferMode.value = 99
  // 扫描时指定 preferMode=99，这样会查找 dsg_7_205_432 和 pcd_7_205_432
  await doScan(99)
}

function imgUrl(fname: string) {
  return `/offline/local_file?path=${encodeURIComponent(imagesDir.value + '/' + fname)}`
}
function resultImgUrl(fname: string) {
  return `/offline/local_file?path=${encodeURIComponent(resultDir.value + '/' + fname)}`
}

function onThumbError(e: Event, idx: number) {
  const img = e.target as HTMLImageElement
  console.error(`[Thumb ${idx}] Image load failed:`, img.src)
  console.error(`[Thumb ${idx}] pair.img:`, pairs.value[idx]?.img)
  console.error(`[Thumb ${idx}] imagesDir:`, imagesDir.value)
  // 显示错误占位符
  img.style.display = 'none'
  const parent = img.parentElement
  if (parent) {
    const placeholder = document.createElement('div')
    placeholder.className = 'sa2-thumb-noimag'
    placeholder.textContent = '加载失败'
    parent.insertBefore(placeholder, img)
  }
}

async function archiveFrame() {
  if (selectedIdx.value < 0 || !archiveDir.value) return
  archiveStatus.value = ''
  archiveError.value = false
  const pair = pairs.value[selectedIdx.value]
  try {
    const res = await fetch('/offline/archive_frame', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pcd_path: pcdsDir.value + '/' + pair.pcd,
        img_path: pair.img ? imagesDir.value + '/' + pair.img : null,
        archive_dir: archiveDir.value,
      }),
    })
    const data = await readJsonResponse<any>(res, '归档障碍帧')
    if (data.ok) {
      archiveStatus.value = `✓ 已归档 ${data.archived_count} 文件`
    } else {
      archiveStatus.value = `✗ ${data.error}`; archiveError.value = true
    }
  } catch (e) {
    archiveStatus.value = `✗ 请求失败`; archiveError.value = true
  }
}

async function doUploadImages() {
  if (!uploadDateStart.value || !uploadDateEnd.value || !uploadPort.value || uploadRunning.value) return
  uploadRunning.value = true
  uploadStatus.value = '正在连接...'
  uploadError.value = false

  // 设置超时控制
  const controller = new AbortController()
  const timeoutId = setTimeout(() => {
    controller.abort()
    uploadStatus.value = '✗ 请求超时（60秒）'
    uploadError.value = true
    uploadRunning.value = false
  }, 60000) // 60秒超时

  try {
    uploadStatus.value = '正在上传图片...'
    const res = await fetch('/offline/upload_images_range', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        port: uploadPort.value,
        date_start: uploadDateStart.value,
        date_end: uploadDateEnd.value,
      }),
      signal: controller.signal,
    })

    clearTimeout(timeoutId)

    if (!res.ok) {
      uploadStatus.value = `✗ 服务器错误 (HTTP ${res.status})`
      uploadError.value = true
      return
    }

    const data = await res.json()
    console.log('[doUploadImages] 响应数据:', data)

    if (data.ok) {
      if (data.folder_count > 0 || data.file_count > 0) {
        uploadStatus.value = `✓ 已上传 ${data.folder_count} 个文件夹，${data.file_count} 个文件`
        if (data.errors && data.errors.length > 0) {
          uploadStatus.value += ` (${data.errors.length} 个错误)`
          console.error('[Upload Errors]', data.errors)
        }
      } else {
        uploadStatus.value = `✗ 上传失败: ${data.errors && data.errors.length > 0 ? data.errors.join('; ') : '未找到匹配文件夹或下载失败'}`
        uploadError.value = true
      }
    } else {
      uploadStatus.value = `✗ ${data.error || '未知错误'}`
      if (data.debug_info) {
        uploadStatus.value += ` (${data.debug_info})`
      }
      uploadError.value = true
    }
  } catch (e: any) {
    clearTimeout(timeoutId)
    if (e.name === 'AbortError') {
      console.log('[doUploadImages] 请求已超时')
      // 超时消息已在 setTimeout 中设置
    } else {
      console.error('[doUploadImages] 请求异常:', e)
      uploadStatus.value = `✗ 请求失败: ${e.message || '网络错误'}`
      uploadError.value = true
    }
  } finally {
    uploadRunning.value = false
  }
}

async function runNightOfflineDebug() {
  console.log('[runNightOfflineDebug] Starting DSG Night mode processing')
  console.log('[runNightOfflineDebug] folderPath:', folderPath.value)
  lastOfflineInferMode.value = 99

  // Mode 7: DSG Night recognition
  // - Uses adaptive stereo matching parameters for night scenes
  // - Processes with DSG multi-task model (detection + segmentation)
  // - Crops to 432 height, resizes to 384 for inference
  // - Maps detection IDs to 100+ format
  // - Supports optional CDT (charge station detection)
  // - Performs depth computation and fusion at 432 resolution
  await doRunOffline(folderPath.value, 99, 205, false)
}

async function resumeOfflineDebug() {
  const resumeDir = lastOfflineInferMode.value === 6 ? dayFolderPath.value : folderPath.value
  await doRunOffline(resumeDir, lastOfflineInferMode.value, 205, true)
}

async function runDayOfflineDebug() {
  console.log('[runDayOfflineDebug] === START ===')
  console.log('[runDayOfflineDebug] dayFolderPath:', dayFolderPath.value)
  console.log('[runDayOfflineDebug] folderPath:', folderPath.value)
  console.log('[runDayOfflineDebug] pairs.length:', pairs.value.length)

  try {
    lastOfflineInferMode.value = 6

    if (!dayFolderPath.value || !dayFolderPath.value.trim()) {
      console.error('[runDayOfflineDebug] dayFolderPath is empty')
      offlineStatus.value = '✗ 请输入白天文件夹路径'
      offlineError.value = true
      return
    }

    // 先扫描白天文件夹，确保 pairs 有数据
    if (pairs.value.length === 0 || folderPath.value !== dayFolderPath.value) {
      console.log('[runDayOfflineDebug] Need to scan first')
      folderPath.value = dayFolderPath.value
      console.log('[runDayOfflineDebug] Calling doScan(6)...')
      await doScan(6)
      console.log('[runDayOfflineDebug] doScan completed, pairs.length:', pairs.value.length)

      // 等待扫描完成
      if (pairs.value.length === 0) {
        console.error('[runDayOfflineDebug] No image pairs found after scanning')
        offlineStatus.value = '✗ 未找到图片或点云'
        offlineError.value = true
        return
      }
    }

    console.log('[runDayOfflineDebug] Found', pairs.value.length, 'pairs')

    // 检查是否有已处理的结果，如果有则继续执行
    const expectedDir = expectedResultDir(6, dayFolderPath.value)
    const hasResults = resultImages.value.length > 0 && resultDir.value === expectedDir
    const resume = hasResults
    console.log('[runDayOfflineDebug] expectedDir:', expectedDir)
    console.log('[runDayOfflineDebug] hasResults:', hasResults, 'resume:', resume)

    // Mode 6: CDT+Multi-Sub Day mode
    console.log('[runDayOfflineDebug] Calling doRunOffline with mode=6')
    await doRunOffline(dayFolderPath.value, 6, 205, resume)
    console.log('[runDayOfflineDebug] === END ===')
  } catch (error) {
    console.error('[runDayOfflineDebug] === ERROR ===', error)
    offlineStatus.value = `✗ 错误: ${error}`
    offlineError.value = true
    offlineRunning.value = false
  }
}

async function resumeDayOfflineDebug() {
  // 继续执行白天模式
  lastOfflineInferMode.value = 6
  await doRunOffline(dayFolderPath.value, 6, 205, true)
}

async function doRunOffline(inputDir: string, inferMode: number, erodePixel: number, resume: boolean = false) {
  console.log('[doRunOffline] inputDir:', inputDir, 'inferMode:', inferMode, 'erodePixel:', erodePixel, 'resume:', resume)
  if (!inputDir || offlineRunning.value) return
  offlineRunToken += 1
  const runToken = offlineRunToken
  closeOfflineEventStream()
  clearOfflineReconnectTimer()
  clearOfflineStatusPollTimer()
  lastOfflineInferMode.value = inferMode
  offlineRunning.value = true
  offlineStatus.value = '启动中...'
  offlineError.value = false
  if (!resume) resetResultState()
  progressTotal.value = pairs.value.length
  if (resume && resultImages.value.length > 0) {
    progressCurrent.value = resultImages.value.length
    offlineStatus.value = `从第 ${progressCurrent.value} 张继续...`
  } else {
    progressCurrent.value = 0
  }
  try {
    console.log('[doRunOffline] Sending POST request to /offline/run')
    const res = await fetch('/offline/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input_dir: inputDir, infer_mode: inferMode, erode_pixel: erodePixel, resume }),
    })
    console.log('[doRunOffline] Response status:', res.status)
    const startData = await readJsonResponse<any>(res, '启动离线调试')
    console.log('[doRunOffline] Response data:', startData)
    if (!startData.ok) {
      offlineStatus.value = `✗ ${startData.error}`; offlineError.value = true
      offlineRunning.value = false; return
    }
    startOfflineStatusPolling(runToken, inputDir)
    connectOfflineEventStream(runToken, inputDir)
  } catch (e) {
    offlineStatus.value = `✗ 请求失败`; offlineError.value = true
    offlineRunning.value = false
    closeOfflineEventStream()
    clearOfflineReconnectTimer()
    clearOfflineStatusPollTimer()
  }
}

async function loadResultPcd(i: number) {
  if (!resultPcdCtx || !resultImages.value[i]) return
  resultSelectedIdx.value = i
  const imgStem = stemName(resultImages.value[i])
  const pcdPath = resultPcdDir.value + '/' + imgStem + '.pcd'
  resultPcdStatus.value = '加载中...'
  try {
    const res = await fetch(`/offline/local_file?path=${encodeURIComponent(pcdPath)}`)
    if (!res.ok) { resultPcdStatus.value = '❌ 无结果点云'; return }
    const text = await res.text()
    loadPcdIntoCtx(resultPcdCtx, text, resultPcdStatus)
  } catch (e) { resultPcdStatus.value = `❌ ${e}` }
}


// ─── PCD renderer ───���────────────────────────────────────────
const LA2_LABEL_COLOR: Record<number, [number, number, number]> = {
  0: [0, 0, 200/255], 1: [0, 0, 200/255],
  2: [100/255, 255/255, 102/255], 3: [118/255, 89/255, 0],
  4: [1, 1, 0], 5: [1, 0, 0], 6: [1, 165/255, 0],
  7: [1, 20/255, 147/255], 8: [0, 1, 1],
  100: [1, 0, 0], 101: [1, 0, 0], 102: [1, 0, 0],
  103: [1, 0, 1], 104: [1, 0, 0], 105: [1, 1, 0], 106: [0, 1, 1],
}
const PASSABLE_LABELS = new Set([2])
function la2Color(label: number): [number, number, number] {
  return LA2_LABEL_COLOR[label] ?? [0.5, 0.5, 0.5]
}

interface PcdCtx {
  renderer: THREE.WebGLRenderer; scene: THREE.Scene; cam: THREE.PerspectiveCamera
  animId: number; points: THREE.Points | null; sph: SphState; orbitCleanup: (() => void) | null
}
let pcdCtx: PcdCtx | null = null
let resultPcdCtx: PcdCtx | null = null

const pcdCanvasRef = ref<HTMLCanvasElement | null>(null)
const resultPcdCanvasRef = ref<HTMLCanvasElement | null>(null)

function initViewer(canvas: HTMLCanvasElement): PcdCtx {
  canvas.width = canvas.clientWidth || 640
  canvas.height = canvas.clientHeight || 300
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

async function selectPair(i: number) {
  selectedIdx.value = i
  await nextTick()

  // 1. 加載原始點雲（如果存在）
  const canvas = pcdCanvasRef.value
  if (canvas && pcdsDir.value) {
    if (!pcdCtx || pcdCtx.renderer.domElement !== canvas) {
      if (pcdCtx) { disposeCtx(pcdCtx); pcdCtx = null }
      pcdCtx = initViewer(canvas)
    }
    pcdStatus.value = '加载中...'
    try {
      const pcdName = pairs.value[i].pcd
      const stem = pcdName.replace(/\.[^.]+$/, '')
      let pcdPath = pcdsDir.value + '/' + pcdName
      let res = await fetch(`/offline/local_file?path=${encodeURIComponent(pcdPath)}`)
      if (!res.ok) {
        pcdPath = pcdsDir.value + '/' + stem + '/' + pcdName
        res = await fetch(`/offline/local_file?path=${encodeURIComponent(pcdPath)}`)
      }
      if (!res.ok) { pcdStatus.value = '❌ 无原始点云' }
      else { loadPcdIntoCtx(pcdCtx, await res.text(), pcdStatus) }
    } catch (e) { pcdStatus.value = `❌ ${e}` }
  } else if (canvas) {
    pcdStatus.value = '❌ 无原始点云'
  }

  // 2. 加載結果點雲 (聯動)
  const resCanvas = resultPcdCanvasRef.value
  console.log('[selectPair] resCanvas exists:', !!resCanvas)
  console.log('[selectPair] resultPcdDir:', resultPcdDir.value)
  if (resCanvas && resultPcdDir.value) {
    console.log('[selectPair] Loading result PCD for index:', i)
    console.log('[selectPair] resultPcdDir:', resultPcdDir.value)
    console.log('[selectPair] resultPcds:', resultPcds.value)
    if (!resultPcdCtx || resultPcdCtx.renderer.domElement !== resCanvas) {
      if (resultPcdCtx) { disposeCtx(resultPcdCtx); resultPcdCtx = null }
      resultPcdCtx = initViewer(resCanvas)
      console.log('[selectPair] Initialized result PCD viewer')
    }
    resultPcdStatus.value = '加载中...'
    try {
      const pcdName = pairs.value[i].pcd
      const stem = stemName(pcdName)
      console.log('[selectPair] Looking for PCD with stem:', stem)
      const matchedResultPcd = resultPcds.value.find((name) => {
        const candidate = stemName(name).toLowerCase()
        const target = stem.toLowerCase()
        return candidate === target || candidate.startsWith(target + '_') || candidate.includes(target + '_')
      })

      const candidatePaths = matchedResultPcd
        ? [resultPcdDir.value + '/' + matchedResultPcd]
        : [
            resultPcdDir.value + '/' + stem + '.pcd',
            resultPcdDir.value + '/' + stem + '_dsg.pcd',
            resultPcdDir.value + '/' + stem + '_rgbl.pcd',
            resultPcdDir.value + '/' + pcdName,
          ]

      let res: Response | null = null
      let pcdPath = ''
      for (const candidatePath of candidatePaths) {
        pcdPath = candidatePath
        console.log('[selectPair] Trying path:', pcdPath)
        res = await fetch(`/offline/local_file?path=${encodeURIComponent(pcdPath)}`)
        console.log('[selectPair] Response status:', res.status)
        if (res.ok) break
      }

      if (!res || !res.ok) {
        console.log('[selectPair] All PCD paths failed, status:', res?.status)
        resultPcdStatus.value = '❌ 無結果點雲'
      }
      else {
        console.log('[selectPair] Successfully loaded PCD from:', pcdPath)
        loadPcdIntoCtx(resultPcdCtx, await res.text(), resultPcdStatus)
      }
    } catch (e) {
      console.error('[selectPair] Error loading result PCD:', e)
      resultPcdStatus.value = `❌ ${e}`
    }
  } else {
    console.log('[selectPair] Skipping result PCD load - resCanvas:', !!resCanvas, 'resultPcdDir:', resultPcdDir.value)
    if (!resultPcdDir.value) {
      resultPcdStatus.value = '❌ 暂无结果点云目录'
    }
  }
}

function disposeCtx(ctx: PcdCtx) {
  cancelAnimationFrame(ctx.animId)
  ctx.orbitCleanup?.()
  ctx.points?.geometry.dispose()
  if (ctx.points) (ctx.points.material as THREE.Material).dispose()
  ctx.renderer.dispose()
}

onBeforeUnmount(() => {
  closeOfflineEventStream()
  clearOfflineReconnectTimer()
  clearOfflineStatusPollTimer()
  if (pcdCtx) { disposeCtx(pcdCtx); pcdCtx = null }
  if (resultPcdCtx) { disposeCtx(resultPcdCtx); resultPcdCtx = null }
})
</script>
<style scoped>
.sa2-root { display:flex; flex-direction:column; height:100%; background:#1a1a2e; color:#e0e0e0; font-size:13px; overflow:hidden; }
.sa2-input-bar { background:#0d1117; border-bottom:1px solid #1e2a3a; padding:6px 14px; display:flex; align-items:center; gap:8px; flex-wrap:wrap; flex-shrink:0; }
.sa2-input-bar label { font-size:11px; color:#888; white-space:nowrap; }
.sa2-path-input { flex:1; min-width:260px; background:#1a1a2e; border:1px solid #333; border-radius:4px; padding:4px 8px; color:#e0e0e0; font-size:11px; font-family:monospace; }
.sa2-path-input:focus { outline:none; border-color:#4fc3f7; }
.sa2-sn-input { width:60px; background:#1a1a2e; border:1px solid #333; border-radius:4px; padding:4px 8px; color:#e0e0e0; font-size:11px; font-family:monospace; text-align:center; }
.sa2-sn-input:focus { outline:none; border-color:#4fc3f7; }
.sa2-path-input-sm { width:200px; background:#1a1a2e; border:1px solid #333; border-radius:4px; padding:4px 8px; color:#e0e0e0; font-size:11px; font-family:monospace; }
.sa2-label-input { width:50px; background:#1a1a2e; border:1px solid #333; border-radius:4px; padding:4px 6px; color:#e0e0e0; font-size:11px; text-align:center; }
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
.sa2-status.error { color:#ef5350; }
.sa2-progress-container { width:180px; height:18px; background:#222; border-radius:9px; position:relative; overflow:hidden; border:1px solid #444; margin-left:8px; }
.sa2-progress-bar { height:100%; background:linear-gradient(90deg, #4f46e5, #9333ea); transition:width 0.3s ease; }
@keyframes pulse { 0%, 100% { opacity: 0.6; } 50% { opacity: 1; } }
.sa2-progress-text { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-size:9px; color:#fff; text-shadow:0 0 2px #000; font-weight:bold; pointer-events:none; }
.sa2-arch-status { font-size:11px; color:#82b1ff; font-family:monospace; white-space:nowrap; }
.sa2-arch-status.error { color:#ef5350; }
.sa2-dbg-status { font-size:11px; color:#ce93d8; font-family:monospace; white-space:nowrap; max-width:300px; overflow:hidden; text-overflow:ellipsis; }
.sa2-dbg-status.error { color:#ef5350; }
.sa2-legend { display:flex; align-items:center; gap:10px; flex-wrap:wrap; font-size:11px; padding:4px 14px; background:#12192a; border-bottom:1px solid #1e2a3a; flex-shrink:0; }
.sa2-li { display:flex; align-items:center; gap:4px; }
.sa2-dot { width:9px; height:9px; border-radius:50%; display:inline-block; flex-shrink:0; }
.sa2-nav-info { font-size:11px; color:#90caf9; font-family:monospace; margin-left:auto; }
.sa2-nav-btn { padding:2px 10px; background:#1a2a4a; border:1px solid #1565c0; border-radius:3px; color:#4fc3f7; cursor:pointer; font-size:12px; }
.sa2-nav-btn:disabled { opacity:.3; cursor:not-allowed; }
.sa2-nav-btn:hover:not(:disabled) { background:#1e3a6a; }
.sa2-body { display:flex; flex-direction:column; flex:1; min-height:0; }
.sa2-top { display:flex; flex-direction:column; flex:1; min-height:0; border-bottom:1px solid #1e2a3a; }
.sa2-thumb-strip { display:flex; gap:4px; padding:5px 10px; overflow-x:auto; overflow-y:hidden; background:#080c14; border-bottom:1px solid #1e2a3a; flex-shrink:0; height:74px; align-items:center; }
.sa2-thumb-item { flex-shrink:0; width:76px; cursor:pointer; border:2px solid #333; border-radius:3px; overflow:hidden; transition:border-color .2s; }
.sa2-thumb-item.active { border-color:#4fc3f7; }
.sa2-thumb-item:hover { border-color:#90caf9; }
.sa2-thumb-item img { width:100%; height:46px; object-fit:cover; display:block; background:#222; }
.sa2-thumb-noimag { width:100%; height:46px; background:#111; display:flex; align-items:center; justify-content:center; font-size:9px; color:#555; }
.sa2-thumb-name { font-size:9px; color:#555; text-align:center; padding:1px 0; background:#0a0e15; }
.sa2-main { display:flex; flex:1; min-height:0; }
.sa2-left { flex:1; display:flex; flex-direction:column; border-right:1px solid #1e2a3a; min-height:0; overflow:hidden; padding:5px; }
.sa2-right { flex:1; display:flex; flex-direction:column; min-height:0; padding:5px; }
.sa2-panel-label { font-size:10px; color:#4fc3f7; padding:2px 4px; flex-shrink:0; }
.sa2-pcd-status { font-size:10px; color:#888; margin-left:6px; font-family:monospace; }
.sa2-stereo-img { flex:1; width:100%; min-height:0; object-fit:contain; background:#050810; border-radius:3px; display:block; cursor:zoom-in; }
.sa2-pcd-canvas { flex:1; display:block; width:100%; min-height:0; }
.sa2-placeholder { flex:1; display:flex; align-items:center; justify-content:center; color:#444; font-size:13px; }
.sa2-frame-info { font-size:9px; color:#444; font-family:monospace; flex-shrink:0; padding:2px 0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.sa2-bottom { display:flex; flex:1; min-height:0; }
.sa2-result-left { flex:1; display:flex; flex-direction:column; border-right:1px solid #1e2a3a; min-height:0; overflow:hidden; padding:5px; }
.sa2-result-right { flex:1; display:flex; flex-direction:column; min-height:0; padding:5px; }
.sa2-result-dir { font-size:9px; color:#555; font-family:monospace; margin-left:6px; }
.sa2-result-thumb-strip { display:flex; gap:4px; overflow-x:auto; flex-shrink:0; height:58px; align-items:center; padding:3px 0; }
.sa2-result-img-grid { flex:1; display:grid; grid-template-columns:repeat(3, 1fr); gap:2px; overflow-y:auto; min-height:0; align-content:start; }
.sa2-result-grid-img { width:100%; aspect-ratio:4/3; object-fit:contain; background:#050810; cursor:pointer; display:block; }
.sa2-result-grid-img.active { outline:2px solid #4fc3f7; }
.sa2-result-img { flex:1; width:100%; min-height:0; object-fit:contain; background:#050810; border-radius:3px; display:block; cursor:zoom-in; }
.sa2-empty { flex:1; display:flex; align-items:center; justify-content:center; color:#444; font-size:14px; }
.sa2-zoom-overlay { position:fixed; inset:0; background:rgba(0,0,0,.93); z-index:9999; display:flex; align-items:center; justify-content:center; cursor:zoom-out; }
.sa2-zoom-img { max-width:92vw; max-height:92vh; object-fit:contain; border:2px solid #4fc3f7; border-radius:4px; cursor:default; }
.sa2-port-input { width:64px; background:#1a1a2e; border:1px solid #333; border-radius:4px; padding:4px 6px; color:#e0e0e0; font-size:11px; text-align:center; }
.sa2-date-input { width:80px; background:#1a1a2e; border:1px solid #333; border-radius:4px; padding:4px 6px; color:#e0e0e0; font-size:11px; font-family:monospace; }
.sa2-upload-btn { padding:4px 12px; background:#1a3a1a; border:1px solid #2e7d32; border-radius:4px; color:#a5d6a7; font-size:11px; cursor:pointer; white-space:nowrap; }
.sa2-upload-btn:hover:not(:disabled) { background:#2e5a2e; }
.sa2-upload-btn:disabled { opacity:.5; cursor:not-allowed; }
.sa2-upload-status { font-size:11px; color:#69f0ae; font-family:monospace; white-space:nowrap; }
.sa2-upload-status.error { color:#ef5350; }
</style>
