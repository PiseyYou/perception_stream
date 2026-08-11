<template>
  <div class="prelabel-root">
    <div class="prelabel-toolbar">
      <div class="prelabel-token">
        <span>Token</span>
        <code>{{ tokenLabel }}</code>
      </div>
      <div class="prelabel-container">
        <span class="status-pill" :class="containerClass">{{ containerLabel }}</span>
        <span class="gpu-pill" :class="{ ok: containerStatus.gpu_ok }">{{ containerStatus.gpu_ok ? 'GPU OK' : 'GPU --' }}</span>
        <button class="prelabel-btn ghost" :disabled="statusLoading" @click="loadContainerStatus">
          {{ statusLoading ? '刷新中' : '刷新' }}
        </button>
        <button class="prelabel-btn warn" :disabled="restarting || running" @click="restartContainer">
          {{ restarting ? '重启中' : '重启容器' }}
        </button>
      </div>
    </div>

    <div class="prelabel-main">
      <section class="prelabel-config">
        <div class="prelabel-band">
          <div class="band-title">CVAT</div>
          <div class="server-list">
            <div v-for="server in cvatServers" :key="server.id" class="server-row" :class="{ active: selectedServerId === server.id }">
              <label class="radio-row">
                <input v-model="selectedServerId" type="radio" :value="server.id" />
                <span>{{ server.name || server.id }}</span>
              </label>
              <input v-model="server.host" class="small-input host-input" placeholder="host" :disabled="running" />
              <input v-model.number="server.port" class="small-input port-input" type="number" min="1" max="65535" :disabled="running" />
              <input v-model.trim="server.user" class="small-input user-input" placeholder="CVAT 用户名" :disabled="running" />
              <input
                v-model="server.password"
                class="small-input password-input"
                type="password"
                :placeholder="server.has_password ? '密码已保存' : 'CVAT 密码'"
                autocomplete="new-password"
                :disabled="running"
              />
              <button class="prelabel-btn ghost" :disabled="serverSavingId === server.id || running" @click="saveServerSettings(server)">
                {{ serverSavingId === server.id ? '保存中' : '保存' }}
              </button>
            </div>
            <div v-if="!cvatServers.length" class="inline-empty">未加载 CVAT server</div>
          </div>
          <div class="form-grid">
            <label>
              <span>分配用户</span>
              <select v-model="assigneeId" class="select-input" :disabled="usersLoading || running">
                <option value="">不分配</option>
                <option v-for="user in cvatUsers" :key="user.id" :value="String(user.id)">
                  {{ userLabel(user) }}
                </option>
              </select>
            </label>
            <button class="prelabel-btn ghost grid-button" :disabled="usersLoading || !selectedServerId || running" @click="loadCvatUsers(true)">
              {{ usersLoading ? '加载中' : '刷新用户' }}
            </button>
          </div>
        </div>

        <div class="prelabel-band">
          <div class="band-title">任务</div>
          <div class="form-grid">
            <label>
              <span>任务前缀</span>
              <input v-model.trim="taskPrefix" class="text-input" placeholder="prelabel_0429" :disabled="running" />
            </label>
            <label>
              <span>min_area</span>
              <input v-model.number="minArea" class="text-input" type="number" min="0" :disabled="running" />
            </label>
            <label>
              <span>segment_size</span>
              <input v-model.number="segmentSize" class="text-input" type="number" min="1" :disabled="running" />
            </label>
            <label class="check-row">
              <input v-model="serialMode" type="checkbox" :disabled="running" />
              <span>串行执行</span>
            </label>
            <label class="check-row">
              <input v-model="pipelineMode" type="radio" value="standard" :disabled="running" />
              <span>标准预标注</span>
            </label>
            <label class="check-row">
              <input v-model="pipelineMode" type="radio" value="shadow_ab" :disabled="running" />
              <span>A/B 影子验证</span>
            </label>
          </div>
        </div>

        <div class="prelabel-band">
          <div class="band-title">来源</div>
          <div class="segmented">
            <button :class="{ active: sourceMode === 'server' }" :disabled="running" @click="sourceMode = 'server'">服务器目录</button>
            <button :class="{ active: sourceMode === 'files' }" :disabled="running" @click="sourceMode = 'files'">上传文件</button>
            <button :class="{ active: sourceMode === 'folder' }" :disabled="running" @click="sourceMode = 'folder'">上传文件夹</button>
          </div>

          <div v-if="sourceMode === 'server'" class="source-block">
            <div v-for="(dir, index) in serverDirs" :key="index" class="dir-row">
              <input v-model.trim="serverDirs[index]" class="path-input" placeholder="/media/sdc2/lhx/MPformer/..." :disabled="running" />
              <button class="prelabel-btn ghost" :disabled="running" @click="openBrowser(index)">浏览</button>
              <button class="icon-btn" :disabled="serverDirs.length <= 1 || running" title="删除" @click="removeServerDir(index)">×</button>
            </div>
            <button class="prelabel-btn ghost" :disabled="running" @click="addServerDir">添加目录</button>
          </div>

          <div v-else class="source-block">
            <input
              v-if="sourceMode === 'files'"
              ref="fileInputRef"
              type="file"
              multiple
              accept="image/*"
              class="file-input"
              :disabled="running"
              @change="onFileChange"
            />
            <input
              v-else
              ref="folderInputRef"
              type="file"
              multiple
              webkitdirectory
              class="file-input"
              :disabled="running"
              @change="onFolderChange"
            />
            <div class="upload-line">
              <span class="upload-summary">{{ fileSummary }}</span>
              <button class="prelabel-btn ghost" :disabled="!selectedFiles.length || uploading || running" @click="clearUploadSelection">清空</button>
              <button class="prelabel-btn" :disabled="!selectedFiles.length || uploading || running" @click="uploadSelectedFiles(true)">
                {{ uploading ? '上传中' : '上传' }}
              </button>
            </div>
            <div v-if="uploadId || uploading" class="progress-track">
              <div class="progress-fill" :style="{ width: `${uploadProgress}%` }"></div>
              <span>{{ uploadProgress }}% · {{ uploadSaved }}/{{ uploadTotal || selectedFiles.length }} · {{ uploadId || '创建上传中' }}</span>
            </div>
          </div>

          <div v-if="browserOpen" class="browser-panel">
            <div class="browser-bar">
              <input v-model.trim="browsePath" class="path-input" placeholder="浏览路径" :disabled="running" @keyup.enter="browseDirectory(browsePath)" />
              <button class="prelabel-btn ghost" :disabled="browsing || running" @click="browseDirectory(parentPath(browsePath))">上级</button>
              <button class="prelabel-btn ghost" :disabled="browsing || running" @click="browseDirectory(browsePath)">打开</button>
              <button class="prelabel-btn" :disabled="running" @click="applyBrowsePath">使用此路径</button>
            </div>
            <div class="browser-list">
              <button v-for="dir in browseDirs" :key="dir.path" class="browser-item" @click="browseDirectory(dir.path)">
                {{ dir.name }}
              </button>
              <div v-if="!browseDirs.length" class="inline-empty">{{ browsing ? '加载中...' : '无子目录' }}</div>
            </div>
          </div>
        </div>

        <div class="prelabel-actions">
          <button class="prelabel-btn primary" :disabled="!canStart" @click="startRun('full')">
            {{ starting ? '启动中' : '开始完整流程' }}
          </button>
          <button class="prelabel-btn" :disabled="!canStart" @click="startRun('uploadOnly')">
            仅上传到 CVAT
          </button>
          <button v-if="ownedRunningRun" class="prelabel-btn danger" @click="cancelRun(ownedRunningRun)">
            停止
          </button>
          <span class="run-state">{{ runStatus }}</span>
        </div>
      </section>

      <section class="prelabel-runtime">
        <div class="timeline">
          <div v-for="step in steps" :key="step.step" class="timeline-step" :class="step.status">
            <div class="step-index">{{ step.step }}</div>
            <div class="step-text">
              <span>{{ step.label }}</span>
              <small>{{ step.msg || step.status }}</small>
            </div>
          </div>
        </div>

        <div class="runtime-grid">
          <div class="log-panel">
            <div class="panel-head">
              <span>运行日志</span>
              <button class="prelabel-btn ghost" @click="logs = []">清空</button>
            </div>
            <div ref="logBoxRef" class="log-box">
              <div v-for="(line, index) in logs" :key="index" class="log-line" :class="line.level || line.status || ''">
                <span class="log-time">{{ line.time || '--:--:--' }}</span>
                <span class="log-msg">{{ line.msg }}</span>
              </div>
              <div v-if="!logs.length" class="inline-empty">等待运行...</div>
            </div>
          </div>

          <div class="history-panel">
            <div class="panel-head">
              <span>历史</span>
              <button class="prelabel-btn ghost" :disabled="runsLoading" @click="loadRuns">{{ runsLoading ? '刷新中' : '刷新' }}</button>
            </div>
            <div class="run-list">
              <div
                v-for="run in runs"
                :key="run.run_id"
                class="run-item"
                :class="{ active: activeRunId === run.run_id }"
                role="button"
                tabindex="0"
                @click="loadRunDetail(run.run_id)"
                @keyup.enter="loadRunDetail(run.run_id)"
              >
                <span class="run-top">
                  <strong>{{ run.task_prefix || run.run_id }}</strong>
                  <em :class="run.status">{{ run.status }}</em>
                </span>
                <span class="run-meta">{{ run.created_at || '-' }} · {{ run.input_dirs?.join(', ') || '-' }}</span>
                <span class="run-actions">
                  <button
                    v-if="run.owned_by_client && run.status === 'running'"
                    class="mini-btn danger"
                    @click.stop="cancelRun(run)"
                  >Stop</button>
                  <button class="mini-btn" :disabled="run.status === 'running' || !run.owned_by_client" @click.stop="deleteRun(run)">Delete</button>
                </span>
              </div>
              <div v-if="!runs.length" class="inline-empty">暂无历史</div>
            </div>
          </div>
        </div>

        <div v-if="selectedDetail" class="detail-strip">
          <span>{{ selectedDetail.run_id }}</span>
          <span>{{ selectedDetail.status }}</span>
          <span>{{ selectedDetail.finished_at || selectedDetail.created_at }}</span>
          <a v-if="resultLink" :href="resultLink" target="_blank" rel="noopener">CVAT: {{ resultLink }}</a>
          <button v-if="shadowReviewReady" class="mini-btn" @click="loadShadowReview(selectedDetail.run_id)">匿名盲评</button>
        </div>

        <section v-if="reviewOpen" class="shadow-review" aria-label="匿名 A/B 盲评">
          <div class="panel-head">
            <span>匿名标注盲评 · {{ reviewIndex + 1 }}/{{ reviewSamples.length }}</span>
            <button class="prelabel-btn ghost" @click="reviewOpen = false">关闭</button>
          </div>
          <template v-if="reviewCurrent">
            <div class="review-pair">
              <figure><figcaption>X</figcaption><img :src="reviewAssetUrl('X')" alt="标注 X" /></figure>
              <figure><figcaption>Y</figcaption><img :src="reviewAssetUrl('Y')" alt="标注 Y" /></figure>
            </div>
            <div class="review-actions">
              <button v-for="choice in reviewChoices" :key="choice" class="mini-btn" :class="{ selected: reviewAnswers[reviewCurrent.sample_id] === choice }" @click="reviewAnswers[reviewCurrent.sample_id] = choice">{{ choice }}</button>
              <button class="mini-btn" :disabled="reviewIndex <= 0" @click="reviewIndex -= 1">上一个</button>
              <button class="mini-btn" :disabled="reviewIndex >= reviewSamples.length - 1" @click="reviewIndex += 1">下一个</button>
              <button class="prelabel-btn primary" :disabled="reviewSubmitting || !reviewComplete" @click="submitShadowReview">{{ reviewSubmitting ? '提交中' : '提交本次盲评' }}</button>
              <button class="prelabel-btn ghost" :disabled="reviewRevealing" @click="revealShadowReview">揭示结果（所有者）</button>
            </div>
          </template>
          <div v-if="reviewDecision" class="review-decision">{{ reviewDecision }}</div>
          <div v-if="reviewReveal" class="review-decision">{{ reviewReveal }}</div>
          <label v-if="reviewShareUrl" class="review-share"><span>评审链接</span><input readonly :value="reviewShareUrl" @focus="selectText" /></label>
          <div v-if="Object.keys(reviewTaskLinks).length" class="review-actions">
            <a v-for="(url, branch) in reviewTaskLinks" :key="branch" class="mini-btn" :href="url" target="_blank" rel="noopener">揭示后 CVAT {{ branch }}</a>
          </div>
        </section>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const TOKEN_KEY = 'PRELABEL_CLIENT_TOKEN'
