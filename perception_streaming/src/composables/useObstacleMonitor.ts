import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'

// SSH port configuration (shared state)
export const sshPort = ref(10111)

// SN to SSH port mapping
export const SN_PORT_MAP: Record<string, number> = {
  'LK-MR2P1US000015': 10015,
  'LK-MR2P1US000016': 10016,
  'LK-MR2P1US000017': 10017,
  'LK-MR2P1US000113': 10113,
  'LK-MR2P1US000115': 10115,
  'LK-MR6P1US000123': 10123,
  'LK-MR6P1US000124': 10124,
  'LK-MR6P1US000286': 10286,
}

// Update SSH port based on device SN
export function updateSshPortForSN(sn: string) {
  const port = SN_PORT_MAP[sn]
  if (port) {
    sshPort.value = port
  }
}

export interface ObstacleStatus {
  timestamp: number
  has_obstacle: boolean
  distance: number
  velocity: number
  angular: number
  type: 'normal' | 'miss_avoidance' | 'false_avoidance' | 'unknown'
  reason: string
  bag_path?: string
}

export interface CmdVelStatus {
  velocity: number
  angular: number
}

export interface RecordingStatus {
  status: 'idle' | 'recording' | 'completed' | 'error' | 'cooldown'
  bag_name?: string
  bag_path?: string
  reason?: string
  duration?: number
}

export interface UploadStatus {
  status: 'downloading' | 'done' | 'error'
  bag_name?: string
  local_path?: string
  reason?: string
}

export interface LogEntry {
  timestamp: number
  text: string
  relevant: boolean
}

const BRIDGE_URL = 'ws://localhost:8765'

