<template>
  <div class="app">
    <!-- Header -->
    <header class="app-header">
      <div class="header-brand">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="23 7 16 12 23 17 23 7"/>
          <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
        </svg>
        <h1>Perception Streaming</h1>
      </div>
      <!-- Tab Nav -->
      <nav class="header-tabs">
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'live' }"
          @click="activeTab = 'live'"
        >实时监控</button>
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'loganalysis2' }"
          @click="activeTab = 'loganalysis2'"
        >Bag包分析</button>
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'logfetch' }"
          @click="activeTab = 'logfetch'"
        >日志分析</button>
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'bagoffline' }"
          @click="activeTab = 'bagoffline'"
        >单目测试</button>
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'stereoanalysis2' }"
          @click="activeTab = 'stereoanalysis2'"
        >双目分析</button>
      </nav>
      <div class="header-status">
        <span class="status-dot" :class="{ active: mqttConnected }"></span>
        <span>{{ mqttConnected ? 'MQTT 已连接' : 'MQTT 未连接' }}</span>
        <span class="status-divider">|</span>
        <span class="status-dot" :class="{ active: monitorStatus.sshConnected, warn: monitorStatus.sshReconnecting }"></span>
        <span :class="monitorStatus.sshReconnecting ? 'status-warn' : ''">
          {{ monitorStatus.sshConnected ? 'SSH 已连接' : monitorStatus.sshReconnecting ? 'SSH 重连中' : 'SSH 未连接' }}
        </span>
        <span class="status-divider">|</span>
        <span class="status-behavior" :class="monitorStatus.behaviorType">
          {{ monitorStatus.behaviorType === 'normal' ? '正常' : monitorStatus.behaviorType === 'miss_avoidance' ? '⚠ 不避障' : monitorStatus.behaviorType === 'false_avoidance' ? '⚠ 误避障' : '–' }}
        </span>
        <template v-if="monitorStatus.recording">
          <span class="status-divider">|</span>
          <span class="status-recording"><span class="rec-dot"></span>录包中</span>
        </template>
        <template v-if="monitorStatus.uploadStatus === 'downloading'">
          <span class="status-divider">|</span>
          <span class="status-download">⬇ 下载中</span>
        </template>
        <template v-if="monitorStatus.abnormalCount > 0">
          <span class="status-divider">|</span>
          <span class="status-abnormal">异常 {{ monitorStatus.abnormalCount }}</span>
        </template>
      </div>
    </header>

    <!-- Live Monitor -->
    <div v-if="activeTab === 'live'" class="app-content" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
      <!-- Sidebar / Config -->
      <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
        <button class="sidebar-toggle" @click="sidebarCollapsed = !sidebarCollapsed" :title="sidebarCollapsed ? '展开' : '收缩'">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path v-if="!sidebarCollapsed" d="M15 18l-6-6 6-6"/>
            <path v-else d="M9 18l6-6-6-6"/>
          </svg>
        </button>
        <div class="sidebar-content">
          <ConnectionPanel v-model="connectionForm" :connected="mqttConnected" />
          <DevicePanel v-model="deviceForm" @snAdded="handleDeviceSnAdded" />
          <ControlBar
            :mqttConnected="mqttConnected"
            :videoStarted="videoStarted"
            @connectMqtt="handleConnectMqtt"
            @disconnectMqtt="handleDisconnectMqtt"
            @startVideo="handleStartVideo"
            @stopVideo="handleStopVideo"
          />
        </div>
      </aside>

      <!-- Main Area -->
      <main class="main-area">
        <!-- Top: Video + Point Cloud side by side -->
        <div class="main-top" :class="{ 'pcl-collapsed': pclCollapsed }">
          <VideoPlayer :streaming="videoStarted" :camera="deviceForm.camera" />
          <PointCloudPanel v-if="!pclCollapsed" @collapse="pclCollapsed = true" />
          <button v-else class="pcl-expand-btn" @click="pclCollapsed = false" title="展开点云">▶</button>
        </div>
        <!-- Bottom: Obstacle Monitor + Log Console side by side -->
        <div class="main-bottom">
          <ObstacleMonitor :mqttConnected="mqttConnected" :videoStarted="videoStarted" @statusUpdate="monitorStatus = $event" />
          <LogConsole :logs="logs" @clear="logs = []" />
        </div>
      </main>
    </div>

    <!-- Log Analysis 2 -->
    <div v-show="activeTab === 'loganalysis2'" class="app-content bag-tab">
      <LogAnalysis2Panel />
    </div>

    <!-- Stereo Analysis 2 -->
    <div v-show="activeTab === 'stereoanalysis2'" class="app-content bag-tab">
      <StereoAnalysis2Panel />
    </div>

    <!-- Log Fetch Analysis -->
    <div v-show="activeTab === 'logfetch'" class="app-content bag-tab">
      <LogFetchPanel />
    </div>

    <!-- Bag Offline Panel -->
    <div v-show="activeTab === 'bagoffline'" class="app-content bag-tab">
      <BagOfflinePanel />
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount, onMounted } from 'vue'
import MqttClient from './utils/mqttClient'
import { joinChannel, leaveChannel, useAgoraRTC } from './composables/useAgoraRTC'
import { updateSshPortForSN } from './composables/useObstacleMonitor'
import ConnectionPanel, { type ConnectionForm } from './components/ConnectionPanel.vue'
import DevicePanel, { type DeviceForm } from './components/DevicePanel.vue'
import VideoPlayer from './components/VideoPlayer.vue'
import LogConsole from './components/LogConsole.vue'
import ControlBar from './components/ControlBar.vue'
import ObstacleMonitor from './components/ObstacleMonitor.vue'
import PointCloudPanel from './components/PointCloudPanel.vue'
import LogAnalysis2Panel from './components/LogAnalysis2Panel.vue'
import StereoAnalysis2Panel from './components/StereoAnalysis2Panel.vue'
import LogFetchPanel from './components/LogFetchPanel.vue'
import BagOfflinePanel from './components/BagOfflinePanel.vue'

