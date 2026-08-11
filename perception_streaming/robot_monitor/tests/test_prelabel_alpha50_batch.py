import hashlib
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import yaml

TEST_DIR = Path(__file__).resolve().parent
ROBOT_MONITOR_DIR = TEST_DIR.parent
if str(ROBOT_MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(ROBOT_MONITOR_DIR))

from prelabel_pipeline.alpha50_batch import (
    Alpha50Candidate,
    CandidatePreflightError,
    build_candidate_provenance,
    persist_candidate_provenance,
    preflight_candidate,
    framework_tree_digest,
    Alpha50Runtime,
    build_cvat_images_xml,
    infer_alpha50_snapshot,
    save_alpha50_artifacts,
    validate_cvat_images_xml,
)


class Alpha50CandidateTest(unittest.TestCase):
    def _candidate(self, root: Path, *, mapping=None):
        weight = root / "candidate.pth"
        weight.write_bytes(b"candidate-weights")
        framework = root / "framework"
        framework.mkdir()
        revision_source = framework / "revision.py"
        revision_source.write_text("candidate-framework-revision", encoding="utf-8")
        candidate = {
            "framework_root": str(framework),
            "framework_revision": "tree-sha256:" + framework_tree_digest(framework),
            "weights": [{"path": str(weight), "sha256": hashlib.sha256(weight.read_bytes()).hexdigest()}],
            "tta": {"scales": [768, 832], "flip": True, "interpolation": "bilinear"},
            "fusion": {"method": "mean_logits"},
            "export": {"ignore_policy": "drop", "background_policy": "exclude", "contours": {"min_area": 50, "approx_epsilon": 1.5, "smooth": True}},
            "label_mapping": mapping or {"1": {"canonical": "lawn", "cvat": "lawn草地"}},
            "expected_cvat_schema": {"version": 1, "labels": [{"name": "lawn草地", "type": "polygon", "attributes": []}]},
            "output_path": str(root / "candidate-output"),
            "min_vram_gb": 4,
            "min_disk_gb": 1,
        }
        return candidate

    def test_preflight_validates_fixed_assets_runtime_capacity_and_creates_cvat_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = self._candidate(Path(tmp))
            create_labels = Mock(return_value={"id": 91, "labels": [{"name": "lawn草地", "type": "polygon", "attributes": []}]})

            result = preflight_candidate(
                candidate,
                input_snapshot_hash="input-sha",
                import_checker=lambda root: ["detectron2", "torch"],
                gpu_checker=lambda: {"cuda": True, "vram_gb": 8},
                disk_checker=lambda _: 8,
                create_cvat_task=create_labels,
                get_cvat_schema=lambda task: task["labels"],
                provenance_path=Path(tmp) / "provenance.json",
                branch_record={},
                cleanup_cvat_task=lambda _: {"status": "deleted"},
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.task_id, 91)
            self.assertFalse(result.block_import)
            create_labels.assert_called_once()
            self.assertEqual(result.manifest["input_snapshot_hash"], "input-sha")
            self.assertEqual(result.manifest_digest, hashlib.sha256(json.dumps(result.manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest())

    def test_preflight_failure_does_not_create_candidate_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = self._candidate(Path(tmp))
            candidate["weights"][0]["sha256"] = "0" * 64
            create_labels = Mock()

            with self.assertRaises(CandidatePreflightError):
                preflight_candidate(
                    candidate,
                    input_snapshot_hash="input-sha",
                    import_checker=lambda root: ["detectron2"],
                    gpu_checker=lambda: {"cuda": True, "vram_gb": 8},
                    disk_checker=lambda _: 8,
                    create_cvat_task=create_labels,
                    get_cvat_schema=lambda task: [],
                )
            create_labels.assert_not_called()

    def test_schema_failure_after_create_blocks_import_and_exposes_cleanup_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = self._candidate(Path(tmp))

            result = preflight_candidate(
                candidate,
                input_snapshot_hash="input-sha",
                import_checker=lambda root: ["detectron2", "torch"],
                gpu_checker=lambda: {"cuda": True, "vram_gb": 8},
                disk_checker=lambda _: 8,
                create_cvat_task=lambda labels, **_: {"id": 91, "labels": labels},
                get_cvat_schema=lambda task: [{"name": "wrong"}],
                provenance_path=Path(tmp) / "provenance.json",
                branch_record={},
                cleanup_cvat_task=lambda _: {"status": "deleted"},
            )

            self.assertFalse(result.ok)
            self.assertTrue(result.block_import)
            self.assertEqual(result.cleanup_task_id, 91)
            self.assertIn("schema", result.errors[0])

    def test_provenance_is_immutable_and_does_not_depend_on_mutable_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = self._candidate(root)
            candidate_config = root / "candidate.yaml"
            candidate_config.write_text(yaml.safe_dump(candidate), encoding="utf-8")
            manifest, digest = build_candidate_provenance(candidate, "input-sha")
            candidate_config.write_text("weights: []\n", encoding="utf-8")

            frozen = json.loads(json.dumps(manifest))
            self.assertEqual(manifest, frozen)
            self.assertEqual(manifest["label_mapping_sha256"], hashlib.sha256(json.dumps(candidate["label_mapping"], sort_keys=True, separators=(",", ":")).encode()).hexdigest())
            self.assertEqual(digest, hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest())

    def test_provenance_manifest_persists_its_digest_as_an_immutable_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, digest = build_candidate_provenance(self._candidate(root), "input-sha")
            path = persist_candidate_provenance(root / "provenance.json", manifest, digest)

            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["manifest"], manifest)
            self.assertEqual(persisted["manifest_digest"], digest)
            self.assertEqual(path.stat().st_mode & 0o222, 0)

    def test_candidate_config_declares_required_fixed_inference_contract(self):
        config_path = ROBOT_MONITOR_DIR / "prelabel_pipeline" / "prelabel_config.yaml"
        candidate = yaml.safe_load(config_path.read_text(encoding="utf-8"))["alpha50_candidate"]
        validated = Alpha50Candidate.from_mapping(candidate)

        self.assertEqual(validated.tta["scales"], [768, 832])
        self.assertTrue(validated.tta["flip"])
        self.assertEqual(validated.tta["interpolation"], "bilinear")
        self.assertTrue(validated.label_mapping)

    def test_candidate_config_carries_all_thirteen_source_id_mappings(self):
        candidate = yaml.safe_load((ROBOT_MONITOR_DIR / "prelabel_pipeline" / "prelabel_config.yaml").read_text(encoding="utf-8"))["alpha50_candidate"]

        self.assertEqual(set(candidate["label_mapping"]), {str(index) for index in range(13)})
        self.assertEqual(candidate["label_mapping"]["12"]["canonical"], "car")

    def test_precreate_rejects_unknown_source_id_without_creating_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = self._candidate(Path(tmp))
            candidate["label_mapping"]["99"] = {"canonical": "unknown", "cvat": "missing"}
            create_task = Mock()

            with self.assertRaisesRegex(CandidatePreflightError, "unknown source ID"):
                preflight_candidate(candidate, input_snapshot_hash="input", import_checker=lambda _: ["torch", "detectron2"], gpu_checker=lambda: {"cuda": True, "vram_gb": 8}, disk_checker=lambda _: 8, create_cvat_task=create_task, get_cvat_schema=lambda _: [])
            create_task.assert_not_called()

    def test_precreate_rejects_mapping_to_missing_cvat_label_without_creating_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = self._candidate(Path(tmp))
            candidate["label_mapping"]["1"]["cvat"] = "not-defined"
            create_task = Mock()

            with self.assertRaisesRegex(CandidatePreflightError, "missing CVAT label"):
                preflight_candidate(candidate, input_snapshot_hash="input", import_checker=lambda _: ["torch", "detectron2"], gpu_checker=lambda: {"cuda": True, "vram_gb": 8}, disk_checker=lambda _: 8, create_cvat_task=create_task, get_cvat_schema=lambda _: [])
            create_task.assert_not_called()

    def test_postcreate_type_or_attribute_mismatch_blocks_import_and_runs_tracked_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = self._candidate(Path(tmp))
            candidate["expected_cvat_schema"] = {"version": 1, "labels": [{"name": "lawn草地", "type": "polygon", "attributes": [{"name": "source", "type": "text", "values": []}]}]}
            cleanup = Mock(return_value={"status": "deleted"})

            result = preflight_candidate(candidate, input_snapshot_hash="input", provenance_path=Path(tmp) / "provenance.json", branch_record={}, import_checker=lambda _: ["torch", "detectron2"], gpu_checker=lambda: {"cuda": True, "vram_gb": 8}, disk_checker=lambda _: 8, create_cvat_task=lambda _, **__: {"id": 44}, get_cvat_schema=lambda _: [{"name": "lawn草地", "type": "tag", "attributes": []}], cleanup_cvat_task=cleanup)

            self.assertTrue(result.block_import)
            self.assertEqual(result.cleanup_task_id, 44)
            self.assertEqual(result.cleanup_outcome, {"status": "deleted"})
            cleanup.assert_called_once_with(44)

    def test_preflight_persists_manifest_digest_to_branch_record_before_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = self._candidate(root)
            branch_record = {}
            provenance_path = root / "branch" / "provenance.json"
            create_task = Mock(return_value={"id": 55})

            result = preflight_candidate(candidate, input_snapshot_hash="input", provenance_path=provenance_path, branch_record=branch_record, import_checker=lambda _: ["torch", "detectron2"], gpu_checker=lambda: {"cuda": True, "vram_gb": 8}, disk_checker=lambda _: 8, create_cvat_task=create_task, get_cvat_schema=lambda _: [{"name": "lawn草地", "type": "polygon", "attributes": []}], cleanup_cvat_task=lambda _: {"status": "deleted"})

            self.assertTrue(provenance_path.is_file())
            self.assertEqual(branch_record["candidate_provenance_digest"], result.manifest_digest)
            self.assertEqual(branch_record["candidate_provenance_path"], str(provenance_path))

    def test_preflight_rejects_missing_provenance_persistence_context_before_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = self._candidate(Path(tmp))
            create_task = Mock()

            with self.assertRaisesRegex(CandidatePreflightError, "provenance persistence"):
                preflight_candidate(candidate, input_snapshot_hash="input", import_checker=lambda _: ["torch", "detectron2"], gpu_checker=lambda: {"cuda": True, "vram_gb": 8}, disk_checker=lambda _: 8, create_cvat_task=create_task, get_cvat_schema=lambda _: [])
            create_task.assert_not_called()

    def test_preflight_rejects_missing_cleanup_facility_before_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = self._candidate(root)
            create_task = Mock()

            with self.assertRaisesRegex(CandidatePreflightError, "cleanup callback"):
                preflight_candidate(candidate, input_snapshot_hash="input", provenance_path=root / "provenance.json", branch_record={}, import_checker=lambda _: ["torch", "detectron2"], gpu_checker=lambda: {"cuda": True, "vram_gb": 8}, disk_checker=lambda _: 8, create_cvat_task=create_task, get_cvat_schema=lambda _: [])
            create_task.assert_not_called()

    def test_preflight_rejects_changed_framework_revision_before_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = self._candidate(root)
            framework_source = root / "framework" / "train.py"
            framework_source.write_text("original", encoding="utf-8")
            candidate["framework_revision"] = "tree-sha256:" + framework_tree_digest(root / "framework")
            framework_source.write_text("changed", encoding="utf-8")
            create_task = Mock()

            with self.assertRaisesRegex(CandidatePreflightError, "framework revision mismatch"):
                preflight_candidate(candidate, input_snapshot_hash="input", provenance_path=root / "provenance.json", branch_record={}, cleanup_cvat_task=lambda _: {}, import_checker=lambda _: ["torch", "detectron2"], gpu_checker=lambda: {"cuda": True, "vram_gb": 8}, disk_checker=lambda _: 8, create_cvat_task=create_task, get_cvat_schema=lambda _: [])
            create_task.assert_not_called()

    def test_disk_check_uses_configured_output_filesystem(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = self._candidate(root)
            output_path = root / "candidate-output"
            candidate["output_path"] = str(output_path)
            seen = []

            preflight_candidate(candidate, input_snapshot_hash="input", provenance_path=root / "provenance.json", branch_record={}, cleanup_cvat_task=lambda _: {}, import_checker=lambda _: ["torch", "detectron2"], gpu_checker=lambda: {"cuda": True, "vram_gb": 8}, disk_checker=lambda path: seen.append(Path(path)) or 8, create_cvat_task=lambda _, **__: {"id": 7}, get_cvat_schema=lambda _: [{"name": "lawn草地", "type": "polygon", "attributes": []}])

            self.assertEqual(seen, [output_path])

    def test_idless_task_response_records_durable_resolution_needed_without_schema_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = self._candidate(root)
            schema = Mock()

            record = {}
            result = preflight_candidate(candidate, input_snapshot_hash="input", provenance_path=root / "provenance.json", branch_record=record, cleanup_cvat_task=lambda _: {}, resolve_cvat_task=lambda *_: None, import_checker=lambda _: ["torch", "detectron2"], gpu_checker=lambda: {"cuda": True, "vram_gb": 8}, disk_checker=lambda _: 8, create_cvat_task=lambda _, **__: {}, get_cvat_schema=schema)
            self.assertTrue(result.block_import)
            self.assertEqual(record["candidate_preflight_status"], "cleanup_resolution_needed")
            schema.assert_not_called()

    def test_schema_fetch_exception_records_cleanup_needed_then_tracks_cleanup_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = self._candidate(root)
            record = {}

            result = preflight_candidate(candidate, input_snapshot_hash="input", provenance_path=root / "provenance.json", branch_record=record, cleanup_cvat_task=Mock(side_effect=RuntimeError("cleanup offline")), import_checker=lambda _: ["torch", "detectron2"], gpu_checker=lambda: {"cuda": True, "vram_gb": 8}, disk_checker=lambda _: 8, create_cvat_task=lambda _, **__: {"id": 17}, get_cvat_schema=Mock(side_effect=RuntimeError("schema offline")))

            self.assertTrue(result.block_import)
            self.assertEqual(result.cleanup_task_id, 17)
            self.assertEqual(result.cleanup_outcome["status"], "cleanup_failed")
            self.assertEqual(record["candidate_cleanup_needed_task_id"], 17)
            self.assertEqual(record["candidate_preflight_status"], "schema_failed")

    def test_framework_tree_pin_rejects_changed_non_pinned_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = self._candidate(root)
            (root / "framework" / "other.py").write_text("changed source", encoding="utf-8")

            with self.assertRaisesRegex(CandidatePreflightError, "framework revision mismatch"):
                preflight_candidate(candidate, input_snapshot_hash="input", provenance_path=root / "provenance.json", branch_record={}, cleanup_cvat_task=lambda _: {}, resolve_cvat_task=lambda *_: None, import_checker=lambda _: ["torch", "detectron2"], gpu_checker=lambda: {"cuda": True, "vram_gb": 8}, disk_checker=lambda _: 8, create_cvat_task=Mock(), get_cvat_schema=lambda _: [])

    def test_missing_id_resolves_task_by_persisted_identity_and_cleans_it_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = self._candidate(root)
            record = {}
            cleanup = Mock(return_value={"status": "deleted"})
            resolver = Mock(return_value={"id": 29})
            create = Mock(return_value={})

            result = preflight_candidate(candidate, input_snapshot_hash="input", provenance_path=root / "provenance.json", branch_record=record, cleanup_cvat_task=cleanup, resolve_cvat_task=resolver, import_checker=lambda _: ["torch", "detectron2"], gpu_checker=lambda: {"cuda": True, "vram_gb": 8}, disk_checker=lambda _: 8, create_cvat_task=create, get_cvat_schema=lambda _: [{"name": "wrong"}])

            self.assertTrue(record["candidate_task_identity"])
            self.assertTrue(record["candidate_request_key"])
            self.assertEqual(create.call_args.kwargs["task_identity"], record["candidate_task_identity"])
            self.assertEqual(create.call_args.kwargs["request_key"], record["candidate_request_key"])
            resolver.assert_called_once_with(record["candidate_task_identity"], record["candidate_request_key"])
            cleanup.assert_called_once_with(29)
            self.assertEqual(result.cleanup_task_id, 29)

    def test_create_exception_with_unresolved_identity_persists_resolution_needed_without_cleanup_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = self._candidate(root)
            record = {}
            cleanup = Mock()

            result = preflight_candidate(candidate, input_snapshot_hash="input", provenance_path=root / "provenance.json", branch_record=record, cleanup_cvat_task=cleanup, resolve_cvat_task=lambda *_: None, import_checker=lambda _: ["torch", "detectron2"], gpu_checker=lambda: {"cuda": True, "vram_gb": 8}, disk_checker=lambda _: 8, create_cvat_task=Mock(side_effect=RuntimeError("connection reset")), get_cvat_schema=lambda _: [])

            self.assertTrue(result.block_import)
            self.assertEqual(record["candidate_preflight_status"], "cleanup_resolution_needed")
            self.assertEqual(record["candidate_cleanup_lookup_key"], record["candidate_request_key"])
            cleanup.assert_not_called()

    def test_preflight_rejects_legacy_create_adapter_before_remote_invocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = self._candidate(root)
            calls = []

            def legacy_create(labels):
                calls.append(labels)
                return {"id": 1}

            with self.assertRaisesRegex(CandidatePreflightError, "idempotency"):
                preflight_candidate(candidate, input_snapshot_hash="input", provenance_path=root / "provenance.json", branch_record={}, cleanup_cvat_task=lambda _: {}, resolve_cvat_task=lambda *_: None, import_checker=lambda _: ["torch", "detectron2"], gpu_checker=lambda: {"cuda": True, "vram_gb": 8}, disk_checker=lambda _: 8, create_cvat_task=legacy_create, get_cvat_schema=lambda _: [])
            self.assertEqual(calls, [])


class Alpha50InferenceTest(unittest.TestCase):
    def _candidate(self):
        return {
            "tta": {"scales": [768, 832], "flip": True, "interpolation": "bilinear", "align_corners": False},
            "fusion": {"method": "mean_logits"},
            "export": {"background_policy": "exclude", "confidence_policy": "per-class-softmax-threshold", "confidence_threshold": 0.50, "contours": {"min_area": 2, "approx_epsilon": 0.0}},
            "label_mapping": {"0": {"canonical": "background", "cvat": "background"}, "1": {"canonical": "lawn", "cvat": "lawn草地"}},
            "expected_cvat_schema": {"version": 1, "labels": [{"name": "background", "type": "polygon", "attributes": []}, {"name": "lawn草地", "type": "polygon", "attributes": []}]},
        }

    def test_inference_fuses_four_logits_unflips_and_preserves_original_shape(self):
        image = np.zeros((2, 4, 3), dtype=np.uint8)
        calls = []
        normal = np.array([[[0, 0, 0, 0], [0, 0, 0, 0]], [[9, 1, 1, 1], [9, 1, 1, 1]]], dtype=np.float32)

        def predict(_, *, size, flip):
            calls.append((size, flip))
            logits = normal + (4 if size == 832 else 0)
            return logits[:, :, ::-1] if flip else logits

        result = infer_alpha50_snapshot(image, predict, self._candidate())

        self.assertEqual(calls, [(768, False), (768, True), (832, False), (832, True)])
        self.assertEqual(result.logits.shape, (2, 2, 4))
        np.testing.assert_allclose(result.logits, normal + 2)
        self.assertTrue(np.all(result.mask == 1))
        self.assertEqual(result.class_stats["lawn"]["pixels"], 8)

    def test_inference_applies_background_when_winning_class_confidence_is_below_threshold(self):
        image = np.zeros((1, 2, 3), dtype=np.uint8)
        logits = np.array([[[0, 0]], [[0.1, 0.1]]], dtype=np.float32)
        candidate = self._candidate()
        candidate["export"]["confidence_threshold"] = 0.75

        result = infer_alpha50_snapshot(image, lambda *_args, **_kwargs: logits, candidate)

        self.assertTrue(np.all(result.mask == 0))

    def test_runtime_loads_model_once_for_repeated_predictions(self):
        loader = Mock(return_value="model")
        predictor = Mock(return_value=np.zeros((2, 1, 1), dtype=np.float32))
        runtime = Alpha50Runtime(loader, predictor)

        runtime.predict(np.zeros((1, 1, 3), dtype=np.uint8), size=768, flip=False)
        runtime.predict(np.zeros((1, 1, 3), dtype=np.uint8), size=832, flip=True)

        loader.assert_called_once_with()
        self.assertEqual(predictor.call_count, 2)

    def test_save_artifacts_writes_raw_mask_and_per_class_stats(self):
        result = infer_alpha50_snapshot(np.zeros((1, 2, 3), dtype=np.uint8), lambda *_args, **_kwargs: np.array([[[0, 0]], [[2, 2]]], dtype=np.float32), self._candidate())
        with tempfile.TemporaryDirectory() as tmp:
            saved = save_alpha50_artifacts(result, "snap.jpg", tmp)

            self.assertTrue(Path(saved["mask_path"]).is_file())
            self.assertEqual(json.loads(Path(saved["stats_path"]).read_text(encoding="utf-8")), result.class_stats)

    def test_xml_filters_small_components_and_is_deterministic(self):
        mask = np.array([[1, 1, 0, 1], [1, 1, 0, 0], [0, 0, 0, 0]], dtype=np.uint8)
        item = {"name": "snap.png", "width": 4, "height": 3, "mask": mask}
        first = build_cvat_images_xml([item], self._candidate())
        second = build_cvat_images_xml([item], self._candidate())

        self.assertEqual(first, second)
        root = ET.fromstring(first)
        polygons = root.findall("./image/polygon")
        self.assertEqual(len(polygons), 1)
        self.assertEqual(polygons[0].attrib["label"], "lawn草地")

    def test_xml_validator_rejects_invalid_name_size_geometry_and_schema(self):
        valid = build_cvat_images_xml([{"name": "snap.png", "width": 4, "height": 3, "mask": np.ones((3, 4), dtype=np.uint8)}], self._candidate()).decode("utf-8")
        validate_cvat_images_xml(valid, [{"name": "snap.png", "width": 4, "height": 3}], self._candidate()["expected_cvat_schema"])

        cases = [
            (valid.replace('name="snap.png"', 'name="wrong.png"'), "image name"),
            (valid.replace('width="4"', 'width="5"'), "image dimensions"),
            (valid.replace('label="lawn草地"', 'label="unknown"'), "label schema"),
            (valid.replace('points="0.0,0.0', 'points="9.0,0.0'), "polygon bounds"),
        ]
        for xml, error in cases:
            with self.subTest(error=error), self.assertRaisesRegex(CandidatePreflightError, error):
                validate_cvat_images_xml(xml, [{"name": "snap.png", "width": 4, "height": 3}], self._candidate()["expected_cvat_schema"])
