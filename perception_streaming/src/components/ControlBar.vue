<template>
  <div class="control-bar">
    <button type="button" class="btn" :class="mqttConnected ? 'btn-active' : 'btn-success'"
            :disabled="mqttConnected" @click="$emit('connectMqtt')">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M5 12.55a11 11 0 0114.08 0"/>
        <path d="M1.42 9a16 16 0 0121.16 0"/>
        <path d="M8.53 16.11a6 6 0 016.95 0"/>
        <circle cx="12" cy="20" r="1"/>
      </svg>
      {{ mqttConnected ? 'MQTT 已连接' : '连接 MQTT' }}
    </button>

    <button type="button" class="btn btn-danger" :disabled="!mqttConnected" @click="$emit('disconnectMqtt')">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="1" y1="1" x2="23" y2="23"/>
        <path d="M16.72 11.06A10.94 10.94 0 0119 12.55"/>
        <path d="M5 12.55a10.94 10.94 0 015.17-2.39"/>
        <path d="M10.71 5.05A16 16 0 0122.56 9"/>
        <path d="M1.42 9a15.91 15.91 0 014.7-2.88"/>
        <path d="M8.53 16.11a6 6 0 016.95 0"/>
        <circle cx="12" cy="20" r="1"/>
      </svg>
      断开 MQTT
    </button>

    <div class="divider"></div>

    <button type="button" class="btn btn-primary" :disabled="!mqttConnected || videoStarted"
            @click="$emit('startVideo')">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polygon points="5 3 19 12 5 21 5 3"/>
      </svg>
      开启视频
    </button>

    <button type="button" class="btn btn-warning" :disabled="!videoStarted" @click="$emit('stopVideo')">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="6" y="4" width="4" height="16"/>
        <rect x="14" y="4" width="4" height="16"/>
      </svg>
      关闭视频
    </button>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  mqttConnected: boolean
  videoStarted: boolean
}>()

defineEmits<{
  connectMqtt: []
  disconnectMqtt: []
  startVideo: []
  stopVideo: []
}>()
</script>

<style scoped>
.control-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.divider {
  width: 1px;
  height: 24px;
  background: var(--color-border);
  margin: 0 4px;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
  color: #fff;
}

.btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  transform: none !important;
}

.btn:not(:disabled):hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.btn:not(:disabled):active {
  transform: translateY(0);
}

.btn-success { background: linear-gradient(135deg, #22c55e, #16a34a); }
.btn-active  { background: linear-gradient(135deg, #4b5563, #374151); }
.btn-danger  { background: linear-gradient(135deg, #ef4444, #dc2626); }
.btn-primary { background: linear-gradient(135deg, #3b82f6, #2563eb); }
.btn-warning { background: linear-gradient(135deg, #f59e0b, #d97706); }

@media (max-width: 640px) {
  .control-bar {
    gap: 6px;
  }
  .btn {
    padding: 6px 12px;
    font-size: 12px;
  }
  .divider { display: none; }
}
</style>
