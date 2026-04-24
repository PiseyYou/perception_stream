<template>
  <div class="panel log-console">
    <div class="panel-header">
      <div class="panel-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="4 17 10 11 4 5"/>
          <line x1="12" y1="19" x2="20" y2="19"/>
        </svg>
        <span>日志</span>
        <span class="log-count">{{ logs.length }}</span>
      </div>
      <button class="btn-icon" @click="$emit('clear')" title="清除日志">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18"/>
          <line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
    </div>
    <div class="log-body" ref="logBody">
      <div v-if="logs.length === 0" class="log-empty">暂无日志</div>
      <div v-for="(log, i) in [...logs].reverse()" :key="i" class="log-line"
           :class="{ 'log-error': log.includes('✗') || log.includes('Error') || log.includes('failed'),
                     'log-success': log.includes('✓') || log.includes('成功') || log.includes('success') || log.includes('已连接') }">
        {{ log }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  logs: string[]
}>()

defineEmits<{
  clear: []
}>()
</script>

<style scoped>
.log-console {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.log-count {
  background: var(--color-surface-hover);
  color: var(--color-text-muted);
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 100px;
  font-weight: 500;
}

.log-body {
  flex: 1;
  min-height: 0;
  max-height: none;
  overflow-y: auto;
  padding: 8px 12px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 12px;
  line-height: 1.7;
  background: var(--color-terminal-bg);
  color: var(--color-terminal-text);
}

.log-empty {
  color: var(--color-text-muted);
  text-align: center;
  padding: 24px;
}

.log-line {
  white-space: pre-wrap;
  word-break: break-all;
}

.log-error { color: #f87171; }
.log-success { color: #4ade80; }

.btn-icon {
  background: var(--color-surface-hover);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 6px;
  cursor: pointer;
  color: var(--color-text-secondary);
  transition: all 0.2s;
}
.btn-icon:hover {
  color: var(--color-text);
  background: var(--color-border);
}
</style>
