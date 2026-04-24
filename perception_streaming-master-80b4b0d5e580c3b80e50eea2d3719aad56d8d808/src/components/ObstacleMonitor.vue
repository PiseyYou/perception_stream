<template>
  <div class="obstacle-monitor">
    <div class="monitor-header">
      <h3>避障行为监控</h3>
      <div class="header-badges">
        <span class="badge" :class="connectionStatus">
          Bridge {{ connectionStatus === 'connected' ? '已连接' : '未连接' }}
        </span>
        <span class="badge" :class="sshConnected ? 'connected' : sshReconnecting ? 'reconnecting' : 'disconnected'">
          SSH {{ sshConnected ? '已连接' : sshReconnecting ? '重连中...' : '未连接' }}
        </span>
      </div>
    </div>

    <!-- SSH 控制 -->
    <div class="ssh-control">
      <input v-model.number="sshPort" type="number" placeholder="端口号" class="port-input" :disabled="sshConnected" />
      <template v-if="sshConnected">
        <button @click="disconnectSSH" class="btn-disconnect">断开</button>
      </template>
      <template v-else>
        <button @click="connectSSH" class="btn-connect" :disabled="connectionStatus !== 'connected'">
          {{ connectionStatus !== 'connected' ? 'Bridge 未连接' : '连接机器' }}
        </button>
        <span v-if="sshErrorMsg" class="ssh-error-text" :title="sshErrorMsg">✗ {{ sshErrorMsg.length > 20 ? sshErrorMsg.slice(0, 20) + '...' : sshErrorMsg }}</span>
      </template>
      <button @click="triggerRecording" class="btn-record" :disabled="!sshConnected">手动录包</button>
      <button @click="bulkUploadBags" class="btn-bulk-upload" :disabled="bulkUploading">
        {{ bulkUploading ? '上传中...' : 'rosbag包上传' }}
      </button>
      <button @click="checkAndStartMonitorService" class="btn-obs-monitor" :class="{ monitoring: monitorServiceRunning }" :disabled="!sshConnected || monitorServiceLoading">
        {{ monitorServiceLoading ? '检查中...' : monitorServiceRunning ? '监控拍照运行中' : '开启监控拍照' }}
      </button>
      <button @click="stopMonitorService" class="btn-obs-stop" :disabled="!sshConnected || !monitorServiceRunning || monitorServiceLoading">关闭监控拍照</button>
      <label class="ctrl-label">开始:</label>
      <input v-model="uploadRangeDateStart" type="text" class="port-input" style="width:90px" placeholder="20260321" maxlength="8" />
      <label class="ctrl-label">截止:</label>
      <input v-model="uploadRangeDateEnd" type="text" class="port-input" style="width:90px" placeholder="20260331" maxlength="8" />
      <button @click="uploadImagesRange" class="btn-bulk-upload" :disabled="uploadRangeRunning || !uploadRangeDateStart || !uploadRangeDateEnd">
        {{ uploadRangeRunning ? '上传中...' : '📤 上传图片' }}
      </button>
      <span v-if="uploadRangeMsg" class="upload-range-msg" :class="{ error: uploadRangeMsg.startsWith('✗') }">{{ uploadRangeMsg }}</span>
    </div>

    <!-- 监控服务状态 -->
    <div class="obs-monitor-panel" v-if="monitorServiceMsg">
      <span class="obs-monitor-dot" v-if="monitorServiceRunning"></span>
      <span class="obs-monitor-text">{{ monitorServiceMsg }}</span>
    </div>

    <!-- 批量上传状态 -->
    <div class="bulk-upload-panel" v-if="bulkUploadMsg">
      <span>{{ bulkUploadMsg }}</span>
    </div>
    <!-- 图片上传状态 -->
    <div class="bulk-upload-panel" v-if="imageUploadMsg">
      <span>{{ imageUploadMsg }}</span>
    </div>

    <div class="monitor-content">
      <!-- 行为判断结果 + 实时状态 -->
      <div class="behavior-panel" :class="behaviorClass" v-if="currentStatus.type !== 'unknown'">
        <span class="icon">{{ behaviorIcon }}</span>
        <span class="text">{{ behaviorText }}</span>
        <span class="reason" v-if="currentStatus.reason">— {{ currentStatus.reason }}</span>
        <span class="status-meta">
          <span :class="{ alert: currentStatus.has_obstacle }">
            {{ currentStatus.has_obstacle ? `障碍 ${formatDistance(currentStatus.distance)}` : '无障碍' }}
          </span>
          <span v-if="cmdVelStatus.velocity !== 0"> · {{ cmdVelStatus.velocity.toFixed(2) }}m/s(底盘)</span>
        </span>
      </div>

      <!-- 录包状态 -->
      <div class="recording-panel starting" v-if="recordingStarting && recordingStatus.status !== 'recording'">
        <span class="recording-dot" style="background:#f4d471"></span>
        <span>启动中，正在连接机器并检查环境...</span>
      </div>
      <div class="recording-panel" v-else-if="recordingStatus.status === 'recording'">
        <span class="recording-dot"></span>
        <span>正在录包: {{ recordingStatus.bag_name }}</span>
        <span class="recording-countdown" v-if="recordingCountdown > 0">剩余 {{ recordingCountdown }}s</span>
      </div>
      <div class="recording-panel error" v-else-if="recordingStatus.status === 'error'">
        <span>✗ 录包失败: {{ recordingStatus.reason }}</span>
      </div>
      <div class="recording-panel cooldown" v-else-if="recordingStatus.status === 'cooldown'">
        <span>⏳ 录包冷却中，还需等待 {{ cooldownCountdown }}s</span>
      </div>

      <!-- 下载状态 -->
      <div class="upload-panel downloading" v-if="uploadStatus?.status === 'downloading'">
        <span class="upload-dot"></span>
        <span>正在下载录包: {{ uploadStatus.bag_name }}</span>
      </div>
      <div class="upload-panel done" v-else-if="uploadStatus?.status === 'done'">
        <span>✓ 已保存: {{ uploadStatus.local_path }}</span>
      </div>
      <div class="upload-panel error" v-else-if="uploadStatus?.status === 'error'">
        <span>✗ 下载失败: {{ uploadStatus.reason }}</span>
      </div>

      <!-- 关联日志 -->
      <div class="logs-panel">
        <div class="logs-header">
          <h4>关联日志</h4>
          <label class="toggle-label">
            <input type="checkbox" v-model="showOnlyRelevantLogs" />
            仅相关
          </label>
          <button @click="recentLogs = []" class="btn-clear">清空</button>
        </div>
        <div class="logs-list" ref="logsListEl">
          <div
            v-for="log in (showOnlyRelevantLogs ? recentLogs.filter(l => l.relevant) : recentLogs)"
            :key="log.timestamp"
            class="log-item"
            :class="{ relevant: log.relevant }"
          >
            <span class="log-time">{{ formatTime(log.timestamp) }}</span>
            <span class="log-text">{{ cleanLog(log.text) }}</span>
          </div>
          <div v-if="recentLogs.length === 0" class="empty-hint">暂无日志</div>
        </div>
      </div>

      <!-- 异常事件列表 -->
      <div class="events-panel">
        <div class="events-header">
          <h4>异常事件 ({{ abnormalEvents.length }})</h4>
          <button @click="abnormalEvents = []" class="btn-clear">清空</button>
        </div>
        <div class="events-list">
          <div v-for="event in abnormalEvents" :key="event.timestamp" class="event-item" :class="event.type">
            <span class="event-time">{{ formatTime(event.timestamp) }}</span>
            <span class="event-type">{{ getEventTypeName(event.type) }}</span>
            <span class="event-reason">{{ event.reason }}</span>
          </div>
          <div v-if="abnormalEvents.length === 0" class="empty-hint">暂无异常事件</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { useObstacleMonitor } from '../composables/useObstacleMonitor'