const activeTab = ref<'live' | 'loganalysis2' | 'logfetch' | 'bagoffline' | 'stereoanalysis2'>('live')

const sidebarCollapsed = ref(false)
const pclCollapsed = ref(false)

// ─── Obstacle Monitor 状态（从子组件上报）────────────
interface MonitorStatus {
  sshConnected: boolean
  sshReconnecting: boolean
  behaviorType: string
  recording: boolean
  uploadStatus: string | null
  abnormalCount: number
}
const monitorStatus = ref<MonitorStatus>({
  sshConnected: false,
  sshReconnecting: false,
  behaviorType: 'unknown',
  recording: false,
  uploadStatus: null,
  abnormalCount: 0,
})

// ─── LocalStorage Persistence ────────────────────────
const LEGACY_STORAGE_KEY = 'perception_streaming_mqtt_creds'
const STORAGE_KEY_PREFIX = 'perception_streaming_mqtt_creds_v2'
const DEFAULT_MQTT_BROKER = 'mqtt-us.yjserver.com'
const DEFAULT_MQTT_USERNAME = import.meta.env.VITE_DEFAULT_MQTT_USERNAME || ''
const DEFAULT_MQTT_PASSWORD = import.meta.env.VITE_DEFAULT_MQTT_PASSWORD || ''

function getCredentialStorageKey(broker: string) {
  return `${STORAGE_KEY_PREFIX}:${broker}`
}

function loadSavedCredentials(broker: string): { username: string; password: string } {
  try {
    const saved = localStorage.getItem(getCredentialStorageKey(broker))
    if (saved) return JSON.parse(saved)
    localStorage.removeItem(LEGACY_STORAGE_KEY)
  } catch { /* ignore */ }
  return { username: DEFAULT_MQTT_USERNAME, password: DEFAULT_MQTT_PASSWORD }
}

function saveCredentials(broker: string, username: string, password: string) {
  localStorage.setItem(getCredentialStorageKey(broker), JSON.stringify({ username, password }))
}

const savedCreds = loadSavedCredentials(DEFAULT_MQTT_BROKER)

// ─── Form State ──────────────────────────────────────

