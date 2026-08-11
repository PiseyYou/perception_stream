# Online Prelabel A/B Shadow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep MPFormer as the online default while one upload batch creates an isolated Alpha50 candidate task and an anonymous, reproducible human comparison.

**Architecture:** Freeze one immutable image snapshot, copy it per branch, run baseline then candidate through the GPU queue, and create tracked CVAT tasks. Candidate inference performs Alpha50 768/832, flip TTA semantic fusion and validated mask-to-polygon export. A separate anonymous-review API hides branch identities until the review is complete.

**Tech Stack:** Python 3.10, existing YOLOv5 segmentation runtime, PyTorch, Pillow/NumPy, CVAT SDK/HTTP, Vue 3 + TypeScript, unittest, Node assert.

---

## Files

- Create `robot_monitor/prelabel_pipeline/shadow_batch.py` for immutable snapshots and branch inputs.
- Create `robot_monitor/prelabel_pipeline/alpha50_batch.py` for candidate preflight, inference and CVAT XML.
- Create `robot_monitor/prelabel_pipeline/shadow_review.py` for sample selection, anonymous mapping and decision.
- Modify `core.py`, `run_state.py` and `routes.py` for orchestration, persistence and APIs.
- Modify `prelabel_config.yaml` for hash-pinned candidate settings and canonical labels.
- Modify `PrelabelPipelinePanel.vue` plus `scripts/test_prelabel_panel_modes.mjs` for shadow mode and review entry.
- Add `test_prelabel_shadow_batch.py`, `test_prelabel_alpha50_batch.py`, and `test_prelabel_shadow_review.py`; extend core, routes and run-state tests.

### Task 1: Immutable batch snapshot

**Files:** Create `shadow_batch.py`; modify `run_state.py`; test `test_prelabel_shadow_batch.py`.

- [ ] Write failing tests that `freeze_batch()` writes sorted relative paths, SHA-256 values and dimensions; then delete a candidate branch file and assert the snapshot and baseline copy remain intact.
- [ ] Run `python3 -m unittest robot_monitor.tests.test_prelabel_shadow_batch -v`; expect import failure for `shadow_batch`.
- [ ] Implement `freeze_batch(source, snapshot_root)` and `materialize_branch_input(snapshot, branch, work_root)`. Reject unsupported/corrupt/duplicate images; atomically save a serializable manifest. Do not give branches writable access to the snapshot.
- [ ] Extend `run_state` disk records with mode, batch ID, snapshot hash/path, branch attempt/status and review state, preserving legacy records.
- [ ] Run `python3 -m unittest robot_monitor.tests.test_prelabel_shadow_batch robot_monitor.tests.test_prelabel_run_state -v`; expect PASS.
- [ ] Commit only these files with message `feat: 固化预标注 A/B 批次快照`.

### Task 2: Candidate model and label contracts

**Files:** Create `alpha50_batch.py`; modify `prelabel_config.yaml`; test `test_prelabel_alpha50_batch.py`.

- [ ] Write failing tests for a missing weight SHA-256, missing 768/832 scale pair, changed weight hash, unknown source class and missing CVAT label.
- [ ] Run `python3 -m unittest robot_monitor.tests.test_prelabel_alpha50_batch -v`; expect missing adapter failure.
- [ ] Add `candidate_alpha50` configuration: framework root, fixed checkpoint(s), SHA-256, scales `[768, 832]`, flip TTA, interpolation, ignore/background policy, contour parameters and source-ID/canonical/CVAT mapping snapshot.
- [ ] Implement preflight that validates files/hashes, framework imports, CUDA/VRAM/disk capacity and the pre-create CVAT label definition. Implement post-create schema validation of each actual CVAT task. Pre-create failure creates no B task; post-create failure blocks import and invokes tracked cleanup.
- [ ] Write an immutable candidate provenance manifest before inference and test it contains the weight SHA-256, framework code revision or image digest, every TTA/fusion/export parameter, mapping snapshot hash and frozen input snapshot hash. Persist its digest in the branch state; never derive it later from mutable configuration.
- [ ] Run the candidate tests; expect PASS. Commit with message `feat: 添加 Alpha50 影子模型契约门禁`.

### Task 3: Candidate inference and validated export

**Files:** Modify `alpha50_batch.py`; test `test_prelabel_alpha50_batch.py`.

- [ ] Write failing tests that four logits (two scales, normal/flip) are resized, unflipped and averaged deterministically; and that component splitting, min-area filtering and out-of-bounds XML rejection work.
- [ ] Run the focused unittest and confirm it fails because fusion/export is missing.
- [ ] Implement inference: each branch image gets 768/832 normal plus flip inputs, output logits are returned to original geometry, averaged, argmaxed under the background rule, and stored as raw masks with per-class counts.
- [ ] Implement deterministic CVAT Images 1.1 export using connected components and configured simplification. Before import validate image name/dimension/uniqueness, label schema and polygon coordinate bounds.
- [ ] Run `python3 -m unittest robot_monitor.tests.test_prelabel_alpha50_batch -v`; expect PASS. Commit with message `feat: 导出 Alpha50 影子标注到 CVAT`.

