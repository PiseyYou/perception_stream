<template>
  <div class="lf-root">
    <!-- ===== Section 1: SSH 日志拉取 ===== -->
    <div class="lf-section">
      <div class="lf-section-title">📡 远程日志拉取</div>
      <div class="lf-row">
        <label class="lf-label">SN末尾4位:</label>
        <input v-model="snLast4" class="lf-input-sn" placeholder="0015" maxlength="4" @input="onSnInput" />
        <label class="lf-label">端口号:</label>
        <input v-model.number="port" type="number" class="lf-input-sm" placeholder="10123" />
        <label class="lf-label">日志保存目录:</label>
        <input v-model="localSaveDir" class="lf-input" placeholder="自动生成，如 data/log_debug/0123/20260331/" />
        <button class="lf-btn blue" :disabled="pullLoading || !port" @click="doPullLogs">
          {{ pullLoading ? '⏳ 拉取中...' : '⬇ 拉取日志' }}
        </button>
        <button v-if="pullLoading" class="lf-btn red" @click="stopPull">■ 停止</button>
      </div>
      <div class="lf-row lf-filter-row">
        <label class="lf-label">拉取模块:</label>
        <input v-model="moduleKeyword" class="lf-input-module" placeholder="stereo_perception" />
        <span class="lf-transfer-hint">只拉取文件名包含该关键词的日志，留空则拉取全部日志</span>
      </div>
      <div class="lf-row lf-transfer-row">
        <label class="lf-label">一键转存:</label>
        <label class="lf-sub-label">目标IP</label>
        <input v-model="logTransferHost" class="lf-input-host" placeholder="192.168.55.239" />
        <button class="lf-btn purple" :disabled="transferLoading || pullLoading || !canTransferLogs" @click="transferLogsToDebugHost">
          {{ transferLoading ? '⏳ 转存中...' : '⇪ 一键转存' }}
        </button>
        <span class="lf-transfer-hint">/home/youfeng/debug/log/{{ transferPortSuffix }}</span>
      </div>
      <div v-if="pullLoading" class="lf-progress-bar">
        <div class="lf-progress-fill" :style="{ width: (pullProgress || 0) + '%' }">{{ pullProgress || 0 }}%</div>
      </div>
      <div v-if="pullStatus" class="lf-status" :class="{ error: pullError }">{{ pullStatus }}</div>
      <div v-if="transferStatus" class="lf-status" :class="{ error: transferError }">{{ transferStatus }}</div>
      <div v-if="pullLogLines.length" class="lf-terminal">
        <div v-for="(line, i) in pullLogLines" :key="i" class="lf-log-line" :class="{ 'log-err': line.startsWith('ERROR') || line.startsWith('❌') }">{{ line }}</div>
      </div>
    </div>

    <!-- ===== Section 2: 离线日志分析 ===== -->
    <div class="lf-section">
      <div class="lf-section-title">📂 离线日志 & 避障图片</div>
      <div class="lf-row">
        <label class="lf-label">日志文件夹:</label>
        <label class="lf-sub-label">端口号</label>
        <input v-model="logPortSuffix" class="lf-input-sn" placeholder="0286" maxlength="4" inputmode="numeric" />
        <label class="lf-sub-label">日期</label>
        <input v-model="logDate" class="lf-input-date" placeholder="20260513" maxlength="8" inputmode="numeric" />
        <label class="lf-label">避障图片文件夹:</label>
        <label class="lf-sub-label">端口号</label>
        <input v-model="imgPortSuffix" class="lf-input-sn" placeholder="0286" maxlength="4" inputmode="numeric" />
        <label class="lf-sub-label">日期</label>
        <input v-model="imgDate" class="lf-input-date" placeholder="20260513" maxlength="8" inputmode="numeric" />
        <button class="lf-btn green" :disabled="analyzeLoading || !canAnalyze" @click="analyzeAvoiding">
          {{ analyzeLoading ? '⏳ 分析中...' : '🔍 分析避障' }}
        </button>
      </div>
      <div v-if="analyzeLoading && analyzeProgress" class="lf-progress-info">
        <div class="lf-progress-text">{{ analyzeProgress }}</div>
        <div v-if="analyzePercent > 0" class="lf-progress-bar">
          <div class="lf-progress-fill" :style="{ width: analyzePercent + '%' }">{{ analyzePercent }}%</div>
        </div>
      </div>
      <div v-if="analyzeStatus" class="lf-status" :class="{ error: analyzeError }">{{ analyzeStatus }}</div>
    </div>

    <!-- ===== Section 3: 分析结果 ===== -->
    <div v-if="analysisResult" class="lf-section lf-report-section lf-fullscreen">
      <div class="lf-report-head">
        <div>
          <div class="lf-section-title lf-section-title-compact">📊 避障原因分析报告</div>
          <div class="lf-section-caption">三列并排对照 robot_decision、nav 和 stereo_perception，每列都会明确说明是否有数据。</div>
        </div>
        <div class="lf-report-actions">
          <button class="lf-chip-btn" :class="{ active: viewMode === 'columns' }" @click="viewMode = 'columns'">三列对照</button>
          <button class="lf-chip-btn" :class="{ active: viewMode === 'timeline' }" @click="viewMode = 'timeline'">时间戳排序</button>
        </div>
      </div>

      <div class="lf-summary-bar">
        <span class="lf-badge">
          <span class="lf-badge-label">避障事件</span>
          <b>{{ analysisResult.avoiding_count }}</b>
        </span>
        <span class="lf-badge">
          <span class="lf-badge-label">关联图片</span>
          <b>{{ analysisResult.image_count }}</b>
        </span>
        <span class="lf-badge">
          <span class="lf-badge-label">时间范围</span>
          <b>{{ analysisResult.time_range || '未提取到有效时间范围' }}</b>
        </span>
      </div>

      <div v-if="viewMode === 'columns'" class="lf-analysis-grid">
        <section
          v-for="card in analysisCards"
          :key="card.key"
          class="lf-log-card"
          :class="`tone-${card.tone}`"
        >
          <div class="lf-log-card-head clickable" @click="toggleCardFocus(card.key)">
            <div class="lf-log-card-title-group">
              <span class="lf-card-icon">{{ card.icon }}</span>
              <div>
                <div class="lf-card-title">{{ card.title }}</div>
                <div class="lf-card-subtitle">{{ card.subtitle }}</div>
              </div>
            </div>
            <div class="lf-card-actions">
              <div class="lf-card-count">{{ card.total }}</div>
              <button class="lf-inline-icon-btn" @click.stop="toggleCardFocus(card.key)">放大</button>
            </div>
          </div>

          <div v-if="card.total" class="lf-log-terminal">
            <div v-for="(row, i) in card.rows" :key="`${card.key}-${i}`" class="lf-log-row">
              <span class="lf-log-ts">{{ row.ts }}</span>
              <span class="lf-log-text">{{ row.text }}</span>
            </div>
            <div v-if="card.truncated" class="lf-log-truncation">
              仅展示前 {{ card.rows.length }} 条，剩余 {{ card.total - card.rows.length }} 条未展开。
            </div>
          </div>

          <div v-else class="lf-log-empty-state">
            <div class="lf-empty-title">{{ card.emptyTitle }}</div>
            <div class="lf-empty-hint">{{ card.emptyHint }}</div>
          </div>
        </section>
      </div>

      <div v-else class="lf-timeline-card">
        <div class="lf-log-card-head clickable" @click="timelineOverlayOpen = true">
          <div class="lf-log-card-title-group">
            <span class="lf-card-icon">⏱</span>
            <div>
              <div class="lf-card-title">时间戳交错视图</div>
              <div class="lf-card-subtitle">不同来源日志按时间顺序混排显示，同一时间下按 decision → nav → stereo 排序。</div>
            </div>
          </div>
          <div class="lf-card-actions">
            <div class="lf-card-count">{{ mergedTimelineRows.length }}</div>
            <button class="lf-inline-icon-btn" @click.stop="timelineOverlayOpen = true">放大</button>
          </div>
        </div>

        <div v-if="mergedTimelineRows.length" class="lf-log-terminal lf-timeline-terminal">
          <div v-for="(row, i) in mergedTimelineRows" :key="`timeline-${i}`" class="lf-timeline-row" :class="`tone-${row.sourceTone}`">
            <span class="lf-log-ts">{{ row.ts }}</span>
            <span class="lf-timeline-source">{{ row.sourceLabel }}</span>
            <span class="lf-log-text">{{ row.text }}</span>
          </div>
          <div v-if="timelineTruncated" class="lf-log-truncation">
            仅展示前 {{ mergedTimelineRows.length }} 条混排结果，剩余 {{ mergedTimelineTotal - mergedTimelineRows.length }} 条未展开。
          </div>
        </div>

        <div v-else class="lf-log-empty-state">
          <div class="lf-empty-title">没有可按时间戳混排的日志</div>
          <div class="lf-empty-hint">当前三类日志都为空，或所有日志都未提取到可展示的时间戳文本。</div>
        </div>
      </div>

      <div class="lf-report-secondary">
        <div class="lf-media-card">
          <div class="lf-media-card-head">
            <div>
              <div class="lf-card-title">🖼 避障图片</div>
              <div class="lf-card-subtitle">关联图片 {{ analysisResult.images.length }} 张</div>
            </div>
          </div>

          <template v-if="analysisResult.images.length">
            <div class="lf-thumb-strip">
              <div
                v-for="img in analysisResult.images"
                :key="img"
                class="lf-thumb-item"
                :class="{ active: selectedImg === img }"
                @click="selectedImg = img"
              >
                <img :src="localFileUrl(img)" loading="lazy" />
                <div class="lf-thumb-name">{{ img.split('/').pop() }}</div>
              </div>
            </div>
            <div v-if="selectedImg" class="lf-img-detail">
              <img :src="localFileUrl(selectedImg)" class="lf-img-full" @click="lightboxSrc = localFileUrl(selectedImg)" />
              <div class="lf-img-name">{{ selectedImg.split('/').pop() }}</div>
            </div>
          </template>

          <div v-else class="lf-log-empty-state">
            <div class="lf-empty-title">当前没有可展示的避障图片</div>
            <div class="lf-empty-hint">请确认图片目录中存在命名规范正确的 JPG/PNG 文件。</div>
          </div>
        </div>

        <div class="lf-conclusion">
          <div class="lf-media-card-head">
            <div>
              <div class="lf-card-title">🧠 AI 分析意见</div>
              <div class="lf-card-subtitle">基于三列日志与图片时间窗口生成</div>
            </div>
          </div>
          <div class="lf-conclusion-body">
            <div v-if="analysisLoading" class="lf-loading">正在生成分析意见...</div>
            <div v-else-if="analysisResult.conclusion" class="lf-conclusion-text" v-html="formatConclusion(analysisResult.conclusion)"></div>
            <div v-else class="lf-log-empty-state">
              <div class="lf-empty-title">当前没有生成分析意见</div>
              <div class="lf-empty-hint">说明日志信息不足，或本次分析只提取到了部分原始数据。</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Lightbox -->
    <div v-if="lightboxSrc" class="lf-lightbox" @click="lightboxSrc = ''">
      <span class="lf-lb-close" @click.stop="lightboxSrc = ''">✕</span>
      <img :src="lightboxSrc" @click.stop />
    </div>

    <div v-if="focusedAnalysisCard" class="lf-panel-overlay" @click="focusedCardKey = null">
      <div class="lf-panel-dialog" :class="`tone-${focusedAnalysisCard.tone}`" @click.stop>
        <div class="lf-panel-head">
          <div class="lf-log-card-title-group">
            <span class="lf-card-icon">{{ focusedAnalysisCard.icon }}</span>
            <div>
              <div class="lf-card-title">{{ focusedAnalysisCard.title }}</div>
              <div class="lf-card-subtitle">{{ focusedAnalysisCard.subtitle }}</div>
            </div>
          </div>
          <div class="lf-card-actions">
            <div class="lf-card-count">{{ focusedAnalysisCard.total }}</div>
            <button class="lf-inline-icon-btn" @click="focusedCardKey = null">关闭</button>
          </div>
        </div>
        <div v-if="focusedAnalysisCard.total" class="lf-log-terminal expanded overlay">
          <div v-for="(row, i) in focusedAnalysisCard.fullRows" :key="`focused-${focusedAnalysisCard.key}-${i}`" class="lf-log-row">
            <span class="lf-log-ts">{{ row.ts }}</span>
            <span class="lf-log-text">{{ row.text }}</span>
          </div>
        </div>
        <div v-else class="lf-log-empty-state overlay">
          <div class="lf-empty-title">{{ focusedAnalysisCard.emptyTitle }}</div>
          <div class="lf-empty-hint">{{ focusedAnalysisCard.emptyHint }}</div>
        </div>
      </div>
    </div>

    <div v-if="timelineOverlayOpen" class="lf-panel-overlay" @click="timelineOverlayOpen = false">
      <div class="lf-panel-dialog tone-nav" @click.stop>
        <div class="lf-panel-head">
          <div class="lf-log-card-title-group">
            <span class="lf-card-icon">⏱</span>
            <div>
              <div class="lf-card-title">时间戳交错视图</div>
              <div class="lf-card-subtitle">不同来源日志按时间顺序混排显示，同一时间下按 decision → nav → stereo 排序。</div>
            </div>
          </div>
          <div class="lf-card-actions">
            <div class="lf-card-count">{{ mergedTimelineTotal }}</div>
            <button class="lf-inline-icon-btn" @click="timelineOverlayOpen = false">关闭</button>
          </div>
        </div>
        <div v-if="mergedTimelineTotal" class="lf-log-terminal expanded overlay">
          <div v-for="(row, i) in mergedTimelineAllRows" :key="`overlay-timeline-${i}`" class="lf-timeline-row" :class="`tone-${row.sourceTone}`">
            <span class="lf-log-ts">{{ row.ts }}</span>
            <span class="lf-timeline-source">{{ row.sourceLabel }}</span>
            <span class="lf-log-text">{{ row.text }}</span>
          </div>
        </div>
        <div v-else class="lf-log-empty-state overlay">
          <div class="lf-empty-title">没有可按时间戳混排的日志</div>
          <div class="lf-empty-hint">当前三类日志都为空，或所有日志都未提取到可展示的时间戳文本。</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { readAnalysisCache, writeAnalysisCache } from '../utils/analysisCache'
