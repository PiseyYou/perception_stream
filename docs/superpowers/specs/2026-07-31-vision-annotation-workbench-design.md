# Vision Annotation Workbench Design

## Goal

Build a standalone offline-first image-folder auto-annotation workbench. It produces high-quality CVAT-compatible annotations for the existing perception label taxonomy. Accuracy of both class and mask boundary takes priority over throughput. A small, selected subset of hard samples may be sent to an external vision API.

The workbench is separate from `perception_streaming`, but reuses its CVAT XML contract, label definitions, and corrected CVAT data as training and evaluation input.

## Scope

Version 1 accepts a folder of independent still images. It does not process video, temporal tracking, stereo matching, ROS Bag ingestion, or robot-side inference. Those are deliberately deferred so the first evaluation is reproducible and isolates image-level annotation quality.

Outputs are:

- CVAT XML and raster masks for accepted annotations.
- Per-image and per-instance provenance, confidence, and quality reports in JSON.
- A review manifest containing samples that need human work in CVAT.
- A training manifest built from human corrections and high-value errors.

## Architecture

```text
Image folder
  -> ingestion and quality checks
  -> local semantic/instance proposal workers
  -> candidate fusion and class mapping
  -> boundary refinement
  -> uncertainty scoring
  -> selective external visual review
  -> policy validation
  -> CVAT export, reports, and review queue
```

### Model roles

`Mask2Former` is the principal local model. Version 1 runs it in panoptic mode: configured `thing` labels produce non-overlapping instances and configured `stuff` labels produce semantic regions. It is fine-tuned on the project label taxonomy and emits class logits, masks, and confidence maps. The taxonomy explicitly declares the thing/stuff policy; it is not inferred at runtime.

`Grounding DINO` is a proposal model. It receives controlled prompt aliases for the existing labels and looks for long-tail or small-object candidates missed by the main model.

`SAM 2`, or a newer SAM-compatible implementation behind the same adapter, refines candidate boundaries from masks, boxes, and positive/negative points. It never invents a project label.

An external vision API is a reviewer, not the primary segmenter. It receives only selected crop images, candidate-mask overlays, and the closed project label list. Its required JSON response decides whether a candidate is valid, which allowed label is most likely, whether a possible missed target exists, and whether human review is required. A missed-target response must include a normalized bounding box and, when the provider supports it, positive points or a coarse polygon that can be passed to SAM; otherwise it only creates a human-review proposal.

### Candidate contract

All adapters produce a versioned `CandidateAnnotation` record. Masks are stored as compressed RLE artifacts in image pixel coordinates with origin at the top-left; polygons are derived artifacts and use the same coordinate system. Holes are represented as separate rings, and every record carries the source image dimensions and an integrity hash:

```json
{
  "schema_version": 1,
  "image_id": "relative/path.jpg",
  "image_sha256": "...",
  "width": 1920,
  "height": 1080,
  "instance_id": "i-0007",
  "mask": {"format": "coco_rle", "artifact": "masks/i-0007.json", "sha256": "..."},
  "polygon": {"rings": [[[12.0, 31.0], [14.0, 33.0]]], "derived": true},
  "label": "canonical internal label",
  "class_confidence": 0.0,
  "boundary_confidence": 0.0,
  "sources": ["mask2former", "grounding_dino", "sam"],
  "review_state": "accepted|external_review|human_review|failed",
  "error": null,
  "provenance": {"run_id": "...", "model_versions": {}, "checkpoint_hashes": {}, "config_hash": "..."}
}
```

The canonical label is validated against the existing `labels.csv`, `labels_mapping.yaml`, and export mapping files before export. The taxonomy schema adds canonical name, aliases, ID, `thing_or_stuff`, allowed overlaps, high-risk flag, minimum area, and exclusivity groups. No adapter may emit labels outside the configured taxonomy.

### Fusion and quality policy

1. Calibrate class confidence on the validation split. Default thresholds are config values: `accept_class >= 0.85`, `external_review in [0.55, 0.85)`, and `human_review < 0.55`; per-class overrides are required for high-risk labels.
2. Fuse candidates deterministically by descending calibrated confidence, then source priority, then stable instance ID. For same-class overlaps, keep the higher-confidence mask and merge only when IoU is at least `0.70`; for different classes, consult the taxonomy exclusivity group and route unresolved overlaps to review.
3. Grounding DINO contributes boxes only. SAM prompts are generated from the box plus positive points sampled inside the candidate and negative points outside it. A refinement is accepted only if its mask IoU with the source mask is at least `0.50`, its area ratio is within `[0.25, 4.0]`, and contour validation passes.
4. Send only difficult crop regions to the external reviewer. Selection is deterministic from the run seed and hard limits: at most 10% of images, 3 regions per image, and a configured daily cost budget. A reviewer may confirm/relabel an existing candidate or propose a box/points for a missed target; it cannot publish a free-form label or polygon.
5. Apply project policy after model decisions: allowed labels, class exclusivity, minimum area, contour validity, and preserve-high-risk-obstacle rules.
6. Export accepted candidates; publish neither `failed` nor unresolved `human_review` candidates as final truth. They are linked into the review manifest instead of silently deleted.