const props = defineProps<{ mqttConnected?: boolean; videoStarted?: boolean }>()
const emit = defineEmits<{
  (e: 'statusUpdate', payload: {
    sshConnected: boolean; sshReconnecting: boolean; behaviorType: string
    recording: boolean; uploadStatus: string | null; abnormalCount: number
  }): void
}>()

const {
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
  checkAndStartMonitorService, stopMonitorService, uploadMonitorImages, uploadImagesRange, tryAutoConnect,
} = useObstacleMonitor(
  () => props.mqttConnected,
  () => props.videoStarted,
  (payload) => emit('statusUpdate', payload)
)

watch(() => props.mqttConnected, (connected) => { if (connected) tryAutoConnect() })
watch(() => props.videoStarted, (started) => { if (started) tryAutoConnect() })
</script>

<style scoped>
.obstacle-monitor {
  background: #1e1e1e;
  border-radius: 8px;
  padding: 12px 16px;
  color: #e0e0e0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.monitor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  border-bottom: 1px solid #333;
  padding-bottom: 12px;
}
.monitor-header h3 { margin: 0; font-size: 16px; }
.header-badges { display: flex; gap: 6px; }
.badge { padding: 3px 10px; border-radius: 4px; font-size: 11px; }
.badge.connected { background: #2d5016; color: #7bc96f; }
.badge.disconnected { background: #3a2a2a; color: #888; }
.badge.reconnecting { background: #2a2a1a; color: #f4d471; }

.ssh-control { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; flex-wrap: nowrap; overflow: hidden; }
.port-input { width: 90px; background: #2a2a2a; border: 1px solid #444; border-radius: 4px; padding: 5px 8px; color: #e0e0e0; font-size: 13px; }
.btn-connect, .btn-disconnect, .btn-record { padding: 5px 12px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; }
.btn-connect { background: #2d5016; color: #7bc96f; }
.btn-disconnect { background: #5c1a1a; color: #f48771; }
.btn-record { background: #3a3a3a; color: #e0e0e0; }
.btn-record:disabled { opacity: 0.4; cursor: not-allowed; }
.ssh-error-text { color: #f48771; font-size: 11px; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.btn-bulk-upload { background: #1a2e3a; color: #5b9bd5; border: none; border-radius: 4px; padding: 5px 12px; cursor: pointer; font-size: 13px; }
.btn-bulk-upload:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-obs-monitor { background: #1a2a1a; color: #6ee7b7; border: 1px solid #2d5a2d; border-radius: 4px; padding: 5px 12px; cursor: pointer; font-size: 13px; transition: background 0.15s; }
.btn-obs-monitor:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-obs-monitor.monitoring { background: #1a2e1a; color: #4ade80; border-color: #3d7a3d; animation: obs-pulse 1.5s infinite; }
@keyframes obs-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
.btn-obs-stop { background: #2d1a1a; color: #f87171; border: 1px solid #5a2d2d; border-radius: 4px; padding: 5px 12px; cursor: pointer; font-size: 13px; transition: background 0.15s; }
.btn-obs-stop:disabled { opacity: 0.4; cursor: not-allowed; }
.obs-monitor-panel { display: flex; align-items: center; gap: 8px; background: #0d1a10; border: 1px solid #2d5a2d; border-radius: 6px; padding: 6px 12px; font-size: 12px; color: #6ee7b7; margin-bottom: 4px; }
.obs-monitor-dot { width: 8px; height: 8px; background: #4ade80; border-radius: 50%; flex-shrink: 0; animation: pulse 1s infinite; }
.obs-monitor-text { word-break: break-all; }
.bulk-upload-panel { background: #1a2030; border: 1px solid #5b9bd5; border-radius: 6px; padding: 6px 12px; font-size: 12px; color: #5b9bd5; margin-bottom: 4px; }
.ctrl-label { font-size: 11px; color: #888; white-space: nowrap; }
.upload-range-msg { font-size: 11px; color: #69f0ae; font-family: monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 220px; flex-shrink: 1; }
.upload-range-msg.error { color: #ef5350; }
.monitor-content { display: flex; flex-direction: column; gap: 8px; flex: 1; min-height: 0; overflow-y: auto; }

.behavior-panel { display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-radius: 6px; border-left: 4px solid; font-size: 14px; }
.behavior-panel.normal { background: #1a2e1a; border-color: #7bc96f; }
.behavior-panel.miss_avoidance, .behavior-panel.false_avoidance { background: #2e1a1a; border-color: #f48771; }
.behavior-panel.unknown { background: #252525; border-color: #444; }
.behavior-panel .icon { font-size: 18px; }
.behavior-panel .text { font-weight: 600; }
.behavior-panel .reason { color: #aaa; font-size: 12px; }
.behavior-panel .status-meta { margin-left: auto; font-size: 11px; color: #666; }
.behavior-panel .status-meta .alert { color: #f48771; font-weight: 600; }

.recording-panel { display: flex; align-items: center; gap: 8px; background: #2e1a1a; padding: 8px 12px; border-radius: 6px; border: 1px solid #f48771; font-size: 13px; }
.recording-panel.error { background: #2e1a1a; border-color: #f48771; color: #f48771; }
.recording-panel.cooldown { background: #2a2a1a; border-color: #f4d471; color: #f4d471; }
.recording-panel.starting { background: #2a2a1a; border-color: #f4d471; }
.recording-countdown { margin-left: auto; font-weight: 600; color: #f4d471; font-size: 13px; }

.upload-panel { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 6px; border: 1px solid; font-size: 13px; }
.upload-panel.downloading { background: #1a2030; border-color: #5b9bd5; color: #5b9bd5; }
.upload-panel.done { background: #1a2e1a; border-color: #7bc96f; color: #7bc96f; }
.upload-panel.error { background: #2e1a1a; border-color: #f48771; color: #f48771; }
.upload-dot { width: 8px; height: 8px; background: #5b9bd5; border-radius: 50%; animation: pulse 1s infinite; flex-shrink: 0; }
.recording-dot { width: 8px; height: 8px; background: #f48771; border-radius: 50%; animation: pulse 1s infinite; flex-shrink: 0; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

.logs-panel { background: #252525; padding: 10px; border-radius: 6px; flex: 1; min-height: 0; display: flex; flex-direction: column; }
.events-panel { background: #252525; padding: 8px 10px; border-radius: 6px; display: flex; flex-direction: column; }
.events-header, .logs-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.events-header h4, .logs-header h4 { margin: 0; font-size: 13px; color: #888; }
.btn-clear { background: none; border: 1px solid #444; border-radius: 3px; color: #666; font-size: 11px; padding: 2px 8px; cursor: pointer; }
.events-list { max-height: 60px; overflow-y: auto; display: flex; flex-direction: column; gap: 3px; }
.logs-list { flex: 1; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
.event-item { display: flex; gap: 8px; align-items: baseline; padding: 6px 8px; background: #1e1e1e; border-radius: 4px; border-left: 3px solid; font-size: 12px; }
.event-item.miss_avoidance { border-color: #f48771; }
.event-item.false_avoidance { border-color: #f4a571; }
.event-time { color: #555; flex-shrink: 0; }
.event-type { font-weight: 600; flex-shrink: 0; }
.event-reason { color: #aaa; }
.log-item { display: block; font-size: 11px; font-family: monospace; padding: 2px 0; border-bottom: 1px solid #2a2a2a; }
.log-item.relevant { background: #1a2020; border-left: 2px solid #7bc96f; padding-left: 4px; }
.log-time { color: #555; margin-right: 6px; }
.log-text { color: #ccc; white-space: pre-wrap; word-break: break-word; }
.toggle-label { display: flex; align-items: center; gap: 4px; font-size: 11px; color: #666; cursor: pointer; margin-left: auto; margin-right: 8px; }
.toggle-label input { cursor: pointer; }
.empty-hint { color: #555; font-size: 12px; text-align: center; padding: 12px 0; }
</style>