import { buildMergedTimeline, type AnalysisTimelineRow } from '../utils/analysisTimeline'
import { consumeSseJsonChunk } from '../utils/sseJsonStream'

function getPreviousDateString(now = new Date()): string {
  const previous = new Date(now)
  previous.setDate(previous.getDate() - 1)
  return previous.getFullYear().toString() +
    String(previous.getMonth() + 1).padStart(2, '0') +
    String(previous.getDate()).padStart(2, '0')
}

function cleanDigits(value: string, maxLength: number): string {
  return value.replace(/\D/g, '').slice(0, maxLength)
}

function buildAvoidingLogDir(portSuffix: string, date: string): string {
  return `data/log_debug/${cleanDigits(portSuffix, 4)}/${cleanDigits(date, 8)}/ros2_log`
}

function buildAvoidingImageDir(portSuffix: string, date: string): string {
  return `data/stereo_debug/${cleanDigits(portSuffix, 4)}/${cleanDigits(date, 8)}`
}

interface AnalysisRow {
  ts: string
  text: string
}

interface AnalysisResultData {
  avoiding_count: number
  image_count: number
  time_range: string
  images: string[]
  conclusion: string
  categories: {
    robot_decision: AnalysisRow[]
    nav: AnalysisRow[]
    stereo: AnalysisRow[]
  }
}

