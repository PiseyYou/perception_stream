# Standalone Prelabel Upload Workbench

## Goal

Create a standalone Vite + Vue 3 frontend for the existing prelabel upload workflow. It must preserve the functional behavior of the current `PrelabelPipelinePanel` while removing unrelated perception-streaming navigation and panels.

## Scope

The new project exposes one full-screen workbench with these areas:

- Service status: client token, container status, GPU status, refresh, and container restart.
- CVAT setup: server credentials, active server selection, and available user refresh.
- Label management: list existing labels, create a new label, and delete a label after confirmation.
- Task setup: task prefix, fast or accurate inference mode, segment size, task owner, stereo output mode, serial execution, and K100 mode.
- Input source: server directories, selected image files or folders, image archives, robot image scans, and ROS Bag files.
- Execution: submit either the complete pipeline or an upload-to-CVAT-only run, track the active run, show owned queued runs, cancel an owned running or queued run, and display runtime logs.
- CVAT export: start a CVAT export, list browser-owned export archives, download them with the client token, and delete owned exports.

The standalone application does not include live streaming, log analysis, offline bag analysis, obstacle monitoring, or cross-application navigation.

## Architecture

The project is a Vite + Vue 3 application. The entry route renders `PrelabelWorkbench` directly and has no internal router requirement.

`PrelabelWorkbench` owns shared run state and composes focused child components:

- `ServiceStatusBar`
- `CvatConfigurationPanel`
- `LabelManagementPanel`
- `TaskConfigurationPanel`
- `SourceSelectionPanel`
- `RunControlPanel`
- `RunQueueAndLogPanel`
- `CvatExportPanel`

`src/api/prelabelApi.ts` is the only browser-facing API layer. It owns request construction, JSON error normalization, upload requests, endpoint URL construction, and the `/offline/config` request used to obtain the default robot SSH port. `src/composables/usePrelabelRun.ts` owns owner-token-authenticated SSE connection and lifecycle cleanup for live run status and logs, plus run-list refresh after an SSE error. Shared interfaces live in `src/types/prelabel.ts`.

## Backend Integration

The new frontend calls the current prelabel backend without changing its contracts. In development, Vite proxies `/prelabel` to `http://192.168.55.245:8769` and `/offline` to the existing offline-config backend. `VITE_PRELABEL_API_BASE` overrides the prelabel base path or origin for deployment; `VITE_OFFLINE_API_BASE` does the same for offline configuration. If offline configuration cannot be read, robot source selection retains the component's local default port.

The client token is generated once and persisted in browser storage. Every ownership-sensitive request and download URL carries that token. API errors are normalized into contextual inline messages and leave current form values intact.

## Interaction Rules

- A selected CVAT server and valid segment size are required before a run is submitted.
- Complete pipeline submissions use an empty `skip_steps`; upload-only submissions use the current `[2, 3, 4]` `skip_steps` contract. Both submit all existing shared task fields, including `serial_mode`, `prepare_stereo`, `k100`, and `stereo_mode`.
- Inputs remain editable while another run executes so a later task can be queued.
- Each source type validates its own inputs before it submits or uploads.
- Submitted upload identifiers are cleared after a successful submission so a future queued task receives a new upload directory.
- The primary cancel action targets the user's active run first, then the first owned queued run.
- An owned submitted run opens `/prelabel/stream/{runId}?token={clientToken}` with SSE for live status and logs. The stream closes when it emits terminal data or the component unmounts; on stream error, the app records the interruption and refreshes the run list.
- Destructive operations are disabled while their matching request is in flight.

## Visual Design

Use the approved one-page workbench layout: a compact service toolbar above a two-column body. The left column contains CVAT, labels, and task configuration; the wider right column contains input source selection, primary run actions, queue state, and logs. Export controls sit below execution controls. The visual language is dense and operational, with persistent status indicators and no card nesting.

## Verification

Unit tests cover API request payloads, complete versus upload-only `skip_steps`, URL/token construction, source validation, SSE URL/lifecycle behavior, offline-config fallback, and queue-cancellation target selection. Component tests cover validation feedback, label deletion confirmation, in-flight disabled states, and active/queued run rendering. A build check verifies the standalone project compiles. A manual smoke test against the existing backend verifies status retrieval, CVAT user refresh, a source submission path, live SSE updates, and owned export download URL generation.

## Acceptance Criteria

- The standalone project starts independently and renders only the prelabel workbench.
- It can use the existing `/prelabel` backend through the configured proxy or deployment base URL.
- All listed current workflow areas are available with their existing request behavior.
- A user can submit and observe an owned run, queue another run, and cancel an owned run.
- Upload and export ownership is protected by the persisted client token.
- Automated tests and the production build succeed.
