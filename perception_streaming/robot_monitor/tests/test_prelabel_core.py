import sys
import tempfile
import threading
import unittest
import hashlib
from pathlib import Path
from unittest.mock import ANY, Mock, patch

TEST_DIR = Path(__file__).resolve().parent
ROBOT_MONITOR_DIR = TEST_DIR.parent
if str(ROBOT_MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(ROBOT_MONITOR_DIR))

from prelabel_pipeline import core


class PrelabelCoreTest(unittest.TestCase):
    def test_shadow_pipeline_blocks_import_when_uploaded_frame_bytes_differ(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            image = source / "one.jpg"
            image.write_bytes(b"not-a-real-image")
            adapters = {
                "freeze_batch": lambda *_: {"batch_id": "batch", "snapshot_hash": "snapshot", "snapshot_path": str(source)},
                "materialize_branch_input": lambda *_: source,
                "create_task": lambda branch, *_args, **_kwargs: {"id": 1 if branch == "A" else 2},
                "upload": lambda *_: None,
                "frames": lambda *_: [{"id": 7, "name": "one.jpg", "width": 1, "height": 1}],
                "frame_bytes": lambda *_: b"changed",
                "baseline": lambda *_: b"<annotations/>",
                "alpha50": lambda *_: b"<annotations/>",
                "import": Mock(),
                "cleanup": lambda *_: None,
            }
            snapshot = {"batch_id": "batch", "snapshot_hash": "snapshot", "files": [{"path": "one.jpg", "sha256": hashlib.sha256(b"original").hexdigest(), "original_dimensions": {"width": 1, "height": 1}}]}
            result = core.run_shadow_pipeline("rid", "task", [str(source)], {"shadow_adapters": adapters, "shadow_snapshot": snapshot}, {"shadow_root": tmp}, None)
            self.assertEqual(result["branches"]["A"]["status"], "failed")
            self.assertIn("frame verification", result["branches"]["A"]["error"])
            adapters["import"].assert_not_called()

    def test_shadow_pipeline_emits_review_manifest_only_after_both_attested_branches(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_bytes = b"original"
            snapshot = {"batch_id": "batch", "snapshot_hash": "snapshot", "files": [{"path": "one.jpg", "sha256": hashlib.sha256(image_bytes).hexdigest(), "original_dimensions": {"width": 1, "height": 1}}]}
            imported = Mock()
            adapters = {
                "materialize_branch_input": lambda *_: Path(tmp),
                "create_task": lambda branch, *_args, **_kwargs: {"id": 1 if branch == "A" else 2},
                "upload": lambda *_: None,
                "frames": lambda *_: [{"id": 0, "name": "one.jpg", "width": 1, "height": 1}],
                "frame_bytes": lambda *_args, **_kwargs: image_bytes,
                "baseline": lambda *_: Path(tmp) / "a.xml",
                "alpha50": lambda *_: Path(tmp) / "b.xml",
                "import": imported,
                "cleanup": lambda *_: None,
            }
            result = core.run_shadow_pipeline("rid", "task", [tmp], {"shadow_adapters": adapters, "shadow_snapshot": snapshot}, {"shadow_root": tmp}, None)
            self.assertTrue(result["review_ready"])
            self.assertEqual(result["common_success"], ["one.jpg"])
            self.assertEqual(result["common_success_manifest"]["images"][0]["branches"]["A"]["frame_id"], 0)
            self.assertEqual(imported.call_count, 2)

    def test_shadow_candidate_preflight_owns_b_task_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = b"image"
            snapshot = {"batch_id": "batch", "snapshot_hash": "snapshot", "files": [{"path": "one.jpg", "sha256": hashlib.sha256(raw).hexdigest(), "original_dimensions": {"width": 1, "height": 1}}]}
            created = Mock(side_effect=lambda branch, *_args, **_kwargs: {"id": 1})
            adapters = {"materialize_branch_input": lambda *_: Path(tmp), "create_task": created, "candidate_preflight": lambda *_: {"task": {"id": 2}}, "upload": lambda *_: None, "frames": lambda *_: [{"id": 0, "name": "one.jpg", "width": 1, "height": 1}], "frame_bytes": lambda *_args, **_kwargs: raw, "baseline": lambda *_: "a", "alpha50": lambda *_: "b", "import": lambda *_: None, "cleanup": lambda *_: None}
            result = core.run_shadow_pipeline("rid", "task", [tmp], {"shadow_adapters": adapters, "shadow_snapshot": snapshot}, {"shadow_root": tmp}, None)
            self.assertEqual(created.call_count, 1)
            self.assertEqual(result["branches"]["B"]["task_id"], 2)
    def test_build_predict_cmd_keeps_opts_last(self):
        cfg = {
            "demo_dir": "/demo",
            "config": "/cfg.yaml",
            "weights": "/w.pth",
            "min_area": 50,
            "smooth_contours": True,
            "fill_holes": True,
        }

        docker_cmd, inner = core.build_predict_cmd("/input", "/output", 123, cfg, "MPformer")

        self.assertEqual(docker_cmd[:3], ["docker", "exec", "MPformer"])
        self.assertTrue(inner.endswith("--opts MODEL.WEIGHTS /w.pth"))

    def test_build_predict_cmd_quotes_shell_paths(self):
        cfg = {
            "demo_dir": "/demo dir",
            "config": "/cfg dir/config.yaml",
            "weights": "/weights dir/model.pth",
        }

        docker_cmd, inner = core.build_predict_cmd("/input dir", "/output dir", 123, cfg, "MPformer")

        self.assertIn("'/input dir'", inner)
        self.assertIn("'/output dir'", inner)
        self.assertIn("cd '/demo dir' &&", docker_cmd[-1])

    def test_cuda_error_detection(self):
        self.assertTrue(core.is_cuda_error(["RuntimeError: CUDA error"]))
        self.assertTrue(core.is_cuda_error("No CUDA GPUs are available"))
        self.assertFalse(core.is_cuda_error(["ordinary failure"]))

    def test_label_mapping_is_module_local(self):
        mapping = core.build_label_mapping()

        self.assertIn("lawn", mapping)
        self.assertEqual(mapping["lawn"], "lawn草地")

    def test_convert_labels_in_xml_updates_definitions_and_polygons(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "annotations.xml"
            dst = Path(tmp) / "annotations_cvat.xml"
            src.write_text(
                """<?xml version="1.0" encoding="utf-8"?>
<annotations>
  <meta><task><labels><label><name>lawn</name></label></labels></task></meta>
  <image id="0" name="a.jpg"><polygon label="lawn" points="0,0;1,1"/></image>
</annotations>
""",
                encoding="utf-8",
            )

            self.assertTrue(core.convert_labels_in_xml(src, {"lawn": "lawn草地"}, dst))
            converted = dst.read_text(encoding="utf-8")

        self.assertIn("lawn草地", converted)
        self.assertNotIn("<name>lawn</name>", converted)
        self.assertNotIn('label="lawn"', converted)

    def test_cvat_session_disables_environment_proxy_and_uses_cache_lock(self):
        server = {
            "id": "local",
            "host": "localhost",
            "port": 8080,
            "user": "u",
            "password": "p",
        }
        session = Mock()
        session.headers = {}
        login_response = Mock()
        login_response.json.return_value = {"key": "token"}
        session.post.return_value = login_response

        with patch.object(core, "_cvat_session_cache", {}), \
             patch.object(core._requests, "Session", return_value=session):
            first_session, first_base = core.cvat_session(server)
            second_session, second_base = core.cvat_session(server)

        self.assertIs(first_session, session)
        self.assertIs(second_session, session)
        self.assertEqual(first_base, "http://localhost:8080")
        self.assertEqual(second_base, first_base)
        self.assertFalse(session.trust_env)
        session.post.assert_called_once()

    def test_upload_only_emits_skipped_steps(self):
        cfg = {
            "segment_size": 1000,
            "model": {"min_area": 50},
            "cvat_servers": [{"id": "local", "host": "localhost", "port": 8080, "user": "u", "password": "p"}],
        }
        logs = []
        with patch.object(core, "step1_upload", return_value=(Mock(), 10, 20)), \
             patch.object(core, "step5_assign", return_value=None):
            result = core.run_pipeline(
                "rid",
                "task",
                ["/tmp/images"],
                {"skip_steps": [2, 3, 4]},
                cfg,
                logs.append,
            )

        self.assertEqual(result[0]["status"], "success")
        skip_events = [entry for entry in logs if isinstance(entry, dict) and entry.get("type") == "step_skip"]
        self.assertEqual([e["step"] for e in skip_events], [2, 3, 4])
        progress_logs = [entry for entry in logs if entry in ("[进度] 80%", "[进度] 100%")]
        self.assertEqual(progress_logs, ["[进度] 80%", "[进度] 100%"])

    def test_run_pipeline_full_flow_emits_log_events_and_assigns(self):
        cfg = {
            "output_base": "/tmp/out",
            "segment_size": 1000,
            "model": {"min_area": 50},
            "docker": {"container": "MPformer"},
            "cvat_servers": [{"id": "local", "host": "localhost", "port": 8080, "user": "u", "password": "p"}],
        }
        logs = []
        events = []
        client = Mock()

        with patch.object(core, "step1_upload", return_value=(client, 10, 20)) as step1, \
             patch.object(core, "step2_predict", return_value=Path("/tmp/out/images/annotations.xml")) as step2, \
             patch.object(core, "step3_rename", return_value=Path("/tmp/out/images/annotations_cvat.xml")) as step3, \
             patch.object(core, "step4_import", return_value="http://localhost:8080/tasks/10") as step4, \
             patch.object(core, "step5_assign", return_value=None) as step5, \
             patch.object(core.os, "makedirs"):
            result = core.run_pipeline(
                "rid",
                "task",
                ["/tmp/images"],
                {"assignee_id": "7", "event_fn": events.append},
                cfg,
                logs.append,
            )

        self.assertEqual(result[0]["status"], "success")
        self.assertEqual(result[0]["cvat_url"], "http://localhost:8080/tasks/10")
        step1.assert_called_once()
        step2.assert_called_once()
        step3.assert_called_once()
        step4.assert_called_once()
        step5.assert_called_once_with(10, 7, cfg, ANY)
        self.assertTrue(any(event.get("type") == "log" and "处理目录" in event.get("msg", "") for event in events))
        self.assertTrue(any(event.get("type") == "pipeline_done" for event in events))

    def test_run_pipeline_propagates_step_event_sequence(self):
        cfg = {
            "output_base": "/tmp/out",
            "segment_size": 1000,
            "model": {"min_area": 50},
            "docker": {"container": "MPformer"},
            "cvat_servers": [{"id": "local", "host": "localhost", "port": 8080, "user": "u", "password": "p"}],
        }
        events = []
        client = Mock()

        def step1(task_name, input_dir, config, log_fn, extra_image_files=None):
            log_fn({"type": "step_start", "step": 1, "msg": "upload"})
            log_fn({"type": "step_done", "step": 1, "status": "success", "msg": "upload done"})
            return client, 10, 20

        def step2(input_dir, output_dir, job_id, config, log_fn, **kwargs):
            log_fn({"type": "step_start", "step": 2, "msg": "predict"})
            log_fn({"type": "step_done", "step": 2, "status": "success", "msg": "predict done"})
            return Path("/tmp/out/images/annotations.xml")

        def step3(xml_path, config, log_fn):
            log_fn({"type": "step_start", "step": 3, "msg": "rename"})
            log_fn({"type": "step_done", "step": 3, "status": "success", "msg": "rename done"})
            return Path("/tmp/out/images/annotations_cvat.xml")

        def step4(client_arg, task_id, xml_path, config, log_fn):
            log_fn({"type": "step_start", "step": 4, "msg": "import"})
            log_fn({"type": "step_done", "step": 4, "status": "success", "msg": "import done"})
            return "http://localhost:8080/tasks/10"

        def step5(task_id, assignee_id, config, log_fn):
            log_fn({"type": "step_start", "step": 5, "msg": "assign"})
            log_fn({"type": "step_done", "step": 5, "status": "success", "msg": "assign done"})

        with patch.object(core, "step1_upload", side_effect=step1), \
             patch.object(core, "step2_predict", side_effect=step2), \
             patch.object(core, "step3_rename", side_effect=step3), \
             patch.object(core, "step4_import", side_effect=step4), \
             patch.object(core, "step5_assign", side_effect=step5), \
             patch.object(core.os, "makedirs"):
            core.run_pipeline("rid", "task", ["/tmp/images"], {"assignee_id": "7", "event_fn": events.append}, cfg, None)

        step_events = [(event["type"], event["step"]) for event in events if event.get("type") in {"step_start", "step_done"}]
        self.assertEqual(
            step_events,
            [
                ("step_start", 1), ("step_done", 1),
                ("step_start", 2), ("step_done", 2),
                ("step_start", 3), ("step_done", 3),
                ("step_start", 4), ("step_done", 4),
                ("step_start", 5), ("step_done", 5),
            ],
        )

    def test_skip_steps_accepts_none_strings_and_bad_values(self):
        self.assertEqual(core._skip_steps_from_params({"skip_steps": None}), set())
        self.assertEqual(core._skip_steps_from_params({"skip_steps": "2, 3, bad, 99"}), {2, 3})
        self.assertEqual(core._skip_steps_from_params({"skip_steps": 4}), {4})
        self.assertEqual(core._skip_steps_from_params({"upload_only": True, "skip_steps": ""}), {2, 3, 4})

    def test_step2_returns_none_when_cancelled_waiting_for_gpu(self):
        logs = []
        cfg = {
            "model": {"demo_dir": "/demo", "config": "/cfg.yaml", "weights": "/w.pth"},
            "docker": {"container": "MPformer"},
        }
        result = core.step2_predict(
            "/input",
            "/output",
            20,
            cfg,
            logs.append,
            cancel_fn=lambda: True,
            params={"gpu_semaphore": threading.Semaphore(0)},
        )

        self.assertIsNone(result)
        self.assertTrue(any("等待 GPU 时任务被取消" in entry for entry in logs if isinstance(entry, str)))

    def test_step5_assign_patches_task_and_jobs(self):
        session = Mock()
        task_response = Mock()
        task_response.json.return_value = {"assignee": {"username": "alice"}}
        jobs_response = Mock()
        jobs_response.json.return_value = {"results": [{"id": 101}, {"id": 102}]}
        session.patch.return_value = task_response
        session.get.return_value = jobs_response
        cfg = {"cvat_servers": [{"id": "local", "host": "localhost", "port": 8080, "user": "u", "password": "p"}]}

        with patch.object(core, "cvat_session", return_value=(session, "http://localhost:8080")):
            core.step5_assign(10, 7, cfg, Mock())

        session.patch.assert_any_call("http://localhost:8080/api/tasks/10", json={"assignee_id": 7}, timeout=10)
        session.get.assert_called_once_with("http://localhost:8080/api/jobs?task_id=10&page_size=100", timeout=10)
        session.patch.assert_any_call("http://localhost:8080/api/jobs/101", json={"assignee": 7}, timeout=10)
        session.patch.assert_any_call("http://localhost:8080/api/jobs/102", json={"assignee": 7}, timeout=10)

    def test_public_package_exports_core_entrypoints(self):
        from prelabel_pipeline import run_pipeline, run_prelabel_pipeline

        self.assertIs(run_pipeline, core.run_pipeline)
        self.assertIs(run_prelabel_pipeline, core.run_prelabel_pipeline)

    def test_run_pipeline_honors_cancel_event_before_start(self):
        cancel_event = threading.Event()
        cancel_event.set()
        logs = []

        result = core.run_pipeline(
            "rid",
            "task",
            ["/tmp/images"],
            {"cancel_event": cancel_event},
            {"model": {}, "cvat_servers": []},
            logs.append,
        )

        self.assertEqual(result, [])
        self.assertTrue(any("已取消" in entry for entry in logs if isinstance(entry, str)))