const MAX_VISIBLE_LOG_ROWS = 240
const MAX_VISIBLE_TIMELINE_ROWS = 600

const DEFAULT_PORT = 10016

function defaultSaveDir(p: number): string {
  const portSuffix = String(p).slice(-4)
  const d = new Date()
  const dateStr = d.getFullYear().toString() +
    String(d.getMonth() + 1).padStart(2, '0') +
    String(d.getDate()).padStart(2, '0')
  return `data/log_debug/${portSuffix}/${dateStr}`
}

const snLast4 = ref('0016')
const port = ref<number | null>(DEFAULT_PORT)
const localSaveDir = ref(defaultSaveDir(DEFAULT_PORT))
const moduleKeyword = ref('stereo_perception')

// 当输入SN末尾4位时，自动拼接路径和端口号
function onSnInput() {
  const sn = snLast4.value.trim()
  if (sn.length === 4 && /^\d{4}$/.test(sn)) {
    const today = new Date().toISOString().slice(0, 10).replace(/-/g, '')
    localSaveDir.value = `data/log_debug/${sn}/${today}`
    port.value = parseInt('1' + sn)
  }
}
const pullLoading = ref(false)
const pullError = ref(false)
const pullStatus = ref('')
const pullLogLines = ref<string[]>([])
const pullProgress = ref(0)
let pullAbort: AbortController | null = null
const logTransferHost = ref('192.168.55.239')
const transferLoading = ref(false)
const transferError = ref(false)
const transferStatus = ref('')
const transferPortSuffix = computed(() => String(port.value || '').slice(-4) || '----')
const canTransferLogs = computed(() =>
  Boolean(port.value) &&
  cleanDigits(transferPortSuffix.value, 4).length === 4 &&
  Boolean(localSaveDir.value.trim()) &&
  Boolean(logTransferHost.value.trim()),
)

const defaultAnalysisDate = getPreviousDateString()
const logPortSuffix = ref('0286')
const logDate = ref(defaultAnalysisDate)
const imgPortSuffix = ref('0286')
const imgDate = ref(defaultAnalysisDate)
const logDir = computed(() => buildAvoidingLogDir(logPortSuffix.value, logDate.value))
const imgDir = computed(() => buildAvoidingImageDir(imgPortSuffix.value, imgDate.value))
const canAnalyze = computed(() =>
  cleanDigits(logPortSuffix.value, 4).length === 4 &&
  cleanDigits(logDate.value, 8).length === 8 &&
  cleanDigits(imgPortSuffix.value, 4).length === 4 &&
  cleanDigits(imgDate.value, 8).length === 8,
)
const analyzeLoading = ref(false)
const analyzeError = ref(false)
const analyzeStatus = ref('')
const analyzeProgress = ref('')
const analyzePercent = ref(0)