## Data and privacy

External requests contain an individual image crop or a minimized downscaled image, a mask overlay, the crop-to-image transform, and a closed label list; no customer or robot metadata is sent. Requests are capped at 1536 px on the long side and 3 regions per image. Each request includes provider/model/version, an idempotency key, a 20-second timeout, and a bounded retry budget of two attempts. Responses are schema-validated and rejected if they contain unknown labels, out-of-range coordinates, or prompt-injected instructions. API credentials live only in environment variables or a local secret store. Raw requests, credentials, and image bytes are excluded from ordinary logs. The adapter supports a disabled mode; on timeout or budget exhaustion the run continues locally and marks the affected candidate `failed` or `human_review`.

## Evaluation and learning loop

The project maintains a frozen, content-hash-addressed human-labeled evaluation set split by scene conditions, including difficult lighting, vegetation, road boundaries, and small obstacles. Images from the same source sequence stay in one split to prevent leakage. Instance metrics match predictions to ground truth at mask IoU `0.50`; semantic metrics are pixel mIoU. Success is measured by:

- mIoU by class and macro average.
- Boundary F-score.
- High-risk obstacle recall and false-negative rate.
- Review rate and post-review change rate.
- External API cost and elapsed time per image.

The acceptance gate is set against the current MP-Former baseline: no regression in high-risk recall, at least 10 percentage points improvement in boundary F-score on hard scenes, and a documented API review rate/cost. CVAT corrections are versioned by source task/job and annotation hash, with corrected images excluded from the frozen evaluation split. A hard-example miner prioritizes disagreements, low-confidence regions, and human-corrected candidates for the next Mask2Former training manifest.

## Project layout

The implementation root will be `vision_annotation_workbench/` alongside `perception_streaming/`.

```text
vision_annotation_workbench/
  app/                 CLI and run orchestration
  adapters/            Mask2Former, Grounding DINO, SAM, external API adapters
  domain/              candidate schema, taxonomy, policy, scoring
  pipelines/           ingest, infer, fuse, review, export, train manifests
  exporters/           CVAT XML and mask output
  configs/             model profiles and policy profiles
  tests/               unit, contract, fixture, and end-to-end tests
  docs/                operator and model documentation
  schemas/             candidate, run, taxonomy, and review JSON schemas
  artifacts/           content-addressed masks, overlays, and reports
```

## Failure handling

Every run has an immutable manifest and per-step status, including input file hashes, canonical ordering, model/checkpoint/config hashes, thresholds, random seed, and taxonomy version. Ingestion accepts JPEG/PNG/TIFF/BMP, applies EXIF orientation once, converts to RGB, rejects corrupt files, de-duplicates by content hash, refuses symlinks that escape the selected root, and processes recursively in normalized path order. A single image failure is recorded and continues; an all-failure run is non-publishable. Local-model or API failure cannot discard a candidate: it is retained with an explicit `failed` state and error code and is routed to human review. Runs support cancellation, resume from completed artifacts, bounded GPU batching, disk quotas, and configurable artifact retention.

## CVAT contract

The exporter is pinned to CVAT for images 1.1. Every `<image>` carries the canonical relative filename, width, and height. Polygon shapes contain closed pixel-coordinate points, with one polygon per ring; holes are emitted as separate supported mask artifacts and are round-tripped through the raster-mask sidecar when CVAT XML cannot represent them without loss. Labels are emitted by canonical name using the taxonomy mapping, attributes include `source`, `confidence`, `review_state`, and `instance_id`, and images/shapes are sorted deterministically. Review manifests link each image to its exported task/job and candidate IDs. Contract tests import and export fixtures and verify dimensions, labels, polygons, masks, holes, and attributes round-trip.

## Delivery phases

1. Scaffold the CLI, typed schemas, configuration, taxonomy adapter, content-addressed artifact store, and CVAT exporter with fixtures.
2. Add Mask2Former inference, confidence calibration, deterministic replay, and evaluation harness.
3. Add Grounding DINO proposals, SAM boundary refinement, deterministic fusion, policy checks, and GPU-unavailable fallback tests.
4. Add selective external-review adapter, privacy/log-redaction tests, API contract tests, hard quotas, retries, and review manifests.
5. Add CVAT correction ingestion, hard-example mining, leakage-safe training manifests, cancellation/resume, and end-to-end recovery tests.

## Non-goals for version 1

- Replacing CVAT.
- Full-image calls to external APIs by default.
- Video propagation or multi-view consistency.
- Real-time robot deployment.
