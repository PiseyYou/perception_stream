import io
import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from PIL import Image

TEST_DIR = Path(__file__).resolve().parent
ROBOT_MONITOR_DIR = TEST_DIR.parent
if str(ROBOT_MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(ROBOT_MONITOR_DIR))

from prelabel_pipeline import run_state
from prelabel_pipeline.shadow_batch import freeze_batch, materialize_branch_input


_png_buffer = io.BytesIO()
Image.new("RGB", (1, 1), "red").save(_png_buffer, format="PNG")
PNG_1X1 = _png_buffer.getvalue()


class PrelabelShadowBatchTest(unittest.TestCase):
    def _image(self, path: Path, data: bytes = PNG_1X1, size: tuple[int, int] | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if size is not None:
            buffer = io.BytesIO()
            Image.new("RGB", size, "blue").save(buffer, format="PNG")
            data = buffer.getvalue()
        path.write_bytes(data)

    def test_freeze_batch_writes_sorted_serializable_manifest_with_image_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._image(source / "z.png", size=(2, 1))
            self._image(source / "nested" / "a.png")

            snapshot = freeze_batch(source, root / "snapshots")

            manifest_path = Path(snapshot["snapshot_path"]) / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual([item["path"] for item in manifest["files"]], ["nested/a.png", "z.png"])
            self.assertEqual(
                [item["original_dimensions"] for item in manifest["files"]],
                [{"width": 1, "height": 1}, {"width": 2, "height": 1}],
            )
            self.assertEqual(
                [item["normalized_dimensions"] for item in manifest["files"]],
                [item["original_dimensions"] for item in manifest["files"]],
            )
            self.assertEqual(manifest["batch_id"], snapshot["batch_id"])
            self.assertEqual(manifest["snapshot_hash"], snapshot["snapshot_hash"])
            self.assertFalse((manifest_path.parent / "manifest.json.tmp").exists())
            json.dumps(snapshot)

    def test_freeze_batch_rejects_unsupported_corrupt_and_duplicate_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._image(source / "ok.png")
            (source / "note.txt").write_text("not an image", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsupported"):
                freeze_batch(source, root / "snapshots")

            (source / "note.txt").unlink()
            (source / "bad.png").write_bytes(b"not a png")
            with self.assertRaisesRegex(ValueError, "corrupt"):
                freeze_batch(source, root / "snapshots")

            (source / "bad.png").unlink()
            self._image(source / "same.png")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                freeze_batch(source, root / "snapshots")

    def test_freeze_batch_ignores_upload_metadata_but_rejects_other_unsupported_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "upload"
            self._image(source / "image.png")
            (source / ".upload_meta.json").write_text('{"owner_token":"opaque"}', encoding="utf-8")

            snapshot = freeze_batch(source, root / "snapshots")

            manifest = json.loads((Path(snapshot["snapshot_path"]) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([item["path"] for item in manifest["files"]], ["image.png"])
            (source / "unexpected.txt").write_text("not allowed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsupported"):
                freeze_batch(source, root / "other-snapshots")

    def test_freeze_batch_rejects_source_image_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            external_image = root / "external.png"
            self._image(external_image)
            (source / "linked.png").symlink_to(external_image)

            with self.assertRaisesRegex(ValueError, "symlink"):
                freeze_batch(source, root / "snapshots")

    def test_freeze_batch_does_not_publish_when_source_changes_during_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            image = source / "image.png"
            self._image(image)

            from prelabel_pipeline import shadow_batch

            original_copy2 = shadow_batch.shutil.copy2

            def mutate_before_copy(src, dst, *args, **kwargs):
                if Path(src) == image:
                    self._image(image, size=(2, 1))
                return original_copy2(src, dst, *args, **kwargs)

            with patch.object(shadow_batch.shutil, "copy2", side_effect=mutate_before_copy):
                with self.assertRaisesRegex(ValueError, "integrity"):
                    freeze_batch(source, root / "snapshots")
            self.assertFalse((root / "snapshots").exists() and any((root / "snapshots").iterdir()))

    def test_freeze_batch_is_idempotent_when_snapshot_already_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._image(source / "image.png")

            first = freeze_batch(source, root / "snapshots")
            second = freeze_batch(source, root / "snapshots")

            self.assertEqual(second, first)
            self.assertEqual([path.name for path in (root / "snapshots").iterdir()], [first["batch_id"]])

    def test_freeze_batch_is_safe_when_two_callers_publish_the_same_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._image(source / "image.png")

            with ThreadPoolExecutor(max_workers=2) as pool:
                snapshots = list(pool.map(lambda _: freeze_batch(source, root / "snapshots"), range(2)))

            self.assertEqual(snapshots[0], snapshots[1])
            self.assertEqual([path.name for path in (root / "snapshots").iterdir()], [snapshots[0]["batch_id"]])

    def test_materialized_branch_inputs_are_writable_copies_isolated_from_snapshot_and_peer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._image(source / "nested" / "image.png")
            snapshot = freeze_batch(source, root / "snapshots")

            branch_a = materialize_branch_input(snapshot, "a", root / "work")
            branch_b = materialize_branch_input(snapshot, "b", root / "work")
            (branch_a / "nested" / "image.png").write_bytes(b"branch-a-change")

            self.assertEqual((branch_b / "nested" / "image.png").read_bytes(), PNG_1X1)
            self.assertEqual(
                (Path(snapshot["snapshot_path"]) / "images" / "nested" / "image.png").read_bytes(),
                PNG_1X1,
            )
            self.assertNotEqual((branch_a / "nested" / "image.png").stat().st_ino,
                                (branch_b / "nested" / "image.png").stat().st_ino)

    def test_deleting_candidate_branch_file_keeps_snapshot_and_baseline_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._image(source / "nested" / "image.png")
            snapshot = freeze_batch(source, root / "snapshots")
            baseline = materialize_branch_input(snapshot, "baseline", root / "work")
            candidate = materialize_branch_input(snapshot, "candidate", root / "work")

            (candidate / "nested" / "image.png").unlink()

            self.assertTrue((baseline / "nested" / "image.png").is_file())
            self.assertEqual((baseline / "nested" / "image.png").read_bytes(), PNG_1X1)
            snapshot_file = Path(snapshot["snapshot_path"]) / "images" / "nested" / "image.png"
            self.assertTrue(snapshot_file.is_file())
            self.assertEqual(snapshot_file.read_bytes(), PNG_1X1)

    def test_materialize_rejects_preexisting_symlinked_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._image(source / "image.png")
            snapshot = freeze_batch(source, root / "snapshots")
            sentinel = root / "sentinel.png"
            sentinel.write_bytes(b"must not be overwritten")
            destination = root / "work" / snapshot["batch_id"] / "a"
            destination.mkdir(parents=True)
            (destination / "image.png").symlink_to(sentinel)

            with self.assertRaisesRegex(ValueError, "symlink"):
                materialize_branch_input(snapshot, "a", root / "work")
            self.assertEqual(sentinel.read_bytes(), b"must not be overwritten")

    def test_materialize_rejects_symlinked_batch_id_ancestor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._image(source / "image.png")
            snapshot = freeze_batch(source, root / "snapshots")
            work_root = root / "work"
            work_root.mkdir()
            (work_root / snapshot["batch_id"]).symlink_to(root / "elsewhere")

            with self.assertRaisesRegex(ValueError, "symlink"):
                materialize_branch_input(snapshot, "a", work_root)

    def test_materialize_rejects_a_work_root_inside_the_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._image(source / "image.png")
            snapshot = freeze_batch(source, root / "snapshots")

            with self.assertRaisesRegex(ValueError, "inside snapshot"):
                materialize_branch_input(snapshot, "a", snapshot["snapshot_path"])

    def test_shadow_metadata_is_optional_and_survives_persistence_and_restore(self):
        shadow = {
            "mode": "ab_shadow",
            "batch_id": "batch-1",
            "snapshot_hash": "abc123",
            "snapshot_path": "/snapshots/batch-1",
            "branches": {"a": {"attempt": 1, "status": "success"}},
            "review_state": "pending",
        }
        with tempfile.TemporaryDirectory() as tmp:
            run_state.runs.clear()
            run_state.runs["abcdef123456"] = run_state.make_runtime_run(
                "demo", ["/tmp/images"], shadow=shadow
            )
            run_state.runs["abcdef123456"].update(status="success", done=True)
            run_state.save_run("abcdef123456", tmp)
            saved = json.loads((Path(tmp) / "abcdef123456.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["shadow"], shadow)

            run_state.runs.clear()
            run_state.init_runs_from_history(tmp)
            self.assertEqual(run_state.runs["abcdef123456"]["shadow"], shadow)