const analysisResult = ref<AnalysisResultData | null>(null)
const analysisLoading = ref(false)
const selectedImg = ref('')
const lightboxSrc = ref('')
const viewMode = ref<'columns' | 'timeline'>('columns')
const focusedCardKey = ref<'robot_decision' | 'nav' | 'stereo' | null>(null)
const timelineOverlayOpen = ref(false)

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

function normalizeAnalysisResult(data: any): AnalysisResultData {
  return {
    avoiding_count: Number(data?.avoiding_count || 0),
    image_count: Number(data?.image_count || 0),
    time_range: String(data?.time_range || ''),
    images: Array.isArray(data?.images) ? data.images : [],
    conclusion: String(data?.conclusion || ''),
    categories: {
      robot_decision: Array.isArray(data?.categories?.robot_decision) ? data.categories.robot_decision : [],
      nav: Array.isArray(data?.categories?.nav) ? data.categories.nav : [],
      stereo: Array.isArray(data?.categories?.stereo) ? data.categories.stereo : [],
    },
  }
}

const analysisCards = computed(() => {
  const result = analysisResult.value
  if (!result) return []

  return [
    {
      key: 'robot_decision',
      title: 'robot_decision',
      subtitle: 'AVOIDING 决策日志',
      icon: '🤖',
      tone: 'decision',
      total: result.categories.robot_decision.length,
      rows: result.categories.robot_decision.slice(0, MAX_VISIBLE_LOG_ROWS),
      truncated: result.categories.robot_decision.length > MAX_VISIBLE_LOG_ROWS,
      emptyTitle: '没有匹配到 AVOIDING 决策日志',
      emptyHint: '当前时间窗口内没有 robot_decision 的避障判定，或日志目录中不包含对应文件。',
    },
    {
      key: 'nav',
      title: 'nav',
      subtitle: '导航侧关联日志',
      icon: '🗺',
      tone: 'nav',
      total: result.categories.nav.length,
      rows: result.categories.nav.slice(0, MAX_VISIBLE_LOG_ROWS),
      truncated: result.categories.nav.length > MAX_VISIBLE_LOG_ROWS,
      emptyTitle: '没有匹配到 nav 日志',
      emptyHint: '当前路径下没有可关联的导航日志，或日志时间戳未落入本次分析窗口。',
    },
    {
      key: 'stereo',
      title: 'stereo_perception',
      subtitle: '感知侧关联日志',
      icon: '📷',
      tone: 'stereo',
      total: result.categories.stereo.length,
      rows: result.categories.stereo.slice(0, MAX_VISIBLE_LOG_ROWS),
      truncated: result.categories.stereo.length > MAX_VISIBLE_LOG_ROWS,
      emptyTitle: '没有匹配到 stereo_perception 日志',
      emptyHint: '如需查看感知侧信息，请确认日志目录中存在 stereo_perception 相关日志文件。',
    },
  ]
})

const mergedTimelineAllRows = computed<AnalysisTimelineRow[]>(() => {
  const result = analysisResult.value
  if (!result) return []
  return buildMergedTimeline(result.categories)
})

const mergedTimelineRows = computed(() => mergedTimelineAllRows.value.slice(0, MAX_VISIBLE_TIMELINE_ROWS))
const mergedTimelineTotal = computed(() => mergedTimelineAllRows.value.length)
const timelineTruncated = computed(() => mergedTimelineTotal.value > MAX_VISIBLE_TIMELINE_ROWS)
const focusedAnalysisCard = computed(() => {
  if (!focusedCardKey.value) return null
  const card = analysisCards.value.find((entry) => entry.key === focusedCardKey.value)
  if (!card || !analysisResult.value) return null
  return {
    ...card,
    fullRows: analysisResult.value.categories[card.key],
  }
})

function toggleCardFocus(key: 'robot_decision' | 'nav' | 'stereo') {
  focusedCardKey.value = focusedCardKey.value === key ? null : key
}

function hasRecoverableAnalysisResult(resultData: any) {
  return Boolean(
    resultData?.ok ||
    resultData?.images?.length ||
    resultData?.categories?.robot_decision?.length ||
    resultData?.categories?.nav?.length ||
    resultData?.categories?.stereo?.length ||
    resultData?.conclusion
  )
}

function applyAnalysisResult(resultData: any, cacheKey: string, statusPrefix = '✅ 分析完成') {
  const normalized = normalizeAnalysisResult(resultData)
  analysisResult.value = normalized
  selectedImg.value = normalized.images[0] || ''
  focusedCardKey.value = null
  console.log('[Cache] 保存分析结果到缓存，key:', cacheKey)
  const cacheMode = writeAnalysisCache(cacheKey, normalized)
  console.log('[Cache] 缓存已保存，模式:', cacheMode)
  return normalized
}

// Load default port from server config on mount
onMounted(async () => {
  try {
    const res = await fetch('/offline/config')
    const data = await res.json()
    if (data.ok && data.default_ports?.log_fetch) {
      port.value = data.default_ports.log_fetch
      localSaveDir.value = defaultSaveDir(data.default_ports.log_fetch)
    }
  } catch (e) {
    console.warn('Failed to load config:', e)
  }

  // 尝试从缓存恢复之前的分析结果
  const cacheKey = `${logDir.value}|${imgDir.value}`
  const cached = readAnalysisCache(cacheKey)
  if (cached?.kind === 'full') {
    const restored = normalizeAnalysisResult(cached.data)
    console.log('[Cache] 恢复缓存的分析结果:', restored.avoiding_count, '个避障事件')
    analysisResult.value = restored
    selectedImg.value = restored.images[0] || ''
    focusedCardKey.value = null
    analyzeStatus.value = `✅ 已加载缓存结果 (${restored.avoiding_count} 个避障事件)`
  } else if (cached?.kind === 'summary') {
    analyzeStatus.value = `ℹ️ 检测到历史分析摘要 (${cached.summary.avoiding_count} 个避障事件)，点击“分析避障”可重新加载完整日志`
  }
})

function localFileUrl(p: string) {
  return `/offline/local_file?path=${encodeURIComponent(p)}`
}