const BATCH_SIZE = 200

type SourceMode = 'server' | 'files' | 'folder'
type StepStatus = 'pending' | 'active' | 'done' | 'skipped' | 'failed'
type RunMode = 'full' | 'uploadOnly'
type PipelineMode = 'standard' | 'shadow_ab'

interface CvatServer {
  id: string
  name: string
  host: string
  port: number
  user?: string
  password?: string
  has_password?: boolean
}

interface CvatUser {
  id: number
  username: string
  full_name?: string
}

interface UploadResponse {
  ok: boolean
  upload_id: string
  upload_dir: string
  count: number
  total_count: number
  skipped?: string[]
}

interface BrowseDir {
  name: string
  path: string
}

interface RunRecord {
  run_id: string
  status: string
  task_prefix: string
  input_dirs: string[]
  created_at: string
  finished_at?: string | null
  result?: unknown
  owned_by_client: boolean
  logs?: StreamEvent[]
}

interface StreamEvent {
  type?: string
  step?: number
  status?: string
  level?: string
  msg?: string
  time?: string
  cvat_url?: string
  [key: string]: unknown
}

interface StepItem {
  step: number
  label: string
  status: StepStatus
  msg: string
}

interface ContainerStatus {
  container?: string
  container_status?: string
  gpu_ok?: boolean
  gpu_info?: string
  docker_error?: string
}

