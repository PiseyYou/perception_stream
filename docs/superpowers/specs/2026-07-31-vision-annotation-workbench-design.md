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

`Mask2Former` is the principal local semantic/instance segmentation model and is fine-tuned on the project label taxonomy. It emits class logits, masks, and confidence maps.

`Grounding DINO` is a proposal model. It receives controlled prompt aliases for the existing labels and looks for long-tail or small-object candidates missed by the main model.

`SAM 2`, or a newer SAM-compatible implementation behind the same adapter, refines candidate boundaries from masks, boxes, and positive/negative points. It never invents a project label.

An external vision API is a reviewer, not the primary segmenter. It receives only selected crop images, candidate-mask overlays, and the closed project label list. Its required JSON response decides whether a candidate is valid, which allowed label is most likely, whether a possible missed target exists, and whether human review is required.

### Candidate contract

All adapters produce a shared `CandidateAnnotation` record:

```json
{
  "image_id": "relative/path.jpg",
  "mask": "artifact reference",
  "label": "canonical internal label",
  "class_confidence": 0.0,
  "boundary_confidence": 0.0,
  "sources": ["mask2former", "grounding_dino", "sam"],
  "review_state": "accepted|external_review|human_review",
  "provenance": {}
}
```

The canonical label is validated against the existing label CSV and mapping files before export. No adapter may emit labels outside the configured taxonomy.

### Fusion and quality policy

1. Keep high-confidence Mask2Former masks when the candidate geometry is stable.
2. Fuse overlapping proposal masks only when the class mapping agrees or the configured class hierarchy permits it.
3. Pass boundary-fragmented, thin, small, or low-IoU candidates to the SAM adapter.
4. Send only difficult crop regions to the external reviewer. A region is difficult if model class predictions conflict, model-mask IoU is low, class confidence is low, a prompt detector finds a target in a predicted-empty zone, or geometric validation fails.
5. Apply project policy after model decisions: allowed labels, class exclusivity, area thresholds, contour validity, and preserve-high-risk-obstacle rules.
6. Export accepted candidates; mark unresolved candidates for CVAT instead of silently deleting them.

## Data and privacy

External requests contain an individual image crop or a minimized downscaled image, a mask overlay, a closed label list, and no customer or robot metadata. API credentials live only in environment variables or a local secret store. Raw requests, credentials, and image bytes are excluded from ordinary logs. The external-review adapter supports a disabled mode for fully offline runs.

## Evaluation and learning loop

The project maintains a frozen human-labeled evaluation set split by scene conditions, including difficult lighting, vegetation, road boundaries, and small obstacles. Success is measured by:

- mIoU by class and macro average.
- Boundary F-score.
- High-risk obstacle recall and false-negative rate.
- Review rate and post-review change rate.
- External API cost and elapsed time per image.

CVAT corrections are ingested as new ground truth. A hard-example miner prioritizes disagreements, low-confidence regions, and human-corrected candidates for the next Mask2Former training set.

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
```

## Failure handling

Every run has an immutable manifest and per-step status. Local-model or API failure cannot discard a candidate: it is retained with a failed-review state and is routed to human review. API failures retry with bounded exponential backoff; after the retry budget, the run continues in local-only mode. Mask/export validation failures block publication and preserve artifacts for diagnosis.

## Delivery phases

1. Scaffold the CLI, configuration, taxonomy adapter, artifact store, and CVAT exporter with fixtures.
2. Add Mask2Former inference, confidence capture, and evaluation harness.
3. Add Grounding DINO proposals, SAM boundary refinement, fusion, and policy checks.
4. Add selective external-review adapter, privacy controls, and review manifests.
5. Add CVAT correction ingestion, hard-example mining, and reproducible training manifests.

## Non-goals for version 1

- Replacing CVAT.
- Full-image calls to external APIs by default.
- Video propagation or multi-view consistency.
- Real-time robot deployment.