function formatConclusion(text: string): string {
  return text
    .replace(/\n/g, '<br/>')
    .replace(/\*\*(.*?)\*\*/g, '<b>$1</b>')
    .replace(/### (.*?)(<br\/?>|$)/g, '<h4>$1</h4>')
    .replace(/## (.*?)(<br\/?>|$)/g, '<h3>$1</h3>')
}

async function doPullLogs() {
  if (!port.value) {
    alert('请输入端口号')
    return
  }

  // 先检查本地文件是否存在
  const checkDir = localSaveDir.value.trim() || defaultSaveDir(port.value)
  pullStatus.value = '正在检查本地文件...'
  console.log('[doPullLogs] 检查目录:', checkDir)

  try {
    const checkRes = await fetch('/offline/check_local_logs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ local_dir: checkDir }),
    })

    if (!checkRes.ok) {
      console.error('[doPullLogs] 检查接口返回错误:', checkRes.status)
      pullStatus.value = `检查本地文件失败 (HTTP ${checkRes.status})，继续拉取...`
    } else {
      const checkData = await checkRes.json()
      console.log('[doPullLogs] 检查结果:', checkData)

      if (checkData.exists && checkData.file_count > 0) {
        // 本地文件已存在，询问是否重新拉取
        const shouldPull = confirm(`本地已存在 ${checkData.file_count} 个日志文件。\n是否重新拉取？\n\n点击"确定"重新拉取（断点续传）\n点击"取消"使用现有文件`)
        if (!shouldPull) {
          pullStatus.value = `✅ 使用现有日志: ${checkDir} (${checkData.file_count} 个文件)`
          localSaveDir.value = checkDir
          return
        }
      }
    }
  } catch (e) {
    console.error('[doPullLogs] 检查本地文件异常:', e)
    pullStatus.value = '检查本地文件失败，继续拉取...'
  }

  console.log('[doPullLogs] 开始拉取，端口:', port.value, '目录:', checkDir)
  pullLoading.value = true
  pullError.value = false
  pullStatus.value = ''
  pullLogLines.value = []
  pullProgress.value = 0
  pullAbort = new AbortController()

  try {
    const requestBody: any = {
      port: port.value,
      resume: true,
      module_keyword: moduleKeyword.value.trim(),
    }  // 启用断点续传
    if (localSaveDir.value && localSaveDir.value.trim()) {
      requestBody.local_save_dir = localSaveDir.value.trim()
    }
    const res = await fetch('/offline/pull_robot_logs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
      signal: pullAbort.signal,
    })

    if (!res.body) {
      throw new Error('No response body')
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    const handlePullPayloads = (payloadText: string) => {
      const parsed = consumeSseJsonChunk(buffer, payloadText)
      buffer = parsed.remainder

      for (const error of parsed.errors) {
        console.warn('[doPullLogs] 跳过无法解析的 SSE 数据:', error.message, error.payload.slice(0, 300))
      }

      for (const event of parsed.events) {
        const data = event as {
          done?: boolean
          ok?: boolean
          partial_success?: boolean
          local_dir?: string
          file_count?: number
          errors?: string[]
          error?: string
          log?: string
          percent?: number
        }

        if (data.done) {
          if (data.ok) {
            if (data.partial_success) {
              pullStatus.value = `⚠️ 部分成功: ${data.local_dir} (${data.file_count} 个文件，${data.errors?.length || 0} 个批次失败)`
              pullError.value = true
            } else {
              pullStatus.value = `✅ 日志已拉取到: ${data.local_dir} (${data.file_count} 个文件)`
            }
          } else {
            pullStatus.value = `❌ 拉取失败: ${data.error || '未能下载任何文件'}`
            if (data.errors && data.errors.length > 0) {
              pullStatus.value += ` - ${data.errors[0]}`
            }
            pullError.value = true
          }
          if (data.local_dir) {
            localSaveDir.value = data.local_dir
          }
          pullProgress.value = 100
          pullLoading.value = false
        } else {
          if (data.log) pullLogLines.value.push(data.log)
          if (data.percent !== undefined) pullProgress.value = data.percent
        }
      }
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      handlePullPayloads(decoder.decode(value, { stream: true }))
    }

    handlePullPayloads(`${decoder.decode()}\n\n`)
  } catch (e: any) {
    if (e.name !== 'AbortError') {
      pullError.value = true
      pullStatus.value = `❌ ${e.message}`
    }
  } finally {
    pullLoading.value = false
    pullAbort = null
  }
}

function stopPull() {
  pullAbort?.abort()
  pullLoading.value = false
  pullStatus.value = '已取消'
}

async function transferLogsToDebugHost() {
  if (!canTransferLogs.value || !port.value) {
    transferError.value = true
    transferStatus.value = '❌ 请先确认端口号、日志保存目录和目标 IP'
    return
  }

  transferLoading.value = true
  transferError.value = false
  transferStatus.value = ''

  try {
    const res = await fetch('/offline/transfer_logs_to_debug_host', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        port: port.value,
        local_dir: localSaveDir.value.trim(),
        host: logTransferHost.value.trim(),
      }),
    })
    const data = await readJsonResponse<any>(res, '一键转存')
    if (!res.ok || !data.ok) {
      throw new Error(data?.error || `HTTP ${res.status}`)
    }

    const warning = data.errors?.length ? `，${data.errors.length} 个警告` : ''
    transferStatus.value = `✅ 已转存到 ${data.remote_path} (${data.file_count || 0} 个文件${warning})`
  } catch (e: any) {
    transferError.value = true
    transferStatus.value = `❌ 转存失败: ${e.message || e}`
  } finally {
    transferLoading.value = false
  }
}