interface ReviewSample {
  sample_id: string
  left: 'X'
  right: 'Y'
}

interface ReviewPayload {
  run_id: string
  samples: ReviewSample[]
}

type ApiOptions = Omit<RequestInit, 'body'> & {
  body?: BodyInit | Record<string, unknown> | null
}

const clientToken = getClientToken()
const tokenLabel = computed(() => `${clientToken.slice(0, 8)}...${clientToken.slice(-4)}`)

const taskPrefix = ref(`prelabel_${datePrefix()}`)
const sourceMode = ref<SourceMode>('server')
const serverDirs = ref<string[]>([''])
const selectedFiles = ref<File[]>([])
const uploadId = ref('')
const uploadProgress = ref(0)
const uploadSaved = ref(0)
const uploadTotal = ref(0)
const uploading = ref(false)
const starting = ref(false)
const runStatus = ref('空闲')

const cvatServers = ref<CvatServer[]>([])
const selectedServerId = ref('')
const cvatUsers = ref<CvatUser[]>([])
const assigneeId = ref('')
const minArea = ref(50)
const segmentSize = ref(1000)
const serialMode = ref(true)
const pipelineMode = ref<PipelineMode>('standard')
const usersLoading = ref(false)
const serverSavingId = ref('')

const runs = ref<RunRecord[]>([])
const runsLoading = ref(false)
const activeRunId = ref('')
const selectedDetail = ref<RunRecord | null>(null)
const reviewOpen = ref(false)
const reviewRunId = ref('')
const reviewToken = ref('')
const reviewSamples = ref<ReviewSample[]>([])
const reviewIndex = ref(0)
const reviewAnswers = ref<Record<string, string>>({})
const reviewSubmitting = ref(false)
const reviewRevealing = ref(false)
const reviewDecision = ref('')
const reviewReveal = ref('')
const reviewTaskLinks = ref<Record<string, string>>({})
const reviewChoices = ['X better', 'Y better', 'tie', 'undecidable'] as const

const logs = ref<StreamEvent[]>([])
const steps = ref<StepItem[]>(makeSteps())

const containerStatus = ref<ContainerStatus>({})
const statusLoading = ref(false)
const restarting = ref(false)

const browserOpen = ref(false)
const browsePath = ref('')
const browseDirs = ref<BrowseDir[]>([])
const browseTargetIndex = ref(0)
const browsing = ref(false)

const fileInputRef = ref<HTMLInputElement | null>(null)
const folderInputRef = ref<HTMLInputElement | null>(null)
const logBoxRef = ref<HTMLElement | null>(null)

let eventSource: EventSource | null = null
let statusTimer: number | null = null

const activeRun = computed(() => runs.value.find(run => run.run_id === activeRunId.value) || selectedDetail.value)
const ownedRunningRun = computed(() => runs.value.find(run => run.owned_by_client && run.status === 'running') || null)
const running = computed(() => Boolean(ownedRunningRun.value))
const canStart = computed(() => !uploading.value && !starting.value && !running.value && Boolean(taskPrefix.value.trim()) && hasSource())
const containerLabel = computed(() => {
  const name = containerStatus.value.container || 'container'
  const status = containerStatus.value.container_status || 'unknown'
  return `${name}: ${status}`
})
const containerClass = computed(() => ({
  ok: containerStatus.value.container_status === 'running',
  bad: containerStatus.value.container_status === 'not_found' || Boolean(containerStatus.value.docker_error),
}))
const fileSummary = computed(() => {
  if (!selectedFiles.value.length) return '未选择图片'
  const totalSize = selectedFiles.value.reduce((sum, file) => sum + file.size, 0)
  return `${selectedFiles.value.length} 个文件 · ${formatBytes(totalSize)}`
})
const resultLink = computed(() => findResultLink(selectedDetail.value?.result))
const shadowReviewReady = computed(() => Boolean(selectedDetail.value?.result && typeof selectedDetail.value.result === 'object' && (selectedDetail.value.result as Record<string, unknown>).review_ready))
const reviewCurrent = computed(() => reviewSamples.value[reviewIndex.value] || null)
const reviewComplete = computed(() => reviewSamples.value.length > 0 && reviewSamples.value.every(item => Boolean(reviewAnswers.value[item.sample_id])))
const reviewShareUrl = computed(() => reviewRunId.value && reviewToken.value ? `${window.location.origin}${window.location.pathname}?review_run=${encodeURIComponent(reviewRunId.value)}&review_token=${encodeURIComponent(reviewToken.value)}` : '')

