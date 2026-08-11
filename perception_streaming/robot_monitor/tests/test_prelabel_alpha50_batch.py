import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

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
)


class Alpha50CandidateTest(unittest.TestCase):
    def _candidate(self, root: Path, *, mapping=None):
        weight = root / "candidate.pth"
        weight.write_bytes(b"candidate-weights")
        framework = root / "framework"
        framework.mkdir()
        candidate = {
            "framework_root": str(framework),
            "framework_revision": "git:abc123",
            "weights": [{"path": str(weight), "sha256": hashlib.sha256(weight.read_bytes()).hexdigest()}],
            "tta": {"scales": [768, 832], "flip": True, "interpolation": "bilinear"},
            "fusion": {"method": "mean_logits"},
            "export": {"ignore_policy": "drop", "background_policy": "exclude", "contours": {"min_area": 50, "approx_epsilon": 1.5, "smooth": True}},
            "label_mapping": mapping or {"1": {"canonical": "lawn", "cvat": "lawn草地"}},
            "min_vram_gb": 4,
            "min_disk_gb": 1,
        }
        return candidate

    def test_preflight_validates_fixed_assets_runtime_capacity_and_creates_cvat_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = self._candidate(Path(tmp))
            create_labels = Mock(return_value={"id": 91, "labels": [{"name": "lawn草地"}]})

            result = preflight_candidate(
                candidate,
                input_snapshot_hash="input-sha",
                import_checker=lambda root: ["detectron2", "torch"],
                gpu_checker=lambda: {"cuda": True, "vram_gb": 8},
                disk_checker=lambda: 8,
                create_cvat_task=create_labels,
                get_cvat_schema=lambda task: task["labels"],
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
                    disk_checker=lambda: 8,
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
                disk_checker=lambda: 8,
                create_cvat_task=lambda labels: {"id": 91, "labels": labels},
                get_cvat_schema=lambda task: [{"name": "wrong"}],
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