export function useObstacleMonitor(
  getMqttConnected: () => boolean | undefined,
  getVideoStarted: () => boolean | undefined,
  onStatus: (payload: {
    sshConnected: boolean
    sshReconnecting: boolean
    behaviorType: string
    recording: boolean
    uploadStatus: string | null
    abnormalCount: number
  }) => void
) {
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let countdownTimer: ReturnType<typeof setInterval> | null = null
  let cooldownTimer: ReturnType<typeof setInterval> | null = null

  const connectionStatus = ref<'connected' | 'disconnected'>('disconnected')
  const sshConnected = ref(false)
  const autoConnectTriggered = ref(false)
  const sshConnectFailed = ref(false)
  const sshErrorMsg = ref('')
  const sshReconnecting = ref(false)

  const currentStatus = ref<ObstacleStatus>({
    timestamp: 0, has_obstacle: false, distance: Infinity,
    velocity: 0, angular: 0, type: 'unknown', reason: ''
  })
  const cmdVelStatus = ref<CmdVelStatus>({ velocity: 0, angular: 0 })
  const abnormalEvents = ref<ObstacleStatus[]>([])
  const recordingStatus = ref<RecordingStatus>({ status: 'idle' })
  const uploadStatus = ref<UploadStatus | null>(null)
  const recentLogs = ref<LogEntry[]>([])
  const showOnlyRelevantLogs = ref(false)
  const logsListEl = ref<HTMLElement | null>(null)
  const bulkUploading = ref(false)
  const bulkUploadMsg = ref('')
  const recordingStarting = ref(false)
  const recordingCountdown = ref(0)
  const cooldownCountdown = ref(0)
  const monitorServiceRunning = ref(false)
  const monitorServiceLoading = ref(false)
  const monitorServiceMsg = ref('')

  // 图片上传
  const yesterday = new Date(); yesterday.setDate(yesterday.getDate() - 1)
  const imageUploadDate = ref(yesterday.toISOString().slice(0, 10).replace(/-/g, ''))
  const imageUploading = ref(false)
  const imageUploadMsg = ref('')

  const behaviorClass = computed(() => currentStatus.value.type)
  const behaviorIcon = computed(() => {
    switch (currentStatus.value.type) {
      case 'normal': return '\u2713'
      case 'miss_avoidance': return '\u26a0'
      case 'false_avoidance': return '\u26a0'
      default: return '\u2013'
    }
  })
  const behaviorText = computed(() => {
    switch (currentStatus.value.type) {
      case 'normal': return '正常'
      case 'miss_avoidance': return '不避障异常'
      case 'false_avoidance': return '误避障异常'
      default: return sshConnected.value ? '等待数据' : 'SSH 未连接'
    }
  })

  function formatDistance(distance: number): string {
    if (!isFinite(distance)) return '\u221e'
    return distance.toFixed(2) + ' m'
  }

  function formatTime(timestamp: number): string {
    const ms = timestamp > 1e11 ? timestamp : timestamp * 1000
    return new Date(ms).toLocaleTimeString('zh-CN')
  }

  function getEventTypeName(type: string): string {
    if (type === 'miss_avoidance') return '不避障'
    if (type === 'false_avoidance') return '误避障'
    return type
  }

  function cleanLog(text: string): string {
    return text
      .replace(/\x1b\[[0-9;]*m/g, '')
      .replace(/[\r\n\t]+/g, ' ')
      .replace(/\s{2,}/g, ' ')
      .trim()
  }

  function send(msg: object) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg))
  }

  function connectSSH() { send({ action: 'connect_ssh', port: sshPort.value }) }
  function disconnectSSH() { send({ action: 'disconnect_ssh' }) }
  function triggerRecording() { recordingStarting.value = true; send({ action: 'trigger_recording', reason: 'manual' }) }
  function bulkUploadBags() { bulkUploading.value = true; bulkUploadMsg.value = '正在扫描录包文件...'; send({ action: 'bulk_upload_bags' }) }
  function checkAndStartMonitorService() { monitorServiceLoading.value = true; monitorServiceMsg.value = '正在检查服务状态...'; send({ action: 'check_and_start_monitor_service' }) }
  function stopMonitorService() { monitorServiceLoading.value = true; monitorServiceMsg.value = '正在关闭监控拍照服务...'; send({ action: 'stop_monitor_service' }) }

  function uploadMonitorImages() {
    imageUploading.value = true
    imageUploadMsg.value = '正在上传图片...'
    send({ action: 'upload_monitor_images', date: imageUploadDate.value })
  }

  // 按日期范围上传图片
  const _today = new Date()
  const _start = new Date(_today); _start.setDate(_today.getDate() - 3)
  const _fmtDate = (d: Date) => d.toISOString().slice(0, 10).replace(/-/g, '')
  const uploadRangeDateStart = ref(_fmtDate(_start))
  const uploadRangeDateEnd = ref(_fmtDate(_today))
  const uploadRangeRunning = ref(false)
  const uploadRangeMsg = ref('')

  async function uploadImagesRange() {
    if (!uploadRangeDateStart.value || !uploadRangeDateEnd.value || uploadRangeRunning.value) return
    uploadRangeRunning.value = true
    uploadRangeMsg.value = '正在上传...'
    try {
      const res = await fetch('/offline/upload_images_range', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          port: sshPort.value,
          date_start: uploadRangeDateStart.value,
          date_end: uploadRangeDateEnd.value,
        }),
      })
      const data = await res.json()
      if (data.ok) {
        uploadRangeMsg.value = `✓ 已上传 ${data.folder_count} 个文件夹，${data.file_count} 个文件`
      } else {
        uploadRangeMsg.value = `✗ ${data.error}`
      }
    } catch {
      uploadRangeMsg.value = '✗ 请求失败'
    } finally {
      uploadRangeRunning.value = false
    }
  }

  function startCountdown(seconds: number) {
    recordingCountdown.value = seconds
    if (countdownTimer) clearInterval(countdownTimer)
    countdownTimer = setInterval(() => {
      if (recordingCountdown.value > 0) { recordingCountdown.value-- }
      else { if (countdownTimer) clearInterval(countdownTimer) }
    }, 1000)
  }

  function stopCountdown() {
    if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null }
    recordingCountdown.value = 0
  }

  function startCooldownCountdown(seconds: number) {
    cooldownCountdown.value = seconds
    if (cooldownTimer) clearInterval(cooldownTimer)
    cooldownTimer = setInterval(() => {
      if (cooldownCountdown.value > 0) { cooldownCountdown.value-- }
      else {
        if (cooldownTimer) clearInterval(cooldownTimer)
        cooldownTimer = null
        if (recordingStatus.value.status === 'cooldown') recordingStatus.value = { status: 'idle' }
      }
    }, 1000)
  }

  function stopCooldownCountdown() {
    if (cooldownTimer) { clearInterval(cooldownTimer); cooldownTimer = null }
    cooldownCountdown.value = 0
  }

  function handleMessage(data: Record<string, unknown>) {
    switch (data.type) {
      case 'bridge_status':
        sshConnected.value = data.ssh_connected as boolean
        sshReconnecting.value = !!(data.reconnecting as boolean)
        sshErrorMsg.value = (data.error as string) || ''
        if (autoConnectTriggered.value && !sshConnected.value && !sshReconnecting.value) {
          sshConnectFailed.value = true
        } else if (sshConnected.value) {
          sshConnectFailed.value = false; sshReconnecting.value = false; sshErrorMsg.value = ''
        }
        if (!sshConnected.value && !sshReconnecting.value) {
          currentStatus.value = { ...currentStatus.value, type: 'unknown', reason: '' }
          if (monitorServiceRunning.value) { monitorServiceRunning.value = false; monitorServiceMsg.value = 'SSH断开，监控服务状态未知' }
        }
        break

      case 'obstacle_analysis':
      case 'obstacle_status': {
        const VALID_TYPES = ['normal', 'miss_avoidance', 'false_avoidance', 'unknown']
        const rawType = data.type as string
        const validatedType = VALID_TYPES.includes(rawType) ? (rawType as ObstacleStatus['type']) : 'unknown'
        const rawDist = data.distance as number
        const validatedDist = (typeof rawDist === 'number' && rawDist >= 0) ? rawDist : Infinity
        const rawVel = data.velocity as number
        const validatedVel = (typeof rawVel === 'number' && isFinite(rawVel)) ? rawVel : 0
        const status: ObstacleStatus = {
          timestamp: (data.timestamp as number) ?? 0, has_obstacle: !!(data.has_obstacle),
          distance: validatedDist, velocity: validatedVel, angular: (data.angular as number) ?? 0,
          type: validatedType, reason: (data.reason as string) ?? '', bag_path: data.bag_path as string | undefined,
        }
        currentStatus.value = status
        if (status.type !== 'normal' && status.type !== 'unknown') {
          abnormalEvents.value.unshift(status)
          if (abnormalEvents.value.length > 100) abnormalEvents.value.pop()
        }
        break
      }

      case 'record_status':
        recordingStatus.value = data as unknown as RecordingStatus
        recordingStarting.value = false
        if ((data.status as string) === 'recording') { startCountdown((data.duration as number) ?? 30) }
        else if ((data.status as string) === 'cooldown') { startCooldownCountdown((data.cooldown_seconds as number) ?? 60) }
        else { stopCountdown(); stopCooldownCountdown(); if ((data.status as string) === 'completed') uploadStatus.value = null }
        break

      case 'upload_status': uploadStatus.value = data as unknown as UploadStatus; break

      case 'bulk_upload_status': {
        const s = data as Record<string, unknown>
        if (s.status === 'done') {
          const parts = []
          if (s.copied) parts.push(`新下载 ${s.copied} 个`)
          if (s.resumed) parts.push(`续传 ${s.resumed} 个`)
          if (s.skipped) parts.push(`跳过 ${s.skipped} 个`)
          bulkUploading.value = false
          bulkUploadMsg.value = `上传完成：${parts.join('，')} → ${s.dest}`
        }
        else if (s.status === 'error') { bulkUploading.value = false; bulkUploadMsg.value = `上传失败: ${s.reason}` }
        else if (s.status === 'progress') { bulkUploadMsg.value = `正在上传: ${s.current}` }
        break
      }

      case 'cmd_vel':
        cmdVelStatus.value.velocity = (data.linear as number) ?? 0
        cmdVelStatus.value.angular = (data.angular as number) ?? 0
        break

      case 'log': {
        const entry = data as unknown as LogEntry
        recentLogs.value.unshift(entry)
        if (recentLogs.value.length > 100) recentLogs.value.pop()
        break
      }

      case 'monitor_service_status': {
        monitorServiceLoading.value = false
        const status = data.status as string
        if (status === 'running') { monitorServiceRunning.value = true; monitorServiceMsg.value = `监控拍照服务运行中${data.enabled ? '' : '（未开机自启）'}` }
        else if (status === 'started') { monitorServiceRunning.value = true; monitorServiceMsg.value = '监控拍照服务已启动并设为开机自启' }
        else if (status === 'stopped') { monitorServiceRunning.value = false; monitorServiceMsg.value = '监控拍照服务已关闭' }
        else if (status === 'error') { monitorServiceRunning.value = false; monitorServiceMsg.value = `错误: ${data.reason ?? '未知'}` }
        break
      }

      case 'image_upload_status': {
        const s = data as Record<string, unknown>
        if (s.status === 'done') { imageUploading.value = false; imageUploadMsg.value = `图片上传完成：${s.copied} 张 → ${s.dest}` }
        else if (s.status === 'error') { imageUploading.value = false; imageUploadMsg.value = `上传失败: ${s.reason}` }
        else if (s.status === 'progress') { imageUploadMsg.value = `正在上传: ${s.current}` }
        break
      }
    }
  }

  function connectBridge() {
    console.log('[ObstacleMonitor] Connecting to Bridge:', BRIDGE_URL)
    ws = new WebSocket(BRIDGE_URL)
    ws.onopen = () => {
      console.log('[ObstacleMonitor] Bridge connected')
      connectionStatus.value = 'connected'
      if (getMqttConnected()) { autoConnectTriggered.value = true; connectSSH() }
    }
    ws.onmessage = (e) => { try { handleMessage(JSON.parse(e.data)) } catch { /* ignore */ } }
    ws.onclose = () => {
      console.log('[ObstacleMonitor] Bridge disconnected, reconnecting in 5s...')
      connectionStatus.value = 'disconnected'
      sshConnected.value = false
      reconnectTimer = setTimeout(connectBridge, 5000)
    }
    ws.onerror = (err) => {
      console.error('[ObstacleMonitor] Bridge connection error:', err)
      ws?.close()
    }
  }

  function tryAutoConnect() {
    if (connectionStatus.value === 'connected' && !sshConnected.value && !sshReconnecting.value) {
      autoConnectTriggered.value = true; sshConnectFailed.value = false; connectSSH()
    }
  }

  function emitStatus() {
    onStatus({
      sshConnected: sshConnected.value, sshReconnecting: sshReconnecting.value,
      behaviorType: currentStatus.value.type, recording: recordingStatus.value.status === 'recording',
      uploadStatus: uploadStatus.value?.status ?? null, abnormalCount: abnormalEvents.value.length,
    })
  }

  watch([sshConnected, sshReconnecting, () => currentStatus.value.type,
    () => recordingStatus.value.status, () => uploadStatus.value?.status,
    () => abnormalEvents.value.length], emitStatus)

  watch(() => recentLogs.value.length, async () => {
    await nextTick()
    if (logsListEl.value) logsListEl.value.scrollTop = 0
  })

  onMounted(() => connectBridge())

  onUnmounted(() => {
    if (reconnectTimer) clearTimeout(reconnectTimer)
    if (countdownTimer) clearInterval(countdownTimer)
    if (cooldownTimer) clearInterval(cooldownTimer)
    ws?.close()
  })

  return {
    connectionStatus, sshConnected, sshPort, sshConnectFailed, sshErrorMsg, sshReconnecting,
    currentStatus, cmdVelStatus, abnormalEvents, recordingStatus, uploadStatus,
    recentLogs, showOnlyRelevantLogs, logsListEl,
    bulkUploading, bulkUploadMsg, recordingStarting, recordingCountdown, cooldownCountdown,
    monitorServiceRunning, monitorServiceLoading, monitorServiceMsg,
    imageUploadDate, imageUploading, imageUploadMsg,
    uploadRangeDateStart, uploadRangeDateEnd, uploadRangeRunning, uploadRangeMsg,
    behaviorClass, behaviorIcon, behaviorText,
    formatDistance, formatTime, getEventTypeName, cleanLog,
    connectSSH, disconnectSSH, triggerRecording, bulkUploadBags,
    checkAndStartMonitorService, stopMonitorService, uploadMonitorImages, uploadImagesRange,
    tryAutoConnect,
  }
}
