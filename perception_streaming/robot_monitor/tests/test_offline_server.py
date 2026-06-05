import struct
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TEST_DIR = Path(__file__).resolve().parent
ROBOT_MONITOR_DIR = TEST_DIR.parent
if str(ROBOT_MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(ROBOT_MONITOR_DIR))

import offline_server  # noqa: E402


class OfflineServerFilterStereoImageSizeTest(unittest.TestCase):
    def test_filter_stereo_image_size_reads_png_size_without_pil(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            kept = folder / "kept.png"
            moved = folder / "moved.png"
            png_sig = b"\x89PNG\r\n\x1a\n"
            kept.write_bytes(png_sig + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 1280, 480) + b"\x08\x02\x00\x00\x00" + b"\x00\x00\x00\x00")
            moved.write_bytes(png_sig + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 640, 480) + b"\x08\x02\x00\x00\x00" + b"\x00\x00\x00\x00")

            with patch.object(offline_server, "PIL_AVAILABLE", False), \
                 patch.object(offline_server, "Image", None):
                result = offline_server._filter_stereo_image_size(str(folder))

            self.assertEqual(result["errors"], [])
            self.assertEqual(result["scanned_count"], 2)
            self.assertEqual(result["kept_count"], 1)
            self.assertEqual(result["moved_count"], 1)
            self.assertTrue(kept.exists())
            self.assertFalse(moved.exists())
            self.assertTrue((folder / "other_size" / "moved.png").exists())
            self.assertEqual(result["moved"][0]["size"], [640, 480])

    def test_filter_stereo_image_size_reads_jpeg_size_without_pil(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            kept = folder / "kept.jpg"
            moved = folder / "moved.jpg"

            def jpeg_bytes(width, height):
                return (
                    b"\xff\xd8"
                    + b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
                    + b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", height, width) + b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00"
                    + b"\xff\xd9"
                )

            kept.write_bytes(jpeg_bytes(1280, 480))
            moved.write_bytes(jpeg_bytes(1280, 720))

            with patch.object(offline_server, "PIL_AVAILABLE", False), \
                 patch.object(offline_server, "Image", None):
                result = offline_server._filter_stereo_image_size(str(folder))

            self.assertEqual(result["errors"], [])
            self.assertEqual(result["scanned_count"], 2)
            self.assertEqual(result["kept_count"], 1)
            self.assertEqual(result["moved_count"], 1)
            self.assertTrue(kept.exists())
            self.assertFalse(moved.exists())
            self.assertTrue((folder / "other_size" / "moved.jpg").exists())
            self.assertEqual(result["moved"][0]["size"], [1280, 720])


class OfflineServerUploadImagesSshKeyTest(unittest.TestCase):
    def test_upload_images_range_reads_current_ssh_key_path_at_call_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_key = str(Path(tmp) / "bestmow_rsa_202605")
            current_key = str(Path(tmp) / "bestmow_rsa_202606")
            calls = []

            def fake_run(cmd, **kwargs):
                calls.append(cmd)
                if cmd[0] == "ssh":
                    return subprocess.CompletedProcess(cmd, 0, stdout="20260602\n", stderr="")
                if cmd[0] == "rsync":
                    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
                raise AssertionError(f"unexpected command: {cmd}")

            with patch.object(offline_server, "SSH_KEY", old_key), \
                 patch.object(offline_server, "get_ssh_key_path", return_value=current_key), \
                 patch.object(offline_server, "LOCAL_IMAGE_BASE", str(Path(tmp) / "stereo_debug")), \
                 patch.object(offline_server.subprocess, "run", side_effect=fake_run):
                result = offline_server.upload_images_range_from_robot(10115, "20260602", "20260605")

            self.assertTrue(result["ok"])
            rsync_ssh_command = calls[1][calls[1].index("-e") + 1]
            self.assertIn(current_key, calls[0])
            self.assertIn(f"ssh -i {current_key}", rsync_ssh_command)
            self.assertNotIn(old_key, calls[0])
            self.assertNotIn(f"ssh -i {old_key}", rsync_ssh_command)


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

    def test_build_night_output_dir_respects_non_k100_suffix(self):
        folder = "data/stereo_debug/7958/20260505"

        self.assertEqual(
            offline_server.build_output_dir(folder, 7, use_k100=False),
            "data/stereo_debug/7958/20260505/dsg_7_205_384",
        )
        self.assertEqual(
            offline_server.build_pointcloud_dir(folder, 7, use_k100=False),
            "data/stereo_debug/7958/20260505/pcd_7_205_384",
        )

    def test_native_offline_config_uses_non_k100_night_suffixes(self):
        config_path = ROBOT_MONITOR_DIR.parent / "stereo_perception_multi2_offline_test" / "include" / "offline_config.hpp"
        config_text = config_path.read_text()

        self.assertIn('input_dir + (use_k100_mode ? "/dsg_7_205_432" : "/dsg_7_205_384")', config_text)
        self.assertIn('input_dir + (use_k100_mode ? "/pcd_7_205_432" : "/pcd_7_205_384")', config_text)

    def test_bestmow_cdt_label_depends_on_day_or_night_mode(self):
        processor_path = ROBOT_MONITOR_DIR.parent / "stereo_perception_multi2_offline_test" / "src" / "offline_processor.cpp"
        processor_text = processor_path.read_text()

        self.assertIn("bestMowCdtLabelForMode", processor_text)
        self.assertIn("return infer_mode == 7 ? 3 : 2;", processor_text)
        self.assertIn("label_map(cdt_rect).setTo(cdt_label);", processor_text)

    def test_model7_k100_keeps_432_field_for_fusion_after_384_inference(self):
        processor_path = ROBOT_MONITOR_DIR.parent / "stereo_perception_multi2_offline_test" / "src" / "offline_processor.cpp"
        processor_text = processor_path.read_text()
        start = processor_text.index("OfflineProcessor::ProcessResult OfflineProcessor::processModel7")
        end = processor_text.index("void OfflineProcessor::saveResults", start)
        model7_text = processor_text[start:end]

        self.assertIn("cv::resize(cropped_img, resized_img, cv::Size(640, 384)", model7_text)
        self.assertIn("const int fusion_height = hardware_mode_.isK100Hardware() ? 432 : 384;", model7_text)
        self.assertIn("cv::resize(lab_dst, fusion_label, cv::Size(640, fusion_height), 0, 0, cv::INTER_NEAREST);", model7_text)
        self.assertIn("result.depth = depth_480(cv::Rect(0, 0, 640, fusion_height)).clone();", model7_text)
        self.assertIn("dsg_fusion_img", model7_text)
        self.assertNotIn("cv::resize(depth_432, result.depth, cv::Size(640, 384)", model7_text)

    def test_model7_k100_applies_reference_depth_morphology(self):
        processor_path = ROBOT_MONITOR_DIR.parent / "stereo_perception_multi2_offline_test" / "src" / "offline_processor.cpp"
        processor_text = processor_path.read_text()
        start = processor_text.index("OfflineProcessor::ProcessResult OfflineProcessor::processModel7")
        end = processor_text.index("void OfflineProcessor::saveResults", start)
        model7_text = processor_text[start:end]

        self.assertIn("cv::morphologyEx(depth_480, opened_depth, cv::MORPH_OPEN, kernel);", model7_text)
        self.assertIn("cv::morphologyEx(opened_depth, closed_depth, cv::MORPH_CLOSE, kernel);", model7_text)

    def test_night_adaptive_stereo_params_match_reference_normal_quality_path(self):
        matcher_path = ROBOT_MONITOR_DIR.parent / "offline_perception_debug_src" / "src" / "stereo_multi_match.cpp"
        matcher_text = matcher_path.read_text()
        start = matcher_text.index("void StereoMultiMatch::stereo_multi_param_init_6m_adaptive")
        end = matcher_text.index("cv::Mat StereoMultiMatch::backgroundSubstract", start)
        adaptive_text = matcher_text[start:end]

        self.assertIn("stereo_block_matcher_->setBlockSize(13);", adaptive_text)
        self.assertIn("stereo_block_matcher_->setSpeckleWindowSize(64);", adaptive_text)
        self.assertIn("stereo_block_matcher_->setSpeckleRange(16);", adaptive_text)
        self.assertIn("stereo_block_matcher_->setTextureThreshold(5);", adaptive_text)
        self.assertIn("stereo_block_matcher_->setUniquenessRatio(4);", adaptive_text)
        self.assertIn("half_top_stereo_block_matcher_->setBlockSize(13);", adaptive_text)
        self.assertIn("half_top_stereo_block_matcher_->setSpeckleWindowSize(80);", adaptive_text)

    def test_stereo_base_calibration_matches_reference_project(self):
        matcher_path = ROBOT_MONITOR_DIR.parent / "offline_perception_debug_src" / "src" / "stereo_multi_match.cpp"
        matcher_text = matcher_path.read_text()
        start = matcher_text.index("void StereoMultiMatch::stereo_base_param_init")
        end = matcher_text.index("void StereoMultiMatch::stereo_dis_init", start)
        base_param_text = matcher_text[start:end]

        self.assertIn("244.9567633", base_param_text)
        self.assertIn("321.05016538", base_param_text)
        self.assertIn("234.44410892", base_param_text)
        self.assertIn("-19.57480185", base_param_text)
        self.assertNotIn("245.1634049359", base_param_text)

    def test_model7_dsg_argmax_label_map_matches_reference(self):
        dsg_path = ROBOT_MONITOR_DIR.parent / "offline_perception_debug_src" / "src" / "dsg_perception.cpp"
        dsg_text = dsg_path.read_text()
        start = dsg_text.index("void dsg_perception::lab_match")
        end = dsg_text.index("int dsg_perception::get_tensor_hwc_index", start)
        lab_match_text = dsg_text[start:end]

        self.assertIn("top_index[0] == 1", lab_match_text)
        self.assertIn("match_label = 1;", lab_match_text)
        self.assertIn("top_index[0] == 2", lab_match_text)
        self.assertIn("match_label = 5;", lab_match_text)
        self.assertIn("top_index[0] == 3", lab_match_text)
        self.assertIn("match_label = 3;", lab_match_text)
        self.assertNotIn("top_index[0] == 1) {\n                    match_label = 5;", lab_match_text)

    def test_model7_uses_reference_dsg_pointcloud_fusion(self):
        processor_path = ROBOT_MONITOR_DIR.parent / "stereo_perception_multi2_offline_test" / "src" / "offline_processor.cpp"
        matcher_path = ROBOT_MONITOR_DIR.parent / "offline_perception_debug_src" / "src" / "stereo_multi_match.cpp"
        header_path = ROBOT_MONITOR_DIR.parent / "offline_perception_debug_src" / "include" / "stereo_multi_match.h"
        processor_text = processor_path.read_text()
        matcher_text = matcher_path.read_text()
        header_text = header_path.read_text()

        start = processor_text.index("OfflineProcessor::ProcessResult OfflineProcessor::processModel7")
        end = processor_text.index("void OfflineProcessor::saveResults", start)
        model7_text = processor_text[start:end]

        self.assertIn("stereo_process_pci_depth_rgb_seg_det_fusion_dsg", header_text)
        self.assertIn("stereo_process_pci_depth_rgb_seg_det_fusion_dsg", model7_text)
        self.assertNotIn("stereo_process_pci_depth_rgb_seg_det_fusion(\n            result.depth, fusion_label", model7_text)

        start = matcher_text.index("void StereoMultiMatch::stereo_process_pci_depth_rgb_seg_det_fusion_dsg")
        end = matcher_text.index("void StereoMultiMatch::stereo_point_ori_rgb_filter", start)
        dsg_fusion_text = matcher_text[start:end]

        self.assertIn("for (int y = 0; y < safe_rows; y += 4)", dsg_fusion_text)
        self.assertIn("if (pc_rgbl.label == 1)", dsg_fusion_text)
        self.assertIn("if (d < 1.5f)", dsg_fusion_text)
        self.assertIn("if (valid_neighbors < 2)", dsg_fusion_text)
        self.assertIn("pc_rgbl.z < 0.3f && (pc_rgbl.label == 2 || pc_rgbl.label == 3)", dsg_fusion_text)

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

    def test_find_existing_result_falls_back_to_available_day_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "data" / "stereo_debug" / "7958" / "20260504"
            day_output = folder / "sub_6_205_432"
            day_pcd = folder / "pcd_6_205_432"
            day_output.mkdir(parents=True)
            day_pcd.mkdir(parents=True)
            (day_output / "frame_0001_combined.jpg").write_bytes(b"jpg")
            (day_pcd / "frame_0001.pcd").write_text("VERSION .7\n")

            result = offline_server._find_existing_result(
                str(folder),
                prefer_mode=6,
                use_k100=False,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["infer_mode"], 6)
            self.assertEqual(result["output_dir"], str(day_output))
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

    def test_terminate_current_process_stops_running_child(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        offline_server._current_proc = proc
        try:
            self.assertTrue(offline_server._terminate_current_process(timeout=1.0))
            self.assertIsNotNone(proc.poll())
            self.assertIsNone(offline_server._current_proc)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=2)
            offline_server._current_proc = None


if __name__ == "__main__":
    unittest.main()
