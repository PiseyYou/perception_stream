# BagOfflineViewer Layout Decoupling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure BagOfflineViewer maintains a consistent layout even when point cloud files are missing, and that the preview/image display functions correctly after clicking the debug button.

**Architecture:** Decouple the main UI container from the `manifest` reactive state and move conditional visibility to specific data-dependent sub-components. Update SSE handling to populate previews independently of manifest selection.

**Tech Stack:** Vue 3, TypeScript, Vite

---

### Task 1: Decouple Main Layout from Manifest State

**Files:**
- Modify: `src/components/BagOfflineViewer.vue:96-242`

**Step 1: Remove layout-hiding classes**

Modify line 96:
```html
<div class="bov-body" :class="{ 'bov-hidden': !manifest && !offlinePanelImages.length }">
```
(Actually, we want it to show if either manifest or offline images exist, or just always show the grid.)
Update line 96 to:
```html
<div class="bov-body">
```
Update line 241 to show loading only if manifest is null AND we haven't started an offline test:
```html
<div class="bov-loading" v-show="!manifest && !offlinePanelImages.length && !running">加载中...</div>
```

**Step 2: Add guard for Thumbnail Strip**

Modify line 98:
```html
<div class="thumb-strip" v-if="manifest">
```

**Step 3: Commit**

```bash
git add src/components/BagOfflineViewer.vue
git commit -m "feat: decouple BagOfflineViewer layout from manifest state"
```

### Task 2: Update Detail Panel for Independent Preview

**Files:**
- Modify: `src/components/BagOfflineViewer.vue:173-210`

**Step 1: Ensure result images show even without 'selected' frame**

Wrap the result blocks in a container that doesn't depend on `selected` if `offlinePanelImages` has data.
Modify line 192:
```html
<div v-if="offlinePanelImages.length" class="view-block otp-inline-results">
```
(This is already somewhat independent, but ensure it's not nested in a `v-if="selected"` block. The current code has it inside `.detail-views` which is inside `.detail-panel`.)

**Step 2: Commit**

```bash
git add src/components/BagOfflineViewer.vue
git commit -m "feat: allow preview results to show without selected frame"
```

### Task 3: Verify and Fix Offline Test Trigger

**Files:**
- Modify: `src/composables/useBagOfflineSSE.ts:72-82`
- Modify: `src/components/BagOfflineViewer.vue:17-19`

**Step 1: Remove manifest requirement for startOfflineTest**

In `src/composables/useBagOfflineSSE.ts`, ensure `startOfflineTest` only checks `offlineInputDir.value`.

**Step 2: Update template button state**

In `src/components/BagOfflineViewer.vue`, ensure the button is enabled if `offlineInputDir` is set.

**Step 3: Commit**

```bash
git add src/composables/useBagOfflineSSE.ts src/components/BagOfflineViewer.vue
git commit -m "fix: allow offline test to run without manifest"
```
