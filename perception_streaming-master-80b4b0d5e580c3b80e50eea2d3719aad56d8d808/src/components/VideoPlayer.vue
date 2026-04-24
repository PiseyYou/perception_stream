<template>
  <div class="video-player" :class="{ 'is-wide': isWide }">
    <div class="video-header">
      <div class="video-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="23 7 16 12 23 17 23 7"/>
          <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
        </svg>
        <span>视频画面</span>
        <span v-if="streaming" class="live-badge">
          <span class="live-dot"></span>
          LIVE
        </span>
      </div>
      <button v-if="streaming" class="btn-icon" @click="toggleFullscreen" title="全屏">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"/>
        </svg>
      </button>
    </div>
    <div ref="containerRef" class="video-wrapper">
      <div id="video-container" class="video-container"></div>
      <div v-if="!streaming" class="video-placeholder">
        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity="0.3">
          <polygon points="23 7 16 12 23 17 23 7"/>
          <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
        </svg>
        <p>等待视频流...</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{
  streaming: boolean
  camera: number
}>()

const containerRef = ref<HTMLElement | null>(null)
const isWide = computed(() => props.camera === 100)

function toggleFullscreen() {
  const el = containerRef.value
  if (!el) return
  if (!document.fullscreenElement) {
    el.requestFullscreen()
  } else {
    document.exitFullscreen()
  }
}
</script>

<style scoped>
.video-player {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  overflow: hidden;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.video-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
}

.video-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 14px;
}

.live-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 100px;
  letter-spacing: 0.5px;
}

.live-dot {
  width: 6px;
  height: 6px;
  background: #ef4444;
  border-radius: 50%;
  animation: pulse-live 1.5s infinite;
}

@keyframes pulse-live {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

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

.video-wrapper {
  position: relative;
  width: 100%;
  flex: 1;
  min-height: 0;
  background: #000;
}

.is-wide .video-wrapper {
  /* no aspect-ratio override needed, fills parent */
}

.video-container {
  position: absolute;
  inset: 0;
}

.video-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--color-text-muted);
  font-size: 14px;
}
</style>