async function analyzeAvoiding() {
  if (!canAnalyze.value) return

  // 先检查是否有缓存的分析结果
  const cacheKey = `${logDir.value}|${imgDir.value}`
  console.log('[Cache] 检查缓存，key:', cacheKey)
  const cached = readAnalysisCache(cacheKey)
  console.log('[Cache] 缓存内容:', cached ? cached.kind : '不存在')

  if (cached?.kind === 'full') {
      const restored = normalizeAnalysisResult(cached.data)
      console.log('[Cache] 使用缓存结果:', restored.avoiding_count, '个避障事件')
      analyzeStatus.value = `✅ 使用缓存结果 (${restored.avoiding_count} 个避障事件)`
      analysisResult.value = restored
      selectedImg.value = restored.images[0] || ''
      focusedCardKey.value = null
      return
  }

  if (cached?.kind === 'summary') {
      console.log('[Cache] 仅命中摘要缓存，继续请求完整分析结果')
      analyzeStatus.value = `ℹ️ 已命中摘要缓存，正在重新加载完整分析结果...`
      selectedImg.value = ''
  }

  console.log('[Cache] 无缓存，开始重新分析')
  analyzeLoading.value = true
  analyzeError.value = false
  analyzeStatus.value = ''
  analyzeProgress.value = '正在初始化...'
  analyzePercent.value = 0
  analysisResult.value = null
  selectedImg.value = ''
  focusedCardKey.value = null
  let resultData: any = {
    categories: {
      robot_decision: [],
      nav: [],
      stereo: [],
    },
    images: [],
  }

  try {
    const res = await fetch('/offline/analyze_avoiding', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        log_dir: logDir.value,
        img_dir: imgDir.value,
      }),
    })

    if (!res.ok) {
      const errorText = await res.text().catch(() => '')
      throw new Error(`HTTP ${res.status}${errorText ? `: ${errorText.slice(0, 200)}` : ''}`)
    }

    if (!res.body) {
      throw new Error('No response body')
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let analysisDone = false

    const handleAnalyzePayloads = (payloadText: string) => {
      const parsed = consumeSseJsonChunk(buffer, payloadText)
      buffer = parsed.remainder

      for (const error of parsed.errors) {
        console.warn('[analyzeAvoiding] 跳过无法解析的 SSE 数据:', error.message, error.payload.slice(0, 300))
      }

      for (const event of parsed.events) {
        const data = event as {
          done?: boolean
          images?: string[]
          category?: string
          lines?: unknown[]
          ok?: boolean
          step?: string
          percent?: number
          avoiding_count?: number
          error?: string
        }

        if (data.done) {
          analysisDone = true
          analyzeLoading.value = false
          if ((resultData as any).ok) {
            const normalized = applyAnalysisResult(resultData, cacheKey)
            analyzeStatus.value = `✅ 分析完成，找到 ${normalized.avoiding_count} 个避障事件`
          } else {
            analyzeError.value = true
            analyzeStatus.value = `❌ ${(resultData as any).error || '分析失败'}`
          }
          analyzeProgress.value = ''
          analyzePercent.value = 100
        } else if (data.images) {
          ;(resultData as any).images = data.images
        } else if (data.category) {
          const categories = (resultData as { categories: Record<string, unknown[]> }).categories
          if (!categories[data.category]) {
            categories[data.category] = []
          }
          categories[data.category].push(...(data.lines || []))
        } else if (data.ok !== undefined) {
          resultData = { ...resultData, ...data, categories: resultData.categories, images: resultData.images }
        } else {
          if (data.step) {
            analyzeProgress.value = data.step
          }
          if (data.percent !== undefined) {
            analyzePercent.value = data.percent
          }
        }
      }
    }

    while (!analysisDone) {
      const { done, value } = await reader.read()
      if (done) break

      handleAnalyzePayloads(decoder.decode(value, { stream: true }))
    }

    if (analysisDone) {
      reader.cancel().catch(() => {})
    } else {
      handleAnalyzePayloads(`${decoder.decode()}\n\n`)
    }
  } catch (e: any) {
    const rawMessage = e?.message || 'network error'
    const message = /failed to fetch|networkerror|network error/i.test(rawMessage)
      ? 'network error，请检查 /offline 服务和代理连接'
      : rawMessage
    if (hasRecoverableAnalysisResult(resultData)) {
      const normalized = applyAnalysisResult(resultData, cacheKey)
      analyzeError.value = false
      analyzeStatus.value = `⚠️ 分析流中断，但已恢复 ${normalized.avoiding_count} 个避障事件的结果`
      console.warn('[analyzeAvoiding] 分析流中断，已使用部分结果恢复界面:', message)
    } else {
      analyzeError.value = true
      analyzeStatus.value = `❌ ${message}`
    }
    analyzeProgress.value = ''
  } finally {
    analyzeLoading.value = false
  }
}
</script>

