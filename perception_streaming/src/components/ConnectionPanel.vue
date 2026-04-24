<template>
  <div class="panel connection-panel" :class="{ collapsed: isCollapsed }">
    <div class="panel-header" @click="isCollapsed = !isCollapsed">
      <div class="panel-title">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/>
          <circle cx="12" cy="12" r="3"/>
        </svg>
        <span>MQTT 连接配置</span>
      </div>
      <svg class="chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M6 9l6 6 6-6"/>
      </svg>
    </div>
    <div class="panel-body" v-show="!isCollapsed">
      <div class="form-grid">
        <div class="form-group">
          <label>协议</label>
          <select :value="modelValue.protocol" @change="update('protocol', ($event.target as HTMLSelectElement).value)">
            <option value="wss">wss://</option>
            <option value="ws">ws://</option>
          </select>
        </div>
        <div class="form-group">
          <label>Broker 地址</label>
          <input :value="modelValue.broker" @input="update('broker', ($event.target as HTMLInputElement).value)"
                 placeholder="mqtt-test.yjserver.com" />
        </div>
        <div class="form-group">
          <label>端口</label>
          <input :value="modelValue.port" @input="update('port', Number(($event.target as HTMLInputElement).value))"
                 type="number" placeholder="8084" />
        </div>
        <div class="form-group">
          <label>Client ID</label>
          <input :value="modelValue.clientId" @input="update('clientId', ($event.target as HTMLInputElement).value)" />
        </div>
        <div class="form-group">
          <label>用户名</label>
          <input :value="modelValue.username" @input="update('username', ($event.target as HTMLInputElement).value)"
                 placeholder="请输入用户名" />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input :value="modelValue.password" @input="update('password', ($event.target as HTMLInputElement).value)"
                 type="password" placeholder="请输入密码" />
        </div>
        <div class="form-group">
          <label>Keep Alive (秒)</label>
          <input :value="modelValue.keepalive" @input="update('keepalive', Number(($event.target as HTMLInputElement).value))"
                 type="number" />
        </div>
        <div class="form-group">
          <label>重连间隔 (ms)</label>
          <input :value="modelValue.reconnectPeriod" @input="update('reconnectPeriod', Number(($event.target as HTMLInputElement).value))"
                 type="number" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'

export interface ConnectionForm {
  protocol: string
  broker: string
  port: number
  clientId: string
  username: string
  password: string
  keepalive: number
  reconnectPeriod: number
}

const props = defineProps<{
  modelValue: ConnectionForm
  connected: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: ConnectionForm]
}>()

const isCollapsed = ref(false)

// Auto-collapse when connected
watch(() => props.connected, (val) => {
  if (val) isCollapsed.value = true
})

// Load default port from server config on mount
onMounted(async () => {
  try {
    const res = await fetch('/offline/config')
    const data = await res.json()
    if (data.ok && data.default_ports?.realtime_monitor) {
      // Only update if current port is still default (10015)
      if (props.modelValue.port === 10015) {
        emit('update:modelValue', { ...props.modelValue, port: data.default_ports.realtime_monitor })
      }
    }
  } catch (e) {
    console.warn('Failed to load config:', e)
  }
})

function update(key: keyof ConnectionForm, value: any) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}
</script>

<style scoped>
.connection-panel .panel-header {
  cursor: pointer;
  user-select: none;
}
.chevron {
  transition: transform 0.3s ease;
}
.collapsed .chevron {
  transform: rotate(-90deg);
}
</style>