const connectionForm = ref<ConnectionForm>({
  protocol: 'wss',
  broker: DEFAULT_MQTT_BROKER,
  port: 8084,
  clientId: 'mqttx_' + Math.random().toString(16).substring(2, 10),
  username: savedCreds.username,
  password: savedCreds.password,
  keepalive: 60,
  reconnectPeriod: 4000,
})

const deviceForm = ref<DeviceForm>({
  sn: new URLSearchParams(location.search).get('sn') || 'LK-MR6P1US000286',
  agoraAppId: import.meta.env.VITE_AGORA_APP_ID || '4b918a3ad6b54639895fcf119d6fe7c7',
  camera: 0,
  resolution: 0,
})

// 切换 SN 时若视频已在播放，自动重连到新设备
watch(() => deviceForm.value.sn, async (newSn, oldSn) => {
  // 更新 SSH 端口
  updateSshPortForSN(newSn)

  if (newSn !== oldSn && videoStarted.value) {
    addLog(`SN 已切换 ${oldSn} → ${newSn}，重连视频...`)
    await leaveChannel()
    videoStarted.value = false
    // 重新发送推流指令，等待机器确认后加入新频道
    handleStartVideo()
  }
})

function handleDeviceSnAdded(sn: string) {
  updateSshPortForSN(sn)
}

// ─── Status ──────────────────────────────────────────

const mqttConnected = ref(false)
const videoStarted = ref(false)
const logs = ref<string[]>([])
const mqttClient = new MqttClient()
const { connectionState: agoraConnectionState, remoteUserCount } = useAgoraRTC()

watch(
  () => [connectionForm.value.broker, connectionForm.value.username, connectionForm.value.password] as const,
  ([broker, username, password]) => saveCredentials(broker, username, password),
  { deep: false }
)

watch(agoraConnectionState, (state) => addLog(`Agora 状态: ${state}`))
watch(remoteUserCount, (count) => {
  if (count > 0) addLog(`Agora 已订阅远端视频用户: ${count}`)
})

function addLog(msg: string) {
  logs.value.push(`[${new Date().toLocaleTimeString()}] ${msg}`)
}

// ─── MQTT ────────────────────────────────────────────

function handleConnectMqtt() {
  const c = connectionForm.value
  const d = deviceForm.value

  if (!c.broker || !c.username || !c.password || !d.sn) {
    alert('请填写 Broker 地址、用户名、密码、设备 SN')
    return
  }

  const brokerUrl = `${c.protocol}://${c.broker}:${c.port}/mqtt`

  mqttClient.init({
    brokerUrl,
    clientId: c.clientId,
    username: c.username,
    password: c.password,
    keepalive: c.keepalive,
    clean: true,
    reconnectPeriod: c.reconnectPeriod,
  })

  // Save credentials to localStorage
  saveCredentials(c.broker, c.username, c.password)

  const result = mqttClient.connect()
  if (result === 'connect') {
    addLog(`MQTT 连接中... ${brokerUrl} (用户: ${c.username})`)

    // Listen for successful connection
    mqttClient.on('connect', () => {
      mqttConnected.value = true
      addLog(`✓ MQTT 已连接 → ${c.broker}:${c.port}`)

      const sn = d.sn
      addLog(`连接设备 SN: ${sn}`)
      const subTopics = [
        `bestmow/respond/${sn}`,
        `bestmow/status_report/${sn}`,
      ]
      mqttClient.subscribe(subTopics, (topic, message) => {
        try {
          const json = JSON.parse(message)
          const operation = json.operation || 'unknown'

          // 过滤掉重复的状态上报消息（只保留关键操作）
          const filteredOperations = [
            'robot_status',
            'wifi_status',
            'robot_real_time_cov_path',
            'ctr_remote_cmd_vel',           // 遥控指令（高频）
            'upload_progress',              // 上传进度
            'robot_event',                  // 机器事件（高频）
            'set_mower_online',             // 上线状态
            'set_mower_offline',            // 离线状态
            'map_get_charging_pose',        // 充电桩位置查询
            'set_get_event_alert',          // 事件告警
            'set_state_synchronization',    // 状态同步
          ]

          if (!filteredOperations.includes(operation)) {
            addLog(`[${topic}] ${operation}`)
          }

          if (operation === 'mow_enable_remote_rtsp' && json.success === true) {
            addLog('机器确认推流, 加入 Agora 频道...')
            joinChannel(deviceForm.value.agoraAppId, deviceForm.value.sn)
              .then(() => { videoStarted.value = true })
              .catch((err) => {
                const message = err instanceof Error ? err.message : String(err)
                addLog(`✗ 加入 Agora 频道失败: ${message}`)
              })
          }
        } catch {
          addLog(`[${topic}] ${message}`)
        }
      })
    })

    // Listen for errors
    mqttClient.on('error', (err: Error) => {
      mqttConnected.value = false
      addLog(`✗ MQTT 错误: ${err.message || err}`)
    })

    // Listen for disconnect
    mqttClient.on('disconnect', () => {
      mqttConnected.value = false
    })
  } else {
    // Already connected
    mqttConnected.value = true
    addLog(`✓ MQTT 已连接 → ${c.broker}:${c.port} (用户: ${c.username})`)
  }
}

