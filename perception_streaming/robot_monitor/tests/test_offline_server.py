import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TEST_DIR = Path(__file__).resolve().parent
ROBOT_MONITOR_DIR = TEST_DIR.parent
if str(ROBOT_MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(ROBOT_MONITOR_DIR))

import offline_server  # noqa: E402
import config_loader  # noqa: E402


class OfflineServerResultDiscoveryTest(unittest.TestCase):
    def test_build_output_dir_uses_stereo_debug_conventions(self):
        folder = "data/stereo_debug/0016/20260420"

        self.assertEqual(
            offline_server.build_output_dir(folder, 6),
            "data/stereo_debug/0016/20260420/sub_6_205_432",
        )
        self.assertEqual(
            offline_server.build_output_dir(folder, 99),
            "data/stereo_debug/0016/20260420/dsg_7_205_432",
        )
        self.assertEqual(
            offline_server.build_pointcloud_dir(folder, 6),
            "data/stereo_debug/0016/20260420/pcd_6_205_432",
        )

    def test_collect_result_images_prefers_combined_subdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "sub_6_205_432"
            (output_dir / "combined").mkdir(parents=True)
            (output_dir / "segmentation").mkdir(parents=True)
            (output_dir / "combined" / "frame_0001_combined.jpg").write_bytes(b"jpg")
            (output_dir / "segmentation" / "frame_0001_seg.png").write_bytes(b"png")

            images = offline_server._collect_result_images(str(output_dir))

            self.assertEqual(images, ["combined/frame_0001_combined.jpg"])

    def test_find_existing_result_prefers_requested_day_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "data" / "stereo_debug" / "0016" / "20260420"
            day_output = folder / "sub_6_205_432"
            day_pcd = folder / "pcd_6_205_432"
            night_output = folder / "dsg_7_205_432"
            (day_output / "combined").mkdir(parents=True)
            day_pcd.mkdir(parents=True)
            (night_output / "combined").mkdir(parents=True)

            (day_output / "combined" / "frame_0001_combined.jpg").write_bytes(b"jpg")
            (day_pcd / "frame_0001.pcd").write_text("VERSION .7\n")
            (night_output / "combined" / "frame_9999_combined.jpg").write_bytes(b"jpg")

            result = offline_server._find_existing_result(str(folder), prefer_mode=6)

            self.assertTrue(result["ok"])
            self.assertEqual(result["infer_mode"], 6)
            self.assertEqual(result["output_dir"], str(day_output))
            self.assertEqual(result["images"], ["combined/frame_0001_combined.jpg"])
            self.assertEqual(result["pcd_dir"], str(day_pcd))
            self.assertEqual(result["pcds"], ["frame_0001.pcd"])

    def test_sync_legacy_pointcloud_dir_copies_nested_pointclouds(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "sub_6_205_432"
            legacy_pcd = output_dir / "pointcloud"
            target_pcd = Path(tmp) / "pcd_6_205_432"
            legacy_pcd.mkdir(parents=True)
            (legacy_pcd / "frame_0001.pcd").write_text("VERSION .7\n")

            pcd_dir, pcds = offline_server._sync_legacy_pointcloud_dir(str(output_dir), str(target_pcd))

            self.assertEqual(pcd_dir, str(target_pcd))
            self.assertEqual(pcds, ["frame_0001.pcd"])
            self.assertTrue((target_pcd / "frame_0001.pcd").is_file())

    def test_update_progress_from_log_parses_bracket_progress(self):
        offline_server._reset_progress_state(input_dir="demo", infer_mode=6, total=25)

        offline_server._update_progress_from_log("[1/25] perception_stereo_001")

        self.assertEqual(offline_server._progress_state["current"], 1)
        self.assertEqual(offline_server._progress_state["total"], 25)
        self.assertEqual(offline_server._progress_state["status"], "正在运行第 1/25 张")

    def test_update_progress_from_log_parses_processing_line(self):
        offline_server._reset_progress_state(input_dir="demo", infer_mode=6, total=0)

        offline_server._update_progress_from_log("Processing 2/25: /app/input/frame_0002.jpg")

        self.assertEqual(offline_server._progress_state["current"], 2)
        self.assertEqual(offline_server._progress_state["total"], 25)
        self.assertEqual(offline_server._progress_state["status"], "正在处理: frame_0002.jpg")


class OfflineServerSecurityTest(unittest.TestCase):
    def test_resolve_legacy_path_rejects_path_outside_roots(self):
        with tempfile.TemporaryDirectory() as root_dir:
            root = Path(root_dir) / "root"
            root.mkdir()

            outside = root.parent / "outside.txt"
            outside.write_text("outside")

            with self.assertRaises(ValueError):
                offline_server._resolve_legacy_path(str(outside), [str(root)])

    def test_resolve_legacy_path_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as root_dir:
            root = Path(root_dir) / "root"
            root.mkdir()
            outside = Path(root_dir) / "outside"
            outside.mkdir()
            target = outside / "secret.txt"
            target.write_text("secret")

            (root / "link_to_outside").symlink_to(outside)

            with self.assertRaises(ValueError):
                offline_server._resolve_legacy_path(
                    str(root / "link_to_outside" / "secret.txt"),
                    [str(root)]
                )

    def test_stop_offline_proc_clears_running_proc(self):
        class FakeProc:
            def __init__(self):
                self.terminated = False

            def poll(self):
                return None

            def terminate(self):
                self.terminated = True

        fake_proc = FakeProc()
        offline_server._current_proc = fake_proc

        stopped, message = offline_server._stop_offline_proc()

        self.assertTrue(stopped)
        self.assertIsNone(offline_server._current_proc)
        self.assertTrue(fake_proc.terminated)
        self.assertEqual(message, "offline process terminated")

    def test_stop_offline_proc_fallback_to_docker_stop(self):
        with patch("offline_server.subprocess.run") as mock_run:
            mock_run.return_value = type("Completed", (), {
                "returncode": 0,
                "stdout": "container stopped",
                "stderr": "",
            })()
            offline_server._current_proc = None

            stopped, message = offline_server._stop_offline_proc()

            self.assertTrue(stopped)
            self.assertEqual(message, "offline docker stopped")
            mock_run.assert_called_once_with(
                ["docker", "stop", "perception_offline_runner"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

    def test_run_offline_test_clears_current_proc_in_finally(self):
        class FakeProc:
            def __init__(self):
                self.stdout = iter([b"line\n"])
                self.returncode = 0

            def wait(self):
                self.returncode = 0

            def poll(self):
                return self.returncode

        fake_proc = FakeProc()

        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            input_dir.mkdir()
            with patch("offline_server.subprocess.run") as mock_run:
                mock_run.return_value = type("Completed", (), {
                    "stdout": "img-id",
                    "returncode": 0,
                })()
                with patch("offline_server.subprocess.Popen", return_value=fake_proc):
                    offline_server.run_offline_test(str(input_dir), 6, 205, False, False)

        self.assertIsNone(offline_server._current_proc)
        self.assertFalse(offline_server._running)


class ConfigLoaderMigrationFixTest(unittest.TestCase):
    def test_default_config_resolves_key_relative_to_conf_dir(self):
        with patch.object(config_loader.Path, "exists", return_value=False), \
             patch.dict("os.environ", {}, clear=True):
            cfg = config_loader.load_ssh_config()

        self.assertEqual(cfg["ssh_key_path"], str((config_loader.CONF_DIR / "bestmow_rsa_202604").resolve()))

    def test_env_overrides_apply_when_config_file_missing(self):
        with patch.object(config_loader.Path, "exists", return_value=False), \
             patch.dict("os.environ", {"SSH_KEY": "custom_key", "ROBOT_HOST": "10.0.0.2", "ROBOT_USER": "tester", "ROBOT_PORT": "10022"}, clear=True):
            cfg = config_loader.load_ssh_config()

        self.assertEqual(cfg["ssh_key_path"], str((config_loader.CONF_DIR / "custom_key").resolve()))
        self.assertEqual(cfg["ssh_host"], "10.0.0.2")
        self.assertEqual(cfg["ssh_user"], "tester")
        self.assertEqual(cfg["ssh_port"], 10022)


if __name__ == "__main__":
    unittest.main()