### Task 4: A/B orchestration, recovery and cleanup

**Files:** Modify `core.py`, `run_state.py`, `routes.py`; test `test_prelabel_core.py`, `test_prelabel_routes.py`.

- [ ] Write failing tests that a `shadow_ab` run has equal snapshot hashes for A/B, serializes GPU use, keeps A successful when B fails, and does not enable review unless both branches validate.
- [ ] Add failing tests that mock the CVAT task/frame list plus frame-byte download: every A and B frame must match the snapshot's frame ID/name/order/dimensions and the SHA-256 recomputed from the actual CVAT frame bytes before XML import or review is allowed. Do not treat frame metadata as a content hash unless the deployed CVAT API has a verified digest field.
- [ ] Add failing single-image-failure tests: branch outcomes must persist a per-image status/size/hash manifest, the common-success intersection must exclude every A-only or B-only failed image, and the review manifest must use only that persisted intersection.
- [ ] Run the focused core/routes tests; expect failure because `shadow_ab` is absent.
- [ ] Add a shadow-specific orchestration entry point while preserving existing `run_pipeline`. Freeze once; materialize branch copies; reuse baseline MPFormer logic for A; run B; create and track separate tasks; run post-create schema/XML checks and imports.
- [ ] After every branch upload, retrieve CVAT frame metadata and download/read the actual task frame bytes. Compare frame ID, name, order, dimensions and recomputed SHA-256 item-by-item with the frozen snapshot before allowing XML import. Persist verified per-image success outcomes (relative path, SHA-256, dimensions, task frame ID) and construct one immutable common-success intersection manifest for blind review.
- [ ] Key submission, restoration, explicit branch retry and orphan cleanup by `batch_id + branch_id + snapshot_hash`; return existing active/terminal work only for that complete key. Permit explicit failed-branch retries only, record attempts, and mark/clean orphan CVAT tasks on cancel/import/schema failure. Never auto-create tasks during process restoration.
- [ ] Run `python3 -m unittest robot_monitor.tests.test_prelabel_core robot_monitor.tests.test_prelabel_routes robot_monitor.tests.test_prelabel_run_state -v`; expect PASS. Commit with message `feat: 编排预标注 A/B 影子任务`.

### Task 5: Anonymous blind review

**Files:** Create `shadow_review.py`; modify `routes.py`; test `test_prelabel_shadow_review.py` and routes tests.

- [ ] Write failing tests that a fixed seed chooses the same 30 common images and that the public payload contains neither branch/model/task/path identity; add tests for one submission per reviewer, early reveal rejection and no-decision.
- [ ] Run `python3 -m unittest robot_monitor.tests.test_prelabel_shadow_review -v`; expect module failure.
- [ ] Generate X/Y mappings server-side; sample 30 (or all below 30); store mapping only in owner state. Accept `X better/Y better/tie/undecidable` plus issue tags. Require 24 valid records and a 20-point candidate win margin; otherwise decide `无结论`.
- [ ] Add anonymous review/submit endpoints and an owner-only reveal endpoint. Do not emit CVAT URLs, task names, branch IDs, paths or model metadata before reveal.
- [ ] Run review/routes tests; expect PASS. Commit with message `feat: 添加预标注 A/B 匿名盲评`.

### Task 6: Web flow and verification

**Files:** Modify `src/components/PrelabelPipelinePanel.vue`, `scripts/test_prelabel_panel_modes.mjs`, and `docs/deployment-guide.md`.

- [ ] Write failing Node assertions for `shadow_ab` selection, review endpoint wiring, X/Y display and the absence of branch identity from the dedicated review surface.
- [ ] Run `node scripts/test_prelabel_panel_modes.mjs`; expect assertion failure.
- [ ] Add baseline/shadow mode selection, branch status and owner-only task links after reveal. Create a dedicated anonymous review view with only artifacts, X/Y choices and issue tags. Keep existing upload/queue behavior unchanged.
- [ ] Document candidate hash installation, GPU preflight, A/B launch, blind review/reveal and candidate-only failure cleanup.
- [ ] Run `python3 -m unittest discover -s robot_monitor/tests -p 'test_*.py' -v`, then `node scripts/test_prelabel_panel_modes.mjs`, then `npm run build`, then `git diff --check`; expect all commands to exit 0.
- [ ] Commit with message `feat: 接入预标注 A/B 影子验证界面`.