let liveMonitorCleanupPromise: Promise<void> | null = null

function cleanupLiveMonitor(waitForVideoLeave = true) {
  if (liveMonitorCleanupPromise) return liveMonitorCleanupPromise

  liveMonitorCleanupPromise = (async () => {
    try {
      if (videoStarted.value) {
        if (waitForVideoLeave) {
          await handleStopVideo()
        } else {
          publishStopVideoCommand()
          videoStarted.value = false
          leaveChannel()
          addLog('已关闭视频')
        }
      }

      if (mqttConnected.value || mqttClient.isConnected) {
        const result = mqttClient.disconnect()
        mqttConnected.value = false
        addLog(result)
      }
    } finally {
      liveMonitorCleanupPromise = null
    }
  })()

  return liveMonitorCleanupPromise
}

async function handleDisconnectMqtt() {
  await cleanupLiveMonitor()
}

// ─── Video Control ───────────────────────────────────

function handleStartVideo() {
  const d = deviceForm.value
  const c = connectionForm.value

  if (!d.agoraAppId) {
    alert('请填写 Agora App ID')
    return
  }

  if (!window.isSecureContext) {
    const secureUrl = `https://${location.host}${location.pathname}${location.search}`
    const msg = `当前页面不是安全上下文，Agora 视频需要使用 ${secureUrl} 打开`
    addLog(`✗ ${msg}`)
    alert(msg)
    return
  }

  const message = {
    msg_id: c.username,
    operation: 'mow_enable_remote_rtsp',
    timestamp: Date.now(),
    payload: {
      appid: d.agoraAppId,
      license: '',
      token: 'web1',
      resolution_level: d.resolution,
      camera: d.camera,
    },
  }

  const topic = `bestmow/request/${d.sn}`
  const result = mqttClient.publish(topic, JSON.stringify(message))
  if (result === 'success') {
    addLog(`已发送开启视频指令 → ${topic}`)
  } else {
    addLog(`发送失败: ${result}`)
  }
}

function publishStopVideoCommand() {
  const d = deviceForm.value
  const c = connectionForm.value
  const message = {
    msg_id: c.username,
    operation: 'mow_disable_remote_rtsp',
    timestamp: Date.now(),
    payload: { appid: '', license: '', token: 'web1' },
  }
  mqttClient.publish(`bestmow/request/${d.sn}`, JSON.stringify(message))
}

async function handleStopVideo() {
  publishStopVideoCommand()
  await leaveChannel()
  videoStarted.value = false
  addLog('已关闭视频')
}

// ─── Load Modes ──────────────────────────────────────

// ─── Initialization ──────────────────────────────────

function handlePageUnload() {
  cleanupLiveMonitor(false)
}

// Initialize SSH port based on current SN
onMounted(() => {
  updateSshPortForSN(deviceForm.value.sn)
  window.addEventListener('pagehide', handlePageUnload)
  window.addEventListener('beforeunload', handlePageUnload)
})

// ─── Cleanup ─────────────────────────────────────────

onBeforeUnmount(() => {
  window.removeEventListener('pagehide', handlePageUnload)
  window.removeEventListener('beforeunload', handlePageUnload)
  cleanupLiveMonitor().finally(() => mqttClient.destroy())
})
</script>

<style scoped>
</style>