<style scoped>
.lf-root {
  display: flex;
  flex-direction: column;
  gap: 0;
  height: 100%;
  overflow-y: auto;
  background: #1a1a2e;
  color: #e0e0e0;
  font-size: 13px;
  padding: 8px;
}
.lf-report-section.lf-fullscreen {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.lf-section {
  background: #16213e;
  border: 1px solid #2a2a4a;
  border-radius: 6px;
  padding: 10px 14px;
  margin-bottom: 10px;
}
.lf-section-title {
  font-size: 14px;
  font-weight: 600;
  color: #7eb8f7;
  margin-bottom: 8px;
  border-bottom: 1px solid #2a2a4a;
  padding-bottom: 4px;
}
.lf-section-title-compact {
  margin-bottom: 4px;
  border-bottom: none;
  padding-bottom: 0;
}
.lf-section-caption {
  color: #8ca4cf;
  font-size: 12px;
  line-height: 1.6;
}
.lf-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.lf-label {
  color: #aaa;
  white-space: nowrap;
  font-size: 12px;
}
.lf-sub-label {
  color: #7f93bb;
  white-space: nowrap;
  font-size: 11px;
}
.lf-input {
  flex: 1;
  min-width: 200px;
  background: #0d1117;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 4px 8px;
  font-size: 12px;
}
.lf-input-sm {
  width: 90px;
  background: #0d1117;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 4px 8px;
  font-size: 12px;
}
.lf-input-sn {
  width: 60px;
  background: #0d1117;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 4px 8px;
  font-size: 12px;
  text-align: center;
  font-family: monospace;
}
.lf-input-date {
  width: 100px;
  background: #0d1117;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 4px 8px;
  font-size: 12px;
  text-align: center;
  font-family: monospace;
}
.lf-input-host {
  width: 140px;
  background: #0d1117;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 4px 8px;
  font-size: 12px;
  font-family: monospace;
}
.lf-input-module {
  width: 180px;
  background: #0d1117;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  padding: 4px 8px;
  font-size: 12px;
  font-family: monospace;
}
.lf-input-sn:focus,
.lf-input-date:focus,
.lf-input-host:focus,
.lf-input-module:focus {
  outline: none;
  border-color: #42a5f5;
}
.lf-btn {
  padding: 4px 14px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}
.lf-btn.blue { background: #1565c0; color: #fff; }
.lf-btn.blue:hover:not(:disabled) { background: #1976d2; }
.lf-btn.green { background: #2e7d32; color: #fff; }
.lf-btn.green:hover:not(:disabled) { background: #388e3c; }
.lf-btn.purple { background: #6d4fc2; color: #fff; }
.lf-btn.purple:hover:not(:disabled) { background: #7b5ed8; }
.lf-btn.red { background: #c62828; color: #fff; }
.lf-btn.red:hover:not(:disabled) { background: #e53935; }
.lf-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.lf-transfer-row {
  margin-top: 8px;
}
.lf-transfer-hint {
  color: #8ca4cf;
  font-size: 12px;
  font-family: monospace;
}
.lf-progress-info {
  margin-top: 8px;
  padding: 8px 12px;
  background: #0d1117;
  border: 1px solid #2a5a8a;
  border-radius: 4px;
}
.lf-progress-text {
  font-size: 12px;
  color: #90caf9;
  margin-bottom: 6px;
  font-family: monospace;
}
.lf-progress-bar {
  margin-top: 8px;
  height: 24px;
  background: #0d1117;
  border: 1px solid #333;
  border-radius: 4px;
  overflow: hidden;
  position: relative;
}
.lf-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #1565c0, #42a5f5);
  transition: width 0.3s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  min-width: 40px;
}
.lf-status {
  margin-top: 6px;
  font-size: 12px;
  color: #81c784;
}
.lf-status.error { color: #ef9a9a; }
.lf-terminal {
  margin-top: 8px;
  background: #0d1117;
  border: 1px solid #222;
  border-radius: 4px;
  padding: 6px 8px;
  max-height: 160px;
  overflow-y: auto;
  font-family: monospace;
  font-size: 11px;
}
.lf-log-line { color: #c8e6c9; line-height: 1.5; }
.lf-log-line.log-err { color: #ef9a9a; }
.lf-summary-bar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.lf-badge {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  background: linear-gradient(180deg, rgba(22, 48, 87, 0.92), rgba(14, 28, 54, 0.96));
  border: 1px solid rgba(86, 127, 196, 0.45);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 11px;
  color: #d7e6ff;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
}
.lf-badge-label {
  color: #86a4d7;
}
.lf-analysis-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  margin-bottom: 6px;
  align-items: stretch;
  flex: 0 0 33vh;
  min-height: min(33vh, 240px);
  max-height: min(33vh, 240px);
}
.lf-log-card {
  background: linear-gradient(180deg, rgba(14, 19, 31, 0.96), rgba(8, 12, 21, 0.98));
  border: 1px solid rgba(58, 73, 108, 0.9);
  border-radius: 10px;
  padding: 6px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: min(33vh, 240px);
  max-height: min(33vh, 240px);
  box-shadow: 0 8px 18px rgba(3, 6, 16, 0.2);
}
.lf-log-card.tone-decision {
  border-color: rgba(82, 145, 255, 0.42);
}
.lf-log-card.tone-nav {
  border-color: rgba(88, 187, 149, 0.34);
}
.lf-log-card.tone-stereo {
  border-color: rgba(208, 156, 86, 0.34);
}
.lf-log-card-head,
.lf-media-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.lf-log-card-head.clickable {
  cursor: pointer;
}
.lf-log-card-title-group {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.lf-card-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.lf-card-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  background: rgba(52, 87, 145, 0.18);
  font-size: 12px;
}
.lf-card-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.01em;
  color: #e7f0ff;
  margin-bottom: 2px;
}
.lf-card-subtitle {
  font-size: 9px;
  color: #7d95be;
}
.lf-card-count {
  min-width: 42px;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(56, 90, 149, 0.18);
  border: 1px solid rgba(86, 127, 196, 0.35);
  text-align: center;
  color: #b9d3ff;
  font-size: 10px;
  font-weight: 700;
}
.lf-log-terminal {
  flex: 1;
  min-height: 0;
  height: calc(min(33vh, 240px) - 48px);
  max-height: calc(min(33vh, 240px) - 48px);
  overflow-y: auto;
  font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, monospace;
  font-size: 10px;
  background: linear-gradient(180deg, rgba(8, 12, 19, 0.96), rgba(5, 8, 14, 0.98));
  border: 1px solid rgba(28, 38, 56, 0.95);
  border-radius: 8px;
  padding: 6px;
}
.lf-log-terminal.expanded {
  height: min(78vh, 920px);
}
.lf-log-row {
  display: grid;
  grid-template-columns: 60px minmax(0, 1fr);
  gap: 6px;
  line-height: 1.3;
  padding: 3px 0;
  border-bottom: 1px solid rgba(29, 38, 56, 0.75);
}
.lf-log-row:last-child { border-bottom: none; }
.lf-log-ts {
  color: #8aa4cf;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.lf-log-text {
  color: #d7e4f8;
  word-break: break-word;
  white-space: pre-wrap;
}
.lf-log-truncation {
  margin-top: 4px;
  padding-top: 4px;
  border-top: 1px dashed rgba(71, 92, 132, 0.7);
  color: #7e96bf;
  font-size: 10px;
}
.lf-log-empty-state {
  flex: 1;
  min-height: 0;
  max-height: calc(min(33vh, 240px) - 48px);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: flex-start;
  border: 1px dashed rgba(80, 99, 138, 0.65);
  border-radius: 8px;
  padding: 10px;
  background: linear-gradient(180deg, rgba(8, 12, 19, 0.82), rgba(5, 8, 14, 0.9));
}
.lf-timeline-card {
  background: linear-gradient(180deg, rgba(14, 19, 31, 0.96), rgba(8, 12, 21, 0.98));
  border: 1px solid rgba(58, 73, 108, 0.9);
  border-radius: 10px;
  padding: 8px;
  margin-bottom: 8px;
  box-shadow: 0 8px 18px rgba(3, 6, 16, 0.2);
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  min-height: min(33vh, 240px);
  max-height: min(33vh, 240px);
}
.lf-timeline-terminal {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.lf-timeline-row {
  display: grid;
  grid-template-columns: 60px 104px minmax(0, 1fr);
  gap: 8px;
  line-height: 1.35;
  padding: 4px 0;
  border-bottom: 1px solid rgba(29, 38, 56, 0.75);
}
.lf-timeline-row:last-child { border-bottom: none; }
.lf-timeline-row .lf-log-text {
  grid-column: 3;
}
.lf-timeline-source {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 20px;
  padding: 0 6px;
  border-radius: 999px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.02em;
  background: rgba(48, 65, 97, 0.45);
  color: #d4e3ff;
}
.lf-timeline-row.tone-decision .lf-timeline-source {
  background: rgba(60, 112, 206, 0.25);
  color: #b8d6ff;
}
.lf-timeline-row.tone-nav .lf-timeline-source {
  background: rgba(53, 136, 112, 0.25);
  color: #b9eedf;
}
.lf-timeline-row.tone-stereo .lf-timeline-source {
  background: rgba(163, 112, 39, 0.24);
  color: #ffe0ac;
}
.lf-empty-title {
  color: #dbe7ff;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 6px;
}
.lf-empty-hint {
  color: #7f95b9;
  font-size: 10px;
  line-height: 1.5;
}
.lf-report-secondary {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  gap: 6px;
  flex: 1;
  min-height: 0;
}
.lf-media-card,
.lf-conclusion {
  background: linear-gradient(180deg, rgba(14, 19, 31, 0.96), rgba(8, 12, 21, 0.98));
  border: 1px solid rgba(58, 73, 108, 0.9);
  border-radius: 10px;
  padding: 6px;
  box-shadow: 0 8px 18px rgba(3, 6, 16, 0.2);
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}
.lf-thumb-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  max-height: 270px;
  overflow-y: hidden;
  margin-bottom: 6px;
  flex-shrink: 0;
}
.lf-thumb-item {
  cursor: pointer;
  border: 1px solid rgba(53, 68, 101, 0.9);
  border-radius: 8px;
  overflow: hidden;
  background: rgba(10, 14, 21, 0.96);
  transition: border-color 0.15s ease, transform 0.15s ease;
  width: 72px;
  flex-shrink: 0;
}
.lf-thumb-item:hover { transform: translateY(-1px); }
.lf-thumb-item.active { border-color: #42a5f5; box-shadow: 0 0 0 1px rgba(66, 165, 245, 0.22); }
.lf-thumb-item img { width: 100%; height: 42px; object-fit: cover; display: block; }
.lf-thumb-name {
  font-size: 9px;
  text-align: center;
  color: #90a6cc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 2px 3px 3px;
}
.lf-img-detail {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
  flex: 1;
  min-height: 0;
}
.lf-img-full {
  width: 100%;
  height: 100%;
  flex: 1;
  min-height: 0;
  border-radius: 10px;
  cursor: zoom-in;
  border: 1px solid rgba(56, 71, 104, 0.92);
  object-fit: contain;
  background: #05080d;
}
.lf-img-name { font-size: 10px; color: #8ca4cf; }
.lf-conclusion-body {
  margin-top: 6px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.lf-conclusion-text {
  font-size: 11px;
  line-height: 1.4;
  color: #dce7fb;
}
.lf-conclusion-text h3 { color: #90caf9; margin: 6px 0 3px; font-size: 12px; }
.lf-conclusion-text h4 { color: #a5d6a7; margin: 5px 0 2px; font-size: 11px; }
.lf-loading { color: #ffd54f; font-style: italic; }
.lf-report-head {
  margin-bottom: 6px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.lf-report-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.lf-chip-btn,
.lf-inline-icon-btn {
  border: 1px solid rgba(88, 113, 160, 0.45);
  background: rgba(18, 29, 51, 0.92);
  color: #b8d1ff;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: 0.18s ease;
}
.lf-chip-btn {
  padding: 7px 12px;
}
.lf-chip-btn.active {
  background: linear-gradient(180deg, rgba(34, 76, 140, 0.96), rgba(22, 48, 97, 0.96));
  color: #eff6ff;
  border-color: rgba(112, 162, 255, 0.55);
}
.lf-chip-btn.subtle {
  background: rgba(17, 24, 39, 0.84);
  color: #d5def0;
}
.lf-inline-icon-btn {
  padding: 6px 10px;
}
.lf-chip-btn:hover,
.lf-inline-icon-btn:hover {
  border-color: rgba(132, 174, 255, 0.68);
  color: #eff6ff;
}
.lf-panel-overlay {
  position: fixed;
  inset: 0;
  z-index: 9998;
  background: rgba(4, 8, 15, 0.78);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.lf-panel-dialog {
  width: min(1500px, 94vw);
  max-height: 88vh;
  background: linear-gradient(180deg, rgba(14, 19, 31, 0.98), rgba(8, 12, 21, 0.99));
  border: 1px solid rgba(70, 89, 132, 0.92);
  border-radius: 16px;
  padding: 14px;
  box-shadow: 0 28px 80px rgba(0, 0, 0, 0.55);
}
.lf-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.lf-log-empty-state.overlay {
  min-height: 260px;
}
.lf-log-terminal.overlay {
  border-color: rgba(66, 88, 128, 0.95);
}
@media (max-width: 1260px) {
  .lf-analysis-grid {
    grid-template-columns: 1fr;
    flex: 0 0 auto;
    min-height: 0;
    max-height: none;
  }
  .lf-log-card {
    min-height: 320px;
    max-height: none;
  }
  .lf-log-terminal,
  .lf-log-empty-state {
    min-height: 200px;
    height: 200px;
  }
  .lf-log-terminal.expanded,
  .lf-timeline-terminal {
    height: 58vh;
  }
  .lf-report-secondary {
    grid-template-columns: 1fr;
  }
  .lf-report-head {
    flex-direction: column;
  }
  .lf-timeline-row {
    grid-template-columns: 72px minmax(0, 1fr);
  }
  .lf-timeline-source {
    grid-column: 2;
    justify-self: start;
    margin-bottom: 4px;
  }
  .lf-timeline-row .lf-log-text {
    grid-column: 2;
  }
  .lf-panel-overlay {
    padding: 12px;
  }
  .lf-panel-dialog {
    width: 100%;
    max-height: 92vh;
  }
}
.lf-lightbox {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  cursor: zoom-out;
}
.lf-lightbox img { max-width: 92vw; max-height: 88vh; border-radius: 6px; }
.lf-lb-close {
  position: absolute;
  top: 18px;
  right: 28px;
  font-size: 28px;
  color: #fff;
  cursor: pointer;
  line-height: 1;
}
</style>
