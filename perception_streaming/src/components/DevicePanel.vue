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
            <div class="sn-combobox" @focusout="handleSnFocusOut">
              <input
                :value="modelValue.sn"
                type="text"
                placeholder="输入或选择设备 SN"
                @focus="snDropdownOpen = true"
                @input="handleSnInput"
              />
              <button
                type="button"
                class="sn-dropdown-toggle"
                title="选择设备 SN"
                @mousedown.prevent="snDropdownOpen = !snDropdownOpen"
              >
                ▼
              </button>
              <div v-if="snDropdownOpen" class="sn-dropdown">
                <button
                  v-for="sn in deviceSnOptions"
                  :key="sn"
                  type="button"
                  class="sn-option"
                  :class="{ active: sn === modelValue.sn }"
                  @mousedown.prevent="selectSn(sn)"
                >
                  {{ sn }}
                </button>
              </div>
            </div>
            <button
              type="button"
              class="btn-add-sn"
              :disabled="!canAddSnOption"
              title="添加到设备 SN 候选列表"
              @click="addCurrentSnToOptions"
            >
              +
            </button>
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
import { computed, ref } from 'vue'

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
  'snAdded': [sn: string]
}>()

function getDeviceSnSuffix(sn: string) {
  const match = sn.match(/\d{4}$/)
  return match ? Number(match[0]) : Number.MAX_SAFE_INTEGER
}

function compareDeviceSn(left: string, right: string) {
  const suffixDiff = getDeviceSnSuffix(left) - getDeviceSnSuffix(right)
  return suffixDiff || left.localeCompare(right)
}

const CUSTOM_DEVICE_SN_OPTIONS_STORAGE_KEY = 'perception_streaming.customDeviceSnOptions'

const DEFAULT_DEVICE_SN_OPTIONS = [
  'LK-MR2P1US000015',
  'LK-MR2P1US000016',
  'LK-MR2P1US000017',
  'LK-MR2P1US000113',
  'LK-MR2P1US000115',
  'LK-MR6P1US000123',
  'LK-MR6P1US000124',
  'LK-MR541EU000027',
  'LK-MR6P1US000286',
  'LK-MR641US000337',
  'LK-MR641US000339',
  'LK-MR641US000367',
]

function loadCustomDeviceSnOptions() {
  try {
    const stored = localStorage.getItem(CUSTOM_DEVICE_SN_OPTIONS_STORAGE_KEY)
    if (!stored) return []
    const parsed = JSON.parse(stored)
    return Array.isArray(parsed) ? parsed.filter((sn): sn is string => typeof sn === 'string' && Boolean(sn.trim())) : []
  } catch {
    return []
  }
}

function saveCustomDeviceSnOptions(options: string[]) {
  localStorage.setItem(CUSTOM_DEVICE_SN_OPTIONS_STORAGE_KEY, JSON.stringify(options))
}

const deviceSnOptions = ref([...new Set([...DEFAULT_DEVICE_SN_OPTIONS, ...loadCustomDeviceSnOptions()])].sort(compareDeviceSn))

const snDropdownOpen = ref(false)
const canAddSnOption = computed(() => {
  const sn = props.modelValue.sn.trim()
  return Boolean(sn && !deviceSnOptions.value.includes(sn))
})

function update(key: keyof DeviceForm, value: any) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}

function handleSnInput(event: Event) {
  snDropdownOpen.value = true
  update('sn', (event.target as HTMLInputElement).value)
}

function selectSn(sn: string) {
  update('sn', sn)
  snDropdownOpen.value = false
}

function addCurrentSnToOptions() {
  const sn = props.modelValue.sn.trim()
  if (!sn || deviceSnOptions.value.includes(sn)) return
  deviceSnOptions.value = [...deviceSnOptions.value, sn].sort(compareDeviceSn)
  saveCustomDeviceSnOptions([...new Set([...loadCustomDeviceSnOptions(), sn])].sort(compareDeviceSn))
  update('sn', sn)
  emit('snAdded', sn)
  snDropdownOpen.value = true
}

function handleSnFocusOut(event: FocusEvent) {
  const nextTarget = event.relatedTarget as Node | null
  if (nextTarget && (event.currentTarget as HTMLElement).contains(nextTarget)) return
  snDropdownOpen.value = false
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

.sn-combobox {
  flex: 1;
  position: relative;
  display: flex;
}

.sn-combobox input {
  width: 100%;
  padding-right: 34px;
}

.sn-dropdown-toggle {
  position: absolute;
  right: 1px;
  top: 1px;
  bottom: 1px;
  width: 32px;
  border: 0;
  border-left: 1px solid var(--color-border);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 11px;
}

.sn-dropdown {
  position: absolute;
  z-index: 30;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  max-height: 220px;
  overflow-y: auto;
  padding: 4px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-lg);
}

.sn-option {
  width: 100%;
  padding: 8px 10px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--color-text);
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  text-align: left;
}

.sn-option:hover,
.sn-option.active {
  background: var(--color-surface-hover);
}

.btn-add-sn {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  padding: 0;
  background: var(--color-surface-hover);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--color-text-secondary);
  font: inherit;
  font-size: 18px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.btn-add-sn:hover:not(:disabled) {
  color: var(--color-accent);
  border-color: var(--color-accent);
}

.btn-add-sn:disabled {
  cursor: not-allowed;
  opacity: 0.45;
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