watch(selectedServerId, () => {
  assigneeId.value = ''
  if (selectedServerId.value) loadCvatUsers()
})

watch(sourceMode, () => {
  clearUploadSelection()
})

onMounted(async () => {
  await Promise.all([loadCvatServers(), loadContainerStatus(), loadRuns()])
  const query = new URLSearchParams(window.location.search)
  const linkedRun = query.get('review_run')
  const linkedToken = query.get('review_token')
  if (linkedRun && linkedToken) void loadShadowReview(linkedRun, linkedToken)
  statusTimer = window.setInterval(loadContainerStatus, 60000)
})

onBeforeUnmount(() => {
  closeStream()
  if (statusTimer !== null) window.clearInterval(statusTimer)
})

function getClientToken(): string {
  const saved = localStorage.getItem(TOKEN_KEY)
  if (saved) return saved
  const generated = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`
  localStorage.setItem(TOKEN_KEY, generated)
  return generated
}

function datePrefix(): string {
  const now = new Date()
  const mm = String(now.getMonth() + 1).padStart(2, '0')
  const dd = String(now.getDate()).padStart(2, '0')
  return `${mm}${dd}`
}

async function apiJson<T>(url: string, options: ApiOptions = {}): Promise<T> {
  const headers = new Headers(options.headers || {})
  const rawBody = options.body
  let body: BodyInit | undefined

  if (rawBody instanceof FormData) {
    body = rawBody
  } else if (rawBody instanceof URLSearchParams || rawBody instanceof Blob || typeof rawBody === 'string') {
    body = rawBody
  } else if (rawBody !== undefined && rawBody !== null) {
    headers.set('Content-Type', 'application/json')
    body = JSON.stringify(rawBody)
  }

  const response = await fetch(url, { ...options, headers, body })
  const text = await response.text()
  let payload: any = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = { ok: false, error: text }
    }
  }
  if (!response.ok) {
    throw new Error(payload?.error || `${response.status} ${response.statusText}`)
  }
  return payload as T
}

function ownerHeaders(): HeadersInit {
  return { 'X-Prelabel-Owner-Token': clientToken }
}

async function loadCvatServers(): Promise<void> {
  try {
    const data = await apiJson<{ ok: boolean; servers: CvatServer[] }>('/prelabel/cvat-servers')
    cvatServers.value = (data.servers || []).map(server => ({ ...server, password: '' }))
    if (!selectedServerId.value && cvatServers.value.length) {
      selectedServerId.value = (cvatServers.value.find(server => server.has_password) || cvatServers.value[0]).id
    }
  } catch (error) {
    pushLog({ type: 'log', level: 'error', msg: `CVAT server 加载失败: ${messageOf(error)}` })
  }
}

async function loadCvatUsers(force = false): Promise<void> {
  if (!selectedServerId.value) return
  if (usersLoading.value && !force) return
  usersLoading.value = true
  try {
    const query = new URLSearchParams({ server_id: selectedServerId.value })
    const data = await apiJson<{ ok: boolean; users: CvatUser[] }>(`/prelabel/cvat-users?${query}`)
    cvatUsers.value = data.users || []
  } catch (error) {
    cvatUsers.value = []
    pushLog({ type: 'log', level: 'error', msg: `CVAT 用户加载失败: ${messageOf(error)}` })
  } finally {
    usersLoading.value = false
  }
}

async function saveServerSettings(server: CvatServer): Promise<void> {
  serverSavingId.value = server.id
  try {
    const body: Record<string, string | number> = {
      host: server.host,
      port: Number(server.port),
      user: server.user || '',
    }
    if (server.password) body.password = server.password
    const updated = await apiJson<{ ok: boolean; server: CvatServer }>(`/prelabel/settings/cvat-server/${encodeURIComponent(server.id)}`, {
      method: 'PATCH',
      body,
    })
    const index = cvatServers.value.findIndex(item => item.id === server.id)
    const saved = { ...updated.server, password: '' }
    if (index >= 0) cvatServers.value[index] = saved
    pushLog({ type: 'log', level: 'info', msg: `已保存 ${server.id} CVAT 配置` })
    await loadCvatUsers(true)
  } catch (error) {
    pushLog({ type: 'log', level: 'error', msg: `保存 CVAT 设置失败: ${messageOf(error)}` })
  } finally {
    serverSavingId.value = ''
  }
}

function userLabel(user: CvatUser): string {
  return user.full_name ? `${user.username} (${user.full_name})` : user.username
}

function addServerDir(): void {
  serverDirs.value.push('')
}

function removeServerDir(index: number): void {
  if (serverDirs.value.length <= 1) return
  serverDirs.value.splice(index, 1)
}

async function openBrowser(index: number): Promise<void> {
  browseTargetIndex.value = index
  browserOpen.value = true
  browsePath.value = serverDirs.value[index] || browsePath.value
  await browseDirectory(browsePath.value)
}

async function browseDirectory(path: string): Promise<void> {
  browsing.value = true
  try {
    const query = path ? `?${new URLSearchParams({ path })}` : ''
    const data = await apiJson<{ ok: boolean; path: string; directories: BrowseDir[] }>(`/prelabel/browse${query}`)
    browsePath.value = data.path
    browseDirs.value = data.directories || []
  } catch (error) {
    pushLog({ type: 'log', level: 'error', msg: `浏览目录失败: ${messageOf(error)}` })
  } finally {
    browsing.value = false
  }
}

function applyBrowsePath(): void {
  serverDirs.value[browseTargetIndex.value] = browsePath.value
  browserOpen.value = false
}

function parentPath(path: string): string {
  const cleaned = path.replace(/\/+$/, '')
  const index = cleaned.lastIndexOf('/')
  if (index > 0) return cleaned.slice(0, index)
  if (cleaned.startsWith('/')) return '/'
  return cleaned
}

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  selectedFiles.value = Array.from(input.files || [])
  uploadId.value = ''
  uploadProgress.value = 0
  uploadSaved.value = 0
  uploadTotal.value = selectedFiles.value.length
}

function onFolderChange(event: Event): void {
  onFileChange(event)
}

function clearUploadSelection(): void {
  selectedFiles.value = []
  uploadId.value = ''
  uploadProgress.value = 0
  uploadSaved.value = 0
  uploadTotal.value = 0
  if (fileInputRef.value) fileInputRef.value.value = ''
  if (folderInputRef.value) folderInputRef.value.value = ''
}

async function uploadSelectedFiles(reset = false): Promise<string> {
  if (!selectedFiles.value.length) throw new Error('请选择要上传的图片')
  uploading.value = true
  if (reset) uploadId.value = ''
  uploadProgress.value = 0
  uploadSaved.value = 0
  uploadTotal.value = selectedFiles.value.length
  try {
    for (let i = 0; i < selectedFiles.value.length; i += BATCH_SIZE) {
      const batch = selectedFiles.value.slice(i, i + BATCH_SIZE)
      const form = new FormData()
      for (const file of batch) form.append('files', file, file.name)
      form.append('owner_token', clientToken)
      form.append('folder_name', taskPrefix.value || 'prelabel_upload')
      if (uploadId.value) form.append('upload_id', uploadId.value)

      const result = await apiJson<UploadResponse>('/prelabel/upload', {
        method: 'POST',
        headers: ownerHeaders(),
        body: form,
      })
      uploadId.value = result.upload_id
      uploadSaved.value = result.total_count
      uploadProgress.value = Math.round((Math.min(i + batch.length, selectedFiles.value.length) / selectedFiles.value.length) * 100)
      if (result.skipped?.length) {
        pushLog({ type: 'log', level: 'warn', msg: `跳过 ${result.skipped.length} 个非图片文件` })
      }
    }
    pushLog({ type: 'log', level: 'info', msg: `上传完成: ${uploadSaved.value} 张，upload_id=${uploadId.value}` })
    return uploadId.value
  } finally {
    uploading.value = false
  }
}

async function startRun(mode: RunMode): Promise<void> {
  if (!taskPrefix.value.trim()) {
    alert('请填写任务前缀')
    return
  }
  starting.value = true
  runStatus.value = '启动中'
  try {
    let runUploadId = ''
    const inputDirs = sourceMode.value === 'server'
      ? serverDirs.value.map(item => item.trim()).filter(Boolean)
      : []

    if (sourceMode.value !== 'server') {
      runUploadId = uploadId.value || await uploadSelectedFiles(false)
    }

    const shadowRun = pipelineMode.value === 'shadow_ab' && mode === 'full'
    const body = {
      owner_token: clientToken,
      task_prefix: taskPrefix.value.trim(),
      input_dirs: inputDirs,
      upload_id: runUploadId,
      skip_steps: mode === 'uploadOnly' ? [2, 3, 4] : [],
      cvat_server_id: selectedServerId.value,
      assignee_id: assigneeId.value ? Number(assigneeId.value) : null,
      min_area: Number(minArea.value),
      segment_size: Number(segmentSize.value),
      serial_mode: Boolean(serialMode.value),
    }

    resetSteps(body.skip_steps)
    logs.value = []
    const data = await apiJson<{ run_id: string }>(shadowRun ? '/prelabel/shadow-run' : '/prelabel/run', {
      method: 'POST',
      headers: ownerHeaders(),
      body,
    })
    activeRunId.value = data.run_id
    runStatus.value = `运行中: ${data.run_id}`
    await loadRuns()
    connectStream(data.run_id)
  } catch (error) {
    runStatus.value = `启动失败: ${messageOf(error)}`
    pushLog({ type: 'log', level: 'error', msg: runStatus.value })
  } finally {
    starting.value = false
  }
}

function connectStream(runId: string): void {
  closeStream()
  const query = new URLSearchParams({ token: clientToken })
  eventSource = new EventSource(`/prelabel/stream/${runId}?${query}`)
  eventSource.onmessage = event => {
    if (event.data === 'null') {
      closeStream()
      runStatus.value = '已结束'
      void loadRunDetail(runId)
      void loadRuns()
      return
    }
    try {
      const item = JSON.parse(event.data) as StreamEvent
      handleStreamEvent(item)
    } catch {
      pushLog({ type: 'log', level: 'error', msg: event.data })
    }
  }
  eventSource.onerror = () => {
    pushLog({ type: 'log', level: 'error', msg: 'SSE 连接中断' })
    closeStream()
    void loadRuns()
  }
}

function closeStream(): void {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

function handleStreamEvent(item: StreamEvent): void {
  const type = item.type || 'log'
  if (type === 'step_start') {
    updateStep(item.step, 'active', item.msg)
  } else if (type === 'step_done') {
    updateStep(item.step, item.status === 'success' ? 'done' : 'failed', item.msg)
  } else if (type === 'step_skip') {
    updateStep(item.step, 'skipped', item.msg)
  } else if (type === 'pipeline_done') {
    runStatus.value = item.msg || `完成: ${item.status || ''}`
    void loadRuns()
  }
  pushLog(item)
}

function pushLog(item: StreamEvent): void {
  const normalized = { ...item }
  normalized.type = normalized.type || 'log'
  normalized.msg = normalized.msg || String(normalized.status || normalized.type)
  normalized.time = normalized.time || new Date().toLocaleTimeString()
  logs.value.push(normalized)
  if (logs.value.length > 1000) logs.value.splice(0, logs.value.length - 1000)
  void nextTick(() => {
    if (logBoxRef.value) logBoxRef.value.scrollTop = logBoxRef.value.scrollHeight
  })
}

async function loadRuns(): Promise<void> {
  runsLoading.value = true
  try {
    const data = await apiJson<RunRecord[] | { error?: string }>('/prelabel/runs', { headers: ownerHeaders() })
    if (!Array.isArray(data)) throw new Error(data.error || '历史响应格式错误')
    runs.value = data
    const ownedRunning = ownedRunningRun.value
    if (ownedRunning && !eventSource) {
      activeRunId.value = ownedRunning.run_id
      runStatus.value = `恢复连接: ${ownedRunning.run_id}`
      resetSteps()
      connectStream(ownedRunning.run_id)
    }
  } catch (error) {
    pushLog({ type: 'log', level: 'error', msg: `历史加载失败: ${messageOf(error)}` })
  } finally {
    runsLoading.value = false
  }
}

async function loadRunDetail(runId: string): Promise<void> {
  try {
    const detail = await apiJson<RunRecord>(`/prelabel/runs/${runId}`, { headers: ownerHeaders() })
    selectedDetail.value = detail
    activeRunId.value = runId
    if (detail.logs?.length) {
      logs.value = detail.logs.map(item => ({
        ...item,
        msg: item.msg || String(item.type || ''),
        time: item.time || '',
      }))
      rebuildStepsFromLogs(detail.logs)
    }
    if (detail.status === 'running' && detail.owned_by_client && !eventSource) {
      connectStream(runId)
    }
  } catch (error) {
    pushLog({ type: 'log', level: 'error', msg: `详情加载失败: ${messageOf(error)}` })
  }
}

async function loadShadowReview(runId: string, capability = ''): Promise<void> {
  try {
    let token = capability
    if (!token) {
      const invite = await apiJson<{ review_token: string }>(`/prelabel/runs/${encodeURIComponent(runId)}/review/invites`, {
        method: 'POST', headers: ownerHeaders(), body: { owner_token: clientToken },
      })
      token = invite.review_token
    }
    const review = await apiJson<ReviewPayload>(`/prelabel/runs/${encodeURIComponent(runId)}/review?${new URLSearchParams({ review_token: token })}`)
    reviewRunId.value = runId
    reviewToken.value = token
    reviewSamples.value = review.samples || []
    reviewIndex.value = 0
    reviewAnswers.value = {}
    reviewDecision.value = ''
    reviewReveal.value = ''
    reviewTaskLinks.value = {}
    reviewOpen.value = true
  } catch (error) {
    pushLog({ type: 'log', level: 'error', msg: `加载匿名盲评失败: ${messageOf(error)}` })
  }
}

function reviewAssetUrl(side: 'X' | 'Y'): string {
  if (!reviewCurrent.value || !reviewRunId.value) return ''
  return `/prelabel/runs/${encodeURIComponent(reviewRunId.value)}/review/assets/${encodeURIComponent(reviewCurrent.value.sample_id)}/${side}?${new URLSearchParams({ review_token: reviewToken.value })}`
}

async function submitShadowReview(): Promise<void> {
  if (!reviewRunId.value || !reviewComplete.value) return
  reviewSubmitting.value = true
  try {
    await apiJson<{ ok: boolean }>(`/prelabel/runs/${encodeURIComponent(reviewRunId.value)}/review`, {
      method: 'POST',
      body: { review_token: reviewToken.value, answers: reviewAnswers.value },
    })
    reviewDecision.value = '盲评已提交；结果将在所有者完成揭示后公布。'
  } catch (error) {
    pushLog({ type: 'log', level: 'error', msg: `提交盲评失败: ${messageOf(error)}` })
  } finally {
    reviewSubmitting.value = false
  }
}

async function revealShadowReview(): Promise<void> {
  if (!reviewRunId.value) return
  reviewRevealing.value = true
  try {
    const data = await apiJson<{ allowed: boolean; decision: { status: string }; mapping: Record<string, { X: string; Y: string }>; task_links: Record<string, string> }>(`/prelabel/runs/${encodeURIComponent(reviewRunId.value)}/review/reveal`, {
      method: 'POST', headers: ownerHeaders(), body: { owner_token: clientToken },
    })
    reviewReveal.value = `已揭示：${reviewDecisionText(data.decision)}。X/Y 映射已在所有者视图解锁。`
    reviewTaskLinks.value = data.task_links || {}
  } catch (error) {
    pushLog({ type: 'log', level: 'warn', msg: `暂不能揭示结果: ${messageOf(error)}` })
  } finally {
    reviewRevealing.value = false
  }
}

function reviewDecisionText(decision: { status: string; valid_votes?: number }): string {
  const labels: Record<string, string> = { candidate_wins: '候选方案胜出', baseline_wins: '基线方案胜出', no_decision: '无结论', pending: '评审进行中' }
  return `${labels[decision.status] || decision.status}（有效判断 ${decision.valid_votes ?? 0}）`
}

function selectText(event: FocusEvent): void {
  ;(event.target as HTMLInputElement | null)?.select()
}

async function cancelRun(run: RunRecord): Promise<void> {
  if (!run.owned_by_client) return
  try {
    const data = await apiJson<{ ok: boolean; msg: string }>(`/prelabel/runs/${run.run_id}/cancel`, {
      method: 'POST',
      headers: ownerHeaders(),
      body: { token: clientToken },
    })
    pushLog({ type: 'log', level: 'warn', msg: data.msg || '已请求停止' })
    await loadRuns()
  } catch (error) {
    pushLog({ type: 'log', level: 'error', msg: `停止失败: ${messageOf(error)}` })
  }
}

async function deleteRun(run: RunRecord): Promise<void> {
  try {
    await apiJson<{ ok: boolean }>(`/prelabel/runs/${run.run_id}`, {
      method: 'DELETE',
      headers: ownerHeaders(),
    })
    if (activeRunId.value === run.run_id) {
      activeRunId.value = ''
      selectedDetail.value = null
    }
    await loadRuns()
  } catch (error) {
    pushLog({ type: 'log', level: 'error', msg: `删除失败: ${messageOf(error)}` })
  }
}

async function loadContainerStatus(): Promise<void> {
  statusLoading.value = true
  try {
    containerStatus.value = await apiJson<ContainerStatus>('/prelabel/container-status')
  } catch (error) {
    containerStatus.value = { container_status: 'unknown', docker_error: messageOf(error), gpu_ok: false }
  } finally {
    statusLoading.value = false
  }
}

async function restartContainer(): Promise<void> {
  restarting.value = true
  try {
    const data = await apiJson<{ ok: boolean; message: string }>('/prelabel/restart-container?mode=manual', { method: 'POST' })
    pushLog({ type: 'log', level: data.ok ? 'info' : 'error', msg: data.message || '容器重启完成' })
    await loadContainerStatus()
  } catch (error) {
    pushLog({ type: 'log', level: 'error', msg: `容器重启失败: ${messageOf(error)}` })
  } finally {
    restarting.value = false
  }
}

function makeSteps(): StepItem[] {
  return [
    { step: 1, label: '上传 CVAT', status: 'pending', msg: '' },
    { step: 2, label: 'AI 预标注', status: 'pending', msg: '' },
    { step: 3, label: '标签转换', status: 'pending', msg: '' },
    { step: 4, label: '导入标注', status: 'pending', msg: '' },
    { step: 5, label: '分配任务', status: 'pending', msg: '' },
  ]
}

function resetSteps(skipSteps: number[] = []): void {
  steps.value = makeSteps()
  for (const step of skipSteps) updateStep(step, 'skipped', '启动时跳过')
}

function updateStep(step: unknown, status: StepStatus, msg?: unknown): void {
  const stepNumber = Number(step)
  const target = steps.value.find(item => item.step === stepNumber)
  if (!target) return
  target.status = status
  target.msg = typeof msg === 'string' ? msg : ''
}

function rebuildStepsFromLogs(items: StreamEvent[]): void {
  resetSteps()
  for (const item of items) {
    if (item.type === 'step_start') updateStep(item.step, 'active', item.msg)
    if (item.type === 'step_done') updateStep(item.step, item.status === 'success' ? 'done' : 'failed', item.msg)
    if (item.type === 'step_skip') updateStep(item.step, 'skipped', item.msg)
  }
}

function hasSource(): boolean {
  if (sourceMode.value === 'server') return serverDirs.value.some(item => item.trim())
  return Boolean(uploadId.value || selectedFiles.value.length)
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function findResultLink(result: unknown): string {
  if (Array.isArray(result)) {
    const item = result.find(entry => entry && typeof entry === 'object' && 'cvat_url' in entry) as { cvat_url?: string } | undefined
    return item?.cvat_url || ''
  }
  if (result && typeof result === 'object' && 'cvat_url' in result) {
    return String((result as { cvat_url?: unknown }).cvat_url || '')
  }
  return ''
}
</script>

<style scoped>
.prelabel-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: #111827;
  color: #d7dee9;
  font-size: 12px;
  overflow: hidden;
}

.prelabel-toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 7px 14px;
  background: #0b1018;
  border-bottom: 1px solid #223044;
}

.prelabel-token,
.prelabel-container,
.prelabel-actions,
.upload-line,
.browser-bar,
.panel-head,
.run-top,
.run-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.prelabel-token span,
.band-title,
.panel-head {
  color: #7dd3fc;
}

.prelabel-token code {
  color: #9ca3af;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.prelabel-main {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(360px, 440px) minmax(0, 1fr);
}

.shadow-review {
  margin: 10px 14px;
  border: 1px solid #2563eb;
  border-radius: 6px;
  background: #080f1f;
  overflow: hidden;
}

.review-pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  padding: 10px;
}

.review-pair figure { margin: 0; min-width: 0; }
.review-pair figcaption { padding: 4px 0; color: #7dd3fc; text-align: center; font-weight: 700; }
.review-pair img { display: block; width: 100%; max-height: 360px; object-fit: contain; background: #020617; border: 1px solid #334155; }
.review-actions { display: flex; flex-wrap: wrap; gap: 7px; padding: 0 10px 10px; }
.review-actions .selected { border-color: #38bdf8; color: #e0f2fe; background: #075985; }
.review-decision { margin: 0 10px 10px; color: #bae6fd; }
.review-share { display: flex; gap: 8px; align-items: center; margin: 0 10px 10px; color: #94a3b8; }
.review-share input { flex: 1; min-width: 0; padding: 5px; color: #cbd5e1; background: #020617; border: 1px solid #334155; }

.prelabel-config,
.prelabel-runtime {
  min-height: 0;
  overflow: auto;
}

.prelabel-config {
  border-right: 1px solid #223044;
  background: #111827;
}

.prelabel-runtime {
  display: flex;
  flex-direction: column;
  background: #0f172a;
}

.prelabel-band {
  padding: 10px 14px;
  border-bottom: 1px solid #223044;
}

.band-title {
  margin-bottom: 8px;
  font-size: 11px;
}

.server-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 8px;
}

.server-row,
.dir-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.server-row {
  display: grid;
  grid-template-columns: minmax(92px, auto) minmax(120px, 1fr) 74px minmax(112px, 0.7fr) minmax(112px, 0.7fr) auto;
  padding: 5px;
  background: #0b1220;
  border: 1px solid #1f2a3b;
  border-radius: 4px;
}

.server-row.active {
  border-color: #38bdf8;
}

.radio-row,
.check-row,
.form-grid label {
  display: flex;
  align-items: center;
  gap: 6px;
}

.radio-row {
  min-width: 94px;
  color: #cbd5e1;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.form-grid label {
  flex-direction: column;
  align-items: stretch;
  color: #94a3b8;
}

.grid-button {
  align-self: end;
}

.text-input,
.small-input,
.select-input,
.path-input {
  min-width: 0;
  background: #172033;
  border: 1px solid #2c3a50;
  border-radius: 4px;
  color: #e5edf8;
  padding: 6px 8px;
  font-size: 12px;
}

.text-input:focus,
.small-input:focus,
.select-input:focus,
.path-input:focus {
  outline: none;
  border-color: #38bdf8;
}

.host-input {
  width: 100%;
}

.port-input {
  width: 74px;
}

.user-input,
.password-input {
  width: 100%;
}

.segmented {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  background: #0b1220;
  border: 1px solid #1f2a3b;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 8px;
}

.segmented button {
  border: 0;
  border-right: 1px solid #1f2a3b;
  background: transparent;
  color: #94a3b8;
  padding: 7px 4px;
  cursor: pointer;
}

.segmented button:last-child {
  border-right: 0;
}

.segmented button.active {
  background: #164e63;
  color: #e0f2fe;
}

.source-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.path-input {
  flex: 1;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.file-input {
  width: 100%;
  color: #cbd5e1;
  background: #0b1220;
  border: 1px dashed #334155;
  border-radius: 4px;
  padding: 10px;
}

.prelabel-btn,
.icon-btn,
.mini-btn {
  border: 1px solid #2563eb;
  background: #1d4ed8;
  color: #eff6ff;
  border-radius: 4px;
  cursor: pointer;
  white-space: nowrap;
}

.prelabel-btn {
  padding: 6px 10px;
  font-size: 12px;
}

.prelabel-btn.primary {
  background: #15803d;
  border-color: #16a34a;
}

.prelabel-btn.ghost,
.mini-btn {
  background: #172033;
  border-color: #334155;
  color: #cbd5e1;
}

.prelabel-btn.warn {
  background: #713f12;
  border-color: #a16207;
}

.prelabel-btn.danger,
.mini-btn.danger {
  background: #7f1d1d;
  border-color: #dc2626;
}

.prelabel-btn:disabled,
.icon-btn:disabled,
.mini-btn:disabled {
  opacity: .45;
  cursor: not-allowed;
}

.icon-btn {
  width: 28px;
  height: 28px;
  background: #263244;
  border-color: #3c4a60;
  font-size: 18px;
  line-height: 1;
}

.mini-btn {
  padding: 3px 7px;
  font-size: 11px;
}

.upload-summary,
.run-state,
.inline-empty,
.detail-strip {
  color: #94a3b8;
}

.upload-summary {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-track {
  position: relative;
  height: 20px;
  overflow: hidden;
  border: 1px solid #334155;
  border-radius: 4px;
  background: #0b1220;
}

.progress-fill {
  height: 100%;
  background: #0891b2;
  transition: width .2s ease;
}

.progress-track span {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #f8fafc;
  font-size: 11px;
}

.browser-panel {
  border: 1px solid #223044;
  border-radius: 4px;
  background: #0b1220;
  padding: 8px;
}

.browser-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 6px;
  max-height: 180px;
  overflow: auto;
  margin-top: 8px;
}

.browser-item {
  min-width: 0;
  border: 1px solid #263244;
  background: #111827;
  color: #cbd5e1;
  border-radius: 4px;
  padding: 6px 8px;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.prelabel-actions {
  position: sticky;
  bottom: 0;
  padding: 10px 14px;
  background: #0b1018;
  border-top: 1px solid #223044;
}

.status-pill,
.gpu-pill {
  border: 1px solid #334155;
  border-radius: 4px;
  padding: 4px 7px;
  color: #cbd5e1;
  background: #172033;
}

.status-pill.ok,
.gpu-pill.ok {
  color: #bbf7d0;
  border-color: #166534;
  background: #052e16;
}

.status-pill.bad {
  color: #fecaca;
  border-color: #991b1b;
  background: #450a0a;
}

.timeline {
  flex-shrink: 0;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid #223044;
}

.timeline-step {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 8px;
  border: 1px solid #263244;
  border-radius: 4px;
  background: #111827;
}

.step-index {
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #263244;
  color: #cbd5e1;
}

.step-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.step-text span,
.step-text small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-text small {
  color: #94a3b8;
}

.timeline-step.active {
  border-color: #38bdf8;
}

.timeline-step.active .step-index {
  background: #0369a1;
}

.timeline-step.done .step-index {
  background: #15803d;
}

.timeline-step.skipped .step-index {
  background: #854d0e;
}

.timeline-step.failed .step-index {
  background: #b91c1c;
}

.runtime-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
}

.log-panel,
.history-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #223044;
}

.history-panel {
  border-right: 0;
}

.panel-head {
  flex-shrink: 0;
  justify-content: space-between;
  padding: 8px 10px;
  background: #0b1018;
  border-bottom: 1px solid #223044;
}

.log-box,
.run-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.log-box {
  padding: 8px 10px;
  background: #080c14;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.log-line {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 8px;
  padding: 2px 0;
  color: #cbd5e1;
}

.log-line.error,
.log-line.failed {
  color: #fca5a5;
}

.log-line.warn,
.log-line.cancelled {
  color: #fde68a;
}

.log-line.success,
.log-line.info {
  color: #a7f3d0;
}

.log-time {
  color: #64748b;
}

.log-msg {
  min-width: 0;
  overflow-wrap: anywhere;
}

.run-list {
  padding: 8px;
}

.run-item {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: 7px;
  padding: 8px;
  border: 1px solid #263244;
  border-radius: 4px;
  background: #111827;
  color: #cbd5e1;
  text-align: left;
  cursor: pointer;
}

.run-item.active {
  border-color: #38bdf8;
}

.run-top {
  justify-content: space-between;
}

.run-top strong,
.run-meta {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-top em {
  flex-shrink: 0;
  font-style: normal;
  color: #93c5fd;
}

.run-top em.success {
  color: #86efac;
}

.run-top em.failed,
.run-top em.cancelled {
  color: #fca5a5;
}

.run-meta {
  color: #94a3b8;
  font-size: 11px;
}

.run-actions {
  justify-content: flex-end;
}

.detail-strip {
  flex-shrink: 0;
  display: flex;
  gap: 14px;
  padding: 7px 14px;
  border-top: 1px solid #223044;
  background: #0b1018;
  overflow: hidden;
}

.detail-strip span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 1100px) {
  .prelabel-main {
    grid-template-columns: 1fr;
  }

  .prelabel-config {
    border-right: 0;
    max-height: 52vh;
  }

  .runtime-grid {
    grid-template-columns: 1fr;
  }

  .history-panel {
    min-height: 240px;
    border-top: 1px solid #223044;
  }
}

@media (max-width: 760px) {
  .prelabel-toolbar,
  .prelabel-container,
  .prelabel-actions,
  .browser-bar {
    align-items: stretch;
    flex-direction: column;
  }

  .form-grid,
  .timeline {
    grid-template-columns: 1fr;
  }

  .server-row,
  .dir-row,
  .upload-line {
    align-items: stretch;
    flex-direction: column;
  }

  .radio-row {
    min-width: 0;
  }

  .host-input,
  .port-input,
  .user-input,
  .password-input {
    width: 100%;
  }

  .server-row {
    grid-template-columns: 1fr;
  }
}
</style>
