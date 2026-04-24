# Design: BagOfflineViewer Layout Decoupling and Preview Enhancement

## Goal
Ensure the `BagOfflineViewer` component maintains a consistent UI layout even when an input folder contains no point cloud files (missing `manifest.json`). Enable "Night Offline Debug" and image preview functionality in this state.

## Proposed Changes

### 1. Template Decoupling (src/components/BagOfflineViewer.vue)
- Remove `:class="{ 'bov-hidden': !manifest }"` from the main `.bov-body` container. 
- Update `v-show="!manifest"` for the loading state to only appear when a scan is actively running, or replace it with a more granular check.
- Ensure the `.side-panel` and `.detail-panel` are always rendered.

### 2. Preview Logic (src/composables/useBagOfflineSSE.ts)
- The `startOfflineTest` function will now only require `offlineInputDir` to be set, independent of the `manifest` state.
- Results in `offlinePanelImages` will trigger visibility of the `otp-inline-results` block in the detail view regardless of `selected` frame state.

### 3. Detail View Fallbacks
- In the absence of a selected frame (`selected === null`), the detail view will focus on the `detail-col-right` where `avoidingImages` or `offlinePanelImages` are displayed.
- If an image from the offline test is clicked, it will be shown in the large preview area even if no point cloud data is available.

## Success Criteria
- Selecting a folder without PCDs does not hide the UI.
- Clicking the "Night Offline Debug" button starts the test correctly.
- Preview images generated during the test are displayed and expandable within the detail panel.
