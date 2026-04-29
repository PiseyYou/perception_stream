import sys
import tempfile
import unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
ROBOT_MONITOR_DIR = TEST_DIR.parent
if str(ROBOT_MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(ROBOT_MONITOR_DIR))

from prelabel_pipeline.path_utils import (
    InvalidPathError,
    safe_filename,
    unique_path,
    validate_run_id,
    validate_upload_id,
    resolve_under,
)


class PrelabelPathUtilsTest(unittest.TestCase):
    def test_resolve_under_accepts_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            child = root / "images"
            child.mkdir()
            self.assertEqual(resolve_under(child, [root]), child)

    def test_resolve_under_rejects_outside_path(self):
        with tempfile.TemporaryDirectory() as root_tmp, tempfile.TemporaryDirectory() as other_tmp:
            with self.assertRaises(InvalidPathError):
                resolve_under(Path(other_tmp), [Path(root_tmp)])

    def test_resolve_under_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as root_tmp, tempfile.TemporaryDirectory() as other_tmp:
            root = Path(root_tmp)
            link = root / "escape"
            link.symlink_to(Path(other_tmp), target_is_directory=True)
            with self.assertRaises(InvalidPathError):
                resolve_under(link, [root])

    def test_safe_filename_keeps_basename_and_extension(self):
        self.assertEqual(safe_filename("../foo/image 1.jpg"), "image_1.jpg")

    def test_safe_filename_rejects_empty(self):
        with self.assertRaises(ValueError):
            safe_filename("..")

    def test_validate_upload_id_accepts_expected_ids(self):
        upload_id = "folder_0429_153012_a1b2c3d4"
        self.assertEqual(validate_upload_id(upload_id), upload_id)

    def test_validate_upload_id_rejects_short_or_path_fragments(self):
        for value in ("../abc", "abc/def", "abc.def", "short", "abcDEF_123456"):
            with self.assertRaises(ValueError):
                validate_upload_id(value)

    def test_validate_run_id_requires_12_hex_chars(self):
        self.assertEqual(validate_run_id("abcdef123456"), "abcdef123456")
        for value in ("abcdef12345", "abcdef1234567", "ABCDEF123456", "../abcdef123456"):
            with self.assertRaises(ValueError):
                validate_run_id(value)

    def test_unique_path_returns_original_when_unused(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.assertEqual(unique_path(directory, "image.jpg"), directory / "image.jpg")

    def test_unique_path_suffixes_duplicate_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "image.jpg").write_text("first", encoding="utf-8")
            self.assertEqual(unique_path(directory, "image.jpg"), directory / "image_2.jpg")

    def test_unique_path_sanitizes_parent_directory_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            candidate = unique_path(directory, "../escape.jpg")
            self.assertEqual(candidate, directory / "escape.jpg")
            self.assertEqual(candidate.parent, directory)

    def test_unique_path_sanitizes_absolute_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            candidate = unique_path(directory, "/tmp/escape.jpg")
            self.assertEqual(candidate, directory / "escape.jpg")
            self.assertEqual(candidate.parent, directory)
