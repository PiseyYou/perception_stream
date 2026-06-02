<template>
  <div class="panel device-panel">
    <div class="panel-header">
      <div class="panel-title">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="4" y="4" width="16" height="16" rx="2"/>
          <path d="M9 9h6v6H9z"/>
        </svg>
        <span>设备 & Agora 配置</span>
      </div>
    </div>
    <div class="panel-body">
      <div class="form-grid">
        <div class="form-group">
          <label>设备 SN</label>
          <div class="sn-row">
            <select :value="modelValue.sn" @change="update('sn', ($event.target as HTMLSelectElement).value)">
              <option value="LK-MR2P1US000015">LK-MR2P1US000015</option>
              <option value="LK-MR2P1US000016">LK-MR2P1US000016</option>
              <option value="LK-MR2P1US000017">LK-MR2P1US000017</option>
              <option value="LK-MR2P1US000113">LK-MR2P1US000113</option>
              <option value="LK-MR2P1US000115">LK-MR2P1US000115</option>
              <option value="LK-MR6P1US000123">LK-MR6P1US000123</option>
              <option value="LK-MR6P1US000124">LK-MR6P1US000124</option>
              <option value="LK-MR541EU000027">LK-MR541EU000027</option>
              <option value="LK-MR6P1US000286">LK-MR6P1US000286</option>
              <option value="LK-MR641US000367">LK-MR641US000367</option>
            </select>
            <button class="btn-newtab" @click="openNewTab" title="在新标签页打开此 SN">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                <polyline points="15 3 21 3 21 9"/>
                <line x1="10" y1="14" x2="21" y2="3"/>
              </svg>
            </button>
          </div>
        </div>
        <div class="form-group">
          <label>Agora App ID</label>
          <input :value="modelValue.agoraAppId" @input="update('agoraAppId', ($event.target as HTMLInputElement).value)"
                 type="password" placeholder="输入声网 App ID" />
        </div>
        <div class="form-group">
          <label>相机类型</label>
          <select :value="modelValue.camera" @change="update('camera', Number(($event.target as HTMLSelectElement).value))">
            <option :value="0">单目 (K100)</option>
            <option :value="100">三目拼接 (K200+)</option>
          </select>
        </div>
        <div class="form-group">
          <label>分辨率等级</label>
          <select :value="modelValue.resolution" @change="update('resolution', Number(($event.target as HTMLSelectElement).value))">
            <option :value="0">640×480</option>
            <option :value="1">480×320</option>
            <option :value="2">320×240 (默认)</option>
            <option :value="3">240×180</option>
          </select>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
export interface DeviceForm {
  sn: string
  agoraAppId: string
  camera: number
  resolution: number
}

const props = defineProps<{
  modelValue: DeviceForm
}>()

const emit = defineEmits<{
  'update:modelValue': [value: DeviceForm]
}>()

function update(key: keyof DeviceForm, value: any) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}

function openNewTab() {
  const url = new URL(location.href)
  url.searchParams.set('sn', props.modelValue.sn)
  window.open(url.toString(), '_blank')
}
</script>

<style scoped>
.sn-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.sn-row select {
  flex: 1;
}

.btn-newtab {
  flex-shrink: 0;
  padding: 7px 8px;
  background: var(--color-surface-hover);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--color-text-secondary);
  display: flex;
  align-items: center;
  transition: all 0.2s;
}

.btn-newtab:hover {
  color: var(--color-accent);
  border-color: var(--color-accent);
}
</style>
