import io
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

TEST_DIR = Path(__file__).resolve().parent
ROBOT_MONITOR_DIR = TEST_DIR.parent
if str(ROBOT_MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(ROBOT_MONITOR_DIR))

from prelabel_pipeline import run_state, routes, shadow_review


class FakeHandler:
    def __init__(self, body=b"", headers=None):
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.headers = headers or {}
        self.status = None
        self.sent_headers = []

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.sent_headers.append((key, value))

    def end_headers(self):
        pass


def parsed(path, query=""):
    return SimpleNamespace(path=path, query=query)


class PrelabelRoutesTest(unittest.TestCase):
    def test_shadow_review_asset_proxies_rendered_x_or_y_without_private_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            from PIL import Image
            root = Path(tmp); image = root / "images" / "private.png"; image.parent.mkdir()
            Image.new("RGB", (4, 3), "black").save(image)
            xml_a = root / "a.xml"; xml_b = root / "b.xml"
            xml_a.write_text('<annotations><image id="0" name="private.png" width="4" height="3"><polygon label="a" points="0,0;3,0;3,2"/></image></annotations>')
            xml_b.write_text('<annotations><image id="0" name="private.png" width="4" height="3"><polygon label="b" points="0,2;3,2;3,0"/></image></annotations>')
            run_state.runs.clear()
            shadow = {"review_ready": True, "batch_id": "batch", "snapshot_hash": "hash", "snapshot_path": str(root), "common_success_manifest": {"images": [{"path": "private.png", "branches": {"A": {}, "B": {}}}]}, "branches": {"A": {"annotation_path": str(xml_a)}, "B": {"annotation_path": str(xml_b)}}}
            run_state.runs["abcdef123456"] = run_state.make_runtime_run("shadow", [], owner_token="owner", shadow=shadow)
            review = shadow_review.create_review(shadow["common_success_manifest"], seed="batch:hash")
            run_state.runs["abcdef123456"]["shadow"]["review"] = review
            token = shadow_review.issue_reviewer_capability(review)
            handler = FakeHandler()
            routes.handle(handler, parsed("/prelabel/runs/abcdef123456/review/assets/s001/X", f"review_token={token}"))
            self.assertEqual(handler.status, 200, handler.wfile.getvalue())
            self.assertIn(("Content-Type", "image/png"), handler.sent_headers)
            self.assertTrue(handler.wfile.getvalue().startswith(b"\x89PNG"))
            self.assertNotIn(b"private.png", handler.wfile.getvalue())

    def test_review_annotation_rejects_excessive_or_nonfinite_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "annotations.xml"
            points = ";".join("0,0" for _ in range(2001))
            path.write_text(f'<annotations><image name="one.png"><polygon points="{points}"/></image></annotations>')
            with self.assertRaisesRegex(ValueError, "point limit"):
                routes._annotation_polygons(str(path), "one.png")
            path.write_text('<annotations><image name="one.png"><polygon points="NaN,0;0,0;0,1"/></image></annotations>')
            with self.assertRaisesRegex(ValueError, "non-finite"):
                routes._annotation_polygons(str(path), "one.png")

    def test_shadow_review_public_payload_is_anonymous_and_submission_is_single_use(self):
        run_state.runs.clear()
        manifest = {"images": [{"path": "private/image.jpg", "branches": {"A": {"task_id": 1}, "B": {"task_id": 2}}} for _ in range(2)]}
        run_state.runs["abcdef123456"] = run_state.make_runtime_run("shadow", [], owner_token="owner", shadow={"review_ready": True, "batch_id": "batch", "snapshot_hash": "hash", "common_success_manifest": manifest})
        handler = FakeHandler()
        routes.handle(handler, parsed("/prelabel/runs/abcdef123456/review"))
        self.assertEqual(handler.status, 403, self._json_payload(handler))
        body = json.dumps({"owner_token": "owner"}).encode()
        handler = FakeHandler(body, {"Content-Length": str(len(body))}); handler.command = "POST"
        routes.handle(handler, parsed("/prelabel/runs/abcdef123456/review/invites"))
        capability = self._json_payload(handler)["review_token"]
        handler = FakeHandler()
        routes.handle(handler, parsed("/prelabel/runs/abcdef123456/review", f"review_token={capability}"))
        payload = self._json_payload(handler)
        self.assertEqual(handler.status, 200, payload)
        self.assertNotIn("private", json.dumps(payload))
        answers = {item["sample_id"]: "tie" for item in payload["samples"]}
        body = json.dumps({"review_token": capability, "answers": answers}).encode()
        handler = FakeHandler(body, {"Content-Length": str(len(body))})
        handler.command = "POST"
        routes.handle(handler, parsed("/prelabel/runs/abcdef123456/review"))
        submission = self._json_payload(handler)
        self.assertEqual(handler.status, 200, submission)
        self.assertNotIn("candidate_wins", json.dumps(submission))
        self.assertNotIn("baseline_wins", json.dumps(submission))
        handler = FakeHandler(body, {"Content-Length": str(len(body))})
        handler.command = "POST"
        routes.handle(handler, parsed("/prelabel/runs/abcdef123456/review"))
        self.assertEqual(handler.status, 409, self._json_payload(handler))

    def test_shadow_review_reveal_requires_owner_and_completed_submission(self):
        run_state.runs.clear()
        manifest = {"images": [{"path": "private/image.jpg", "branches": {"A": {}, "B": {}}}]}
        run_state.runs["abcdef123456"] = run_state.make_runtime_run("shadow", [], owner_token="owner", shadow={"review_ready": True, "batch_id": "batch", "snapshot_hash": "hash", "common_success_manifest": manifest})
        handler = FakeHandler()
        routes.handle(handler, parsed("/prelabel/runs/abcdef123456/review/reveal"))
        self.assertEqual(handler.status, 403, self._json_payload(handler))
        body = json.dumps({"owner_token": "owner"}).encode()
        handler = FakeHandler(body, {"Content-Length": str(len(body))})
        routes.handle(handler, parsed("/prelabel/runs/abcdef123456/review/reveal"))
        self.assertEqual(handler.status, 409, self._json_payload(handler))

    def test_shadow_route_builds_production_adapters_not_request_callbacks(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = json.dumps({"task_prefix": "shadow", "owner_token": "owner", "input_dirs": [tmp], "shadow_adapters": {"evil": "ignored"}}).encode()
            handler = FakeHandler(body, {"Content-Length": str(len(body))})
            snapshot = {"batch_id": "batch", "snapshot_hash": "hash", "snapshot_path": tmp}
            factory = Mock(return_value={"cleanup": Mock()})
            class ImmediateThread:
                def __init__(self, target, daemon): self.target = target
                def start(self): self.target()
            with patch.object(routes.config_manager, "load_config", return_value={"browse_roots": [tmp], "runs_dir": str(Path(tmp) / "runs")}), \
                 patch.object(routes, "_validated_inputs", return_value=([tmp], None)), \
                 patch.object(routes, "freeze_batch", return_value=snapshot), \
                 patch.object(routes.core, "build_shadow_adapters", factory), \
                 patch.object(routes.core, "run_shadow_pipeline", return_value={"status": "failed", "branches": {}}), \
                 patch.object(routes.threading, "Thread", ImmediateThread):
                routes.handle(handler, parsed("/prelabel/shadow-run"))
            self.assertEqual(handler.status, 200, self._json_payload(handler))
            factory.assert_called_once()
            self.assertEqual(self._json_payload(handler)["batch_id"], "batch")

    def test_shadow_reconcile_requires_owner_token_before_orphan_cleanup(self):
        run_state.runs["abcdef123456"] = {"owner_token": "owner", "shadow": {"branches": {"B": {"task_id": 42, "cleanup": {"status": "needed"}}}}}
        body = json.dumps({"token": "wrong"}).encode()
        handler = FakeHandler(body, {"Content-Length": str(len(body))})
        with patch.object(routes.core, "build_shadow_adapters") as factory:
            routes.handle(handler, parsed("/prelabel/runs/abcdef123456/shadow-reconcile"))
        self.assertEqual(handler.status, 403)
        factory.assert_not_called()

    def test_shadow_reconcile_cleans_recorded_orphan_for_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_state.runs["abcdef123456"] = run_state.make_runtime_run("shadow", [], owner_token="owner", shadow={"branches": {"B": {"task_id": 42, "cleanup": {"status": "needed"}}}})
            run_state.runs["abcdef123456"]["status"] = "failed"
            body = json.dumps({"token": "owner"}).encode()
            handler = FakeHandler(body, {"Content-Length": str(len(body))})
            cleanup = Mock(return_value={"deleted": True})
            with patch.object(routes.config_manager, "load_config", return_value={"runs_dir": str(Path(tmp) / "runs")}), \
                 patch.object(routes.core, "build_shadow_adapters", return_value={"cleanup": cleanup}):
                routes.handle(handler, parsed("/prelabel/runs/abcdef123456/shadow-reconcile"))
            self.assertEqual(handler.status, 200, self._json_payload(handler))
            self.assertEqual(self._json_payload(handler)["reconciled_task_ids"], [42])
            self.assertEqual(run_state.runs["abcdef123456"]["shadow"]["branches"]["B"]["cleanup"]["status"], "reconciled")
            cleanup.assert_called_once_with(42)

    def test_shadow_reconcile_resolves_crash_window_identity_before_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = run_state.make_runtime_run("shadow", [], owner_token="owner", shadow={"branches": {"A": {"idempotency_key": "batch:A:hash", "cleanup": {"status": "needed"}}}})
            run["status"] = "failed"; run_state.runs["abcdef123456"] = run
            body = json.dumps({"token": "owner"}).encode(); handler = FakeHandler(body, {"Content-Length": str(len(body))})
            cleanup = Mock()
            with patch.object(routes.config_manager, "load_config", return_value={"runs_dir": str(Path(tmp) / "runs")}), \
                 patch.object(routes.core, "build_shadow_adapters", return_value={"cleanup": cleanup, "resolve_task": Mock(return_value={"id": 88})}):
                routes.handle(handler, parsed("/prelabel/runs/abcdef123456/shadow-reconcile"))
            branch = run_state.runs["abcdef123456"]["shadow"]["branches"]["A"]
            self.assertEqual(branch["task_id"], 88)
            self.assertEqual(branch["cleanup"]["status"], "reconciled")
            cleanup.assert_called_once_with(88)

    def test_shadow_cancel_persists_cleanup_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = run_state.make_runtime_run("shadow", [], owner_token="owner", shadow={"branches": {"A": {"task_id": 7}}})
            cleanup = Mock(return_value="deleted")
            run["shadow_cleanup"] = cleanup
            run_state.runs["abcdef123456"] = run
            body = json.dumps({"token": "owner"}).encode()
            handler = FakeHandler(body, {"Content-Length": str(len(body))})
            with patch.object(routes.config_manager, "load_config", return_value={"runs_dir": str(Path(tmp) / "runs")}):
                routes.handle(handler, parsed("/prelabel/runs/abcdef123456/cancel"))
            branch = run_state.runs["abcdef123456"]["shadow"]["branches"]["A"]
            self.assertEqual(branch["cleanup"], {"status": "attempted", "task_id": 7, "result": "deleted"})
            cleanup.assert_called_once_with(7)
    def setUp(self):
        run_state.runs.clear()

    def tearDown(self):
        run_state.runs.clear()

    def _json_payload(self, handler):
        return json.loads(handler.wfile.getvalue().decode("utf-8"))

    def test_runs_redacts_owner_token_and_sets_owned_by_client(self):
        run_state.runs["abcdef123456"] = {
            "status": "running",
            "task_prefix": "demo",
            "input_dirs": ["/root/images"],
            "created_at": "2026-04-29T12:00:00",
            "finished_at": None,
            "logs": [{"type": "log", "msg": "hello"}],
            "result": None,
            "owner_token": "token",
            "done": False,
        }
        handler = FakeHandler(headers={"X-Prelabel-Owner-Token": "token"})

        routes.handle(handler, parsed("/prelabel/runs"))

        payload = self._json_payload(handler)
        self.assertTrue(payload[0]["owned_by_client"])
        self.assertEqual(payload[0]["input_dirs"], ["images"])
        self.assertNotIn("owner_token", json.dumps(payload, ensure_ascii=False))

    def test_run_detail_redacts_owner_token_from_logs(self):
        run_state.runs["abcdef123456"] = {
            "status": "success",
            "task_prefix": "demo",
            "input_dirs": ["/root/images"],
            "created_at": "2026-04-29T12:00:00",
            "finished_at": "2026-04-29T12:01:00",
            "logs": [{"type": "log", "msg": "token is hidden", "owner_token": "secret"}],
            "result": {"owner_token": "secret", "ok": True},
            "owner_token": "secret",
            "done": True,
        }
        handler = FakeHandler(headers={"X-Prelabel-Owner-Token": "secret"})

        routes.handle(handler, parsed("/prelabel/runs/abcdef123456"))

        payload = self._json_payload(handler)
        self.assertTrue(payload["owned_by_client"])
        self.assertNotIn("owner_token", json.dumps(payload, ensure_ascii=False))

    def test_cancel_rejects_wrong_token(self):
        run_state.runs["abcdef123456"] = {
            "status": "running",
            "owner_token": "token",
            "cancel": False,
            "proc": None,
            "done": False,
        }
        body = json.dumps({"token": "wrong"}).encode("utf-8")
        handler = FakeHandler(body=body, headers={"Content-Length": str(len(body))})

        routes.handle(handler, parsed("/prelabel/runs/abcdef123456/cancel"))

        self.assertEqual(handler.status, 403)
        self.assertFalse(run_state.runs["abcdef123456"]["cancel"])

    def test_cancel_accepts_header_token_and_kills_proc(self):
        proc = Mock()
        run_state.runs["abcdef123456"] = {
            "status": "running",
            "owner_token": "token",
            "cancel": False,
            "proc": proc,
            "done": False,
        }
        handler = FakeHandler(headers={"X-Prelabel-Owner-Token": "token"})

        routes.handle(handler, parsed("/prelabel/runs/abcdef123456/cancel"))

        self.assertEqual(handler.status, 200)
        self.assertTrue(run_state.runs["abcdef123456"]["cancel"])
        proc.kill.assert_called_once()

    def test_sse_stream_writes_existing_logs_and_null(self):
        event = threading.Event()
        event.set()
        run_state.runs["abcdef123456"] = {
            "status": "success",
            "logs": [{"type": "log", "msg": "hello", "owner_token": "secret"}],
            "event": event,
            "done": True,
            "owner_token": "",
        }
        handler = FakeHandler()

        routes.handle(handler, parsed("/prelabel/stream/abcdef123456"))

        out = handler.wfile.getvalue().decode("utf-8")
        self.assertIn('"hello"', out)
        self.assertIn("data: null", out)
        self.assertNotIn("owner_token", out)

    def test_sse_stream_rejects_wrong_owner_token(self):
        event = threading.Event()
        event.set()
        run_state.runs["abcdef123456"] = {
            "status": "success",
            "logs": [],
            "event": event,
            "done": True,
            "owner_token": "owner",
        }
        handler = FakeHandler()

        routes.handle(handler, parsed("/prelabel/stream/abcdef123456", "token=wrong"))

        self.assertEqual(handler.status, 403)

    def test_upload_continuation_rejects_token_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            upload_dir = Path(tmp) / "upload_20260429_abcd"
            upload_dir.mkdir()
            run_state.write_upload_meta(upload_dir, "owner-a")
            body = b"--boundary--\r\n"
            headers = {
                "Content-Length": str(len(body)),
                "Content-Type": "multipart/form-data; boundary=boundary",
            }
            handler = FakeHandler(body=body, headers=headers)
            form = {
                "owner_token": SimpleNamespace(value="owner-b"),
                "upload_id": SimpleNamespace(value=upload_dir.name),
                "files": [],
            }

            with patch.object(routes, "_parse_multipart", return_value=form), \
                 patch.object(routes, "_upload_root", return_value=Path(tmp)):
                routes.handle(handler, parsed("/prelabel/upload"))

            self.assertEqual(handler.status, 400)

    def test_upload_rejects_non_multipart_body_as_bad_request(self):
        body = json.dumps({"owner_token": "owner"}).encode("utf-8")
        handler = FakeHandler(
            body=body,
            headers={"Content-Length": str(len(body)), "Content-Type": "application/json"},
        )

        routes.handle(handler, parsed("/prelabel/upload"))

        self.assertEqual(handler.status, 400)

    def test_upload_generated_id_is_valid_for_folder_names_with_dots_and_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_field = SimpleNamespace(
                filename="image.jpg",
                file=io.BytesIO(b"fake-image"),
            )
            form = {
                "owner_token": SimpleNamespace(value="owner"),
                "folder_name": SimpleNamespace(value="my.folder name " + ("x" * 80)),
                "files": [file_field],
            }
            handler = FakeHandler(headers={"Content-Length": "1"})

            with patch.object(routes, "_parse_multipart", return_value=form), \
                 patch.object(routes, "_upload_root", return_value=Path(tmp)):
                routes.handle(handler, parsed("/prelabel/upload"))

            payload = self._json_payload(handler)
            self.assertTrue(payload["ok"])
            self.assertEqual(routes.validate_upload_id(payload["upload_id"]), payload["upload_id"])
            self.assertLessEqual(len(payload["upload_id"]), 64)

    def test_browse_rejects_path_outside_root(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            cfg = {"browse_roots": [root]}
            handler = FakeHandler()

            with patch.object(routes.config_manager, "load_config", return_value=cfg):
                routes.handle(handler, parsed("/prelabel/browse", f"path={other}"))

            self.assertEqual(handler.status, 403)

    def test_browse_skips_symlink_children_outside_root(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            root_path = Path(root)
            (root_path / "inside").mkdir()
            (root_path / "escape").symlink_to(Path(other), target_is_directory=True)
            cfg = {"browse_roots": [root]}
            handler = FakeHandler()

            with patch.object(routes.config_manager, "load_config", return_value=cfg):
                routes.handle(handler, parsed("/prelabel/browse", f"path={root}"))

            payload = self._json_payload(handler)
            self.assertEqual([item["name"] for item in payload["directories"]], ["inside"])

    def test_settings_redacts_credentials_and_clears_cache(self):
        cfg = {
            "cvat_servers": [{
                "id": "local",
                "name": "Local",
                "host": "127.0.0.1",
                "port": 8080,
                "user": "alice",
                "password": "secret",
            }],
            "docker": {"container": "MPformer"},
            "model": {"min_area": 50},
        }
        body = json.dumps({"host": "localhost", "port": 8081, "name": "Ignored"}).encode("utf-8")
        handler = FakeHandler(body=body, headers={"Content-Length": str(len(body))})

        with patch.object(routes.config_manager, "load_config", return_value=cfg) as load_config, \
             patch.object(routes.config_manager, "save_config") as save_config, \
             patch.object(routes.core, "clear_cvat_session_cache") as clear_cache:
            routes.handle(handler, parsed("/prelabel/settings/cvat-server/local"))

        payload = self._json_payload(handler)
        self.assertEqual(payload["server"], {
            "id": "local",
            "name": "Local",
            "host": "localhost",
            "port": 8081,
            "user": "alice",
            "has_password": True,
        })
        self.assertNotIn("secret", json.dumps(payload, ensure_ascii=False))
        load_config.assert_called_once_with(expand_placeholders=False, require_credentials=False)
        save_config.assert_called_once()
        clear_cache.assert_called_once_with("local")

    def test_settings_accepts_credentials_without_returning_password(self):
        cfg = {
            "cvat_servers": [{
                "id": "remote",
                "name": "Remote",
                "host": "127.0.0.1",
                "port": 8080,
            }],
            "docker": {"container": "MPformer"},
            "model": {"min_area": 50},
        }
        body = json.dumps({"user": "alice", "password": "secret"}).encode("utf-8")
        handler = FakeHandler(body=body, headers={"Content-Length": str(len(body))})

        with patch.object(routes.config_manager, "load_config", return_value=cfg), \
             patch.object(routes.config_manager, "save_config") as save_config, \
             patch.object(routes.core, "clear_cvat_session_cache"):
            routes.handle(handler, parsed("/prelabel/settings/cvat-server/remote"))

        payload = self._json_payload(handler)
        self.assertEqual(payload["server"]["user"], "alice")
        self.assertTrue(payload["server"]["has_password"])
        self.assertNotIn("secret", json.dumps(payload, ensure_ascii=False))
        saved_cfg = save_config.call_args.args[0]
        self.assertEqual(saved_cfg["cvat_servers"][0]["user"], "alice")
        self.assertEqual(saved_cfg["cvat_servers"][0]["password"], "secret")

    def test_run_creates_background_thread_with_mocked_core(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as upload_root:
            upload_dir = Path(upload_root) / "upload_20260429_abcd"
            upload_dir.mkdir()
            run_state.write_upload_meta(upload_dir, "owner")
            input_dir = Path(root) / "images"
            input_dir.mkdir()
            cfg = {
                "browse_roots": [root],
                "upload_dir": upload_root,
                "docker": {"container": "MPformer"},
                "model": {"min_area": 50},
                "cvat_servers": [{"id": "local", "host": "localhost", "port": 8080, "user": "u", "password": "p"}],
            }
            body = json.dumps({
                "task_prefix": "demo",
                "input_dirs": [str(input_dir)],
                "upload_id": upload_dir.name,
                "owner_token": "owner",
                "skip_steps": [2, 3, 4],
            }).encode("utf-8")
            handler = FakeHandler(body=body, headers={"Content-Length": str(len(body))})
            started = []

            class ImmediateThread:
                def __init__(self, target, daemon=False):
                    self.target = target
                    self.daemon = daemon

                def start(self):
                    started.append(self.daemon)
                    self.target()

            with patch.object(routes.config_manager, "load_config", return_value=cfg), \
                 patch.object(routes.uuid, "uuid4", return_value=SimpleNamespace(hex="abcdef1234567890")), \
                 patch.object(routes.threading, "Thread", ImmediateThread), \
                 patch.object(routes.core, "run_pipeline", return_value=[{"status": "success"}]) as run_pipeline, \
                 patch.object(routes.run_state, "save_run") as save_run:
                routes.handle(handler, parsed("/prelabel/run"))

            payload = self._json_payload(handler)
            self.assertEqual(payload["run_id"], "abcdef123456")
            self.assertEqual(started, [True])
            self.assertEqual(run_state.runs["abcdef123456"]["status"], "success")
            run_pipeline.assert_called_once()
            params = run_pipeline.call_args.args[3]
            self.assertTrue(callable(params["cancel_fn"]))
            self.assertTrue(callable(params["set_proc_fn"]))
            self.assertTrue(callable(params["clear_proc_fn"]))
            self.assertNotIn("event_fn", params)
            self.assertNotIn("event_callback", params)
            save_run.assert_called()

    def test_run_rejects_upload_without_owner_metadata(self):
        with tempfile.TemporaryDirectory() as upload_root:
            upload_dir = Path(upload_root) / "upload_20260429_abcd"
            upload_dir.mkdir()
            cfg = {"browse_roots": [], "upload_dir": upload_root}
            body = json.dumps({
                "task_prefix": "demo",
                "upload_id": upload_dir.name,
                "owner_token": "owner",
            }).encode("utf-8")
            handler = FakeHandler(body=body, headers={"Content-Length": str(len(body))})

            with patch.object(routes.config_manager, "load_config", return_value=cfg):
                routes.handle(handler, parsed("/prelabel/run"))

            self.assertEqual(handler.status, 403)

    def test_run_only_uses_pipeline_semaphore_in_serial_mode(self):
        run_id = "abcdef123456"
        run_state.runs[run_id] = run_state.make_runtime_run("demo", ["/tmp/images"])
        semaphore = Mock()
        semaphore.acquire.return_value = True
        old_semaphore = routes.pipeline_semaphore
        routes.pipeline_semaphore = semaphore
        try:
            with patch.object(routes.core, "run_pipeline", return_value=[{"status": "success"}]), \
                 patch.object(routes.run_state, "save_run"):
                routes._run_pipeline_thread(run_id, "demo", ["/tmp/images"], {"serial_mode": False}, {}, None)
            semaphore.acquire.assert_not_called()

            run_state.runs[run_id] = run_state.make_runtime_run("demo", ["/tmp/images"])
            with patch.object(routes.core, "run_pipeline", return_value=[{"status": "success"}]), \
                 patch.object(routes.run_state, "save_run"):
                routes._run_pipeline_thread(run_id, "demo", ["/tmp/images"], {"serial_mode": True}, {}, None)
            semaphore.acquire.assert_called_once()
            semaphore.release.assert_called_once()
        finally:
            routes.pipeline_semaphore = old_semaphore

    def test_container_status_checks_gpu_inside_container(self):
        cfg = {"docker": {"container": "MPformer"}}
        handler = FakeHandler()
        inspect = Mock(returncode=0, stdout="running\n", stderr="")
        gpu = Mock(returncode=0, stdout="GPU, 1 MiB, 100 MiB\n", stderr="")

        with patch.object(routes, "_try_load_config", return_value=cfg), \
             patch.object(routes.subprocess, "run", side_effect=[inspect, gpu]) as run:
            routes.handle(handler, parsed("/prelabel/container-status"))

        payload = self._json_payload(handler)
        self.assertTrue(payload["gpu_ok"])
        self.assertIn("docker exec MPformer nvidia-smi", payload["gpu_command"])
        self.assertEqual(run.call_args_list[1].args[0][:4], ["docker", "exec", "MPformer", "nvidia-smi"])

    def test_restart_container_runs_diagnostics_before_restart(self):
        cfg = {"docker": {"container": "MPformer"}}
        handler = FakeHandler()

        with patch.object(routes.config_manager, "load_config", return_value=cfg), \
             patch.object(routes.core, "diagnose_cuda_error") as diagnose, \
             patch.object(routes.core, "restart_docker_container", return_value=True) as restart:
            routes.handle(handler, parsed("/prelabel/restart-container", "mode=manual"))

        diagnose.assert_called_once()
        restart.assert_called_once()

    def test_delete_uses_configured_runs_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id = "abcdef123456"
            run_file = Path(tmp) / f"{run_id}.json"
            run_file.write_text("{}", encoding="utf-8")
            run_state.runs[run_id] = {"status": "success"}
            handler = FakeHandler()
            handler.command = "DELETE"

            with patch.object(routes, "_try_load_config", return_value={"runs_dir": tmp}):
                routes.handle(handler, parsed(f"/prelabel/runs/{run_id}"))

            self.assertEqual(handler.status, 200)
            self.assertFalse(run_file.exists())

    def test_delete_rejects_wrong_owner_token(self):
        run_id = "abcdef123456"
        run_state.runs[run_id] = {"status": "success", "owner_token": "owner"}
        handler = FakeHandler(headers={"X-Prelabel-Owner-Token": "wrong"})
        handler.command = "DELETE"

        routes.handle(handler, parsed(f"/prelabel/runs/{run_id}"))

        self.assertEqual(handler.status, 403)
        self.assertIn(run_id, run_state.runs)

    def test_sse_serializes_unusual_log_values_without_breaking_stream(self):
        event = threading.Event()
        event.set()
        run_state.runs["abcdef123456"] = {
            "status": "success",
            "logs": [{"type": "log", "msg": {"path": Path("/tmp/image.jpg")}}],
            "event": event,
            "done": True,
            "owner_token": "",
        }
        handler = FakeHandler()

        routes.handle(handler, parsed("/prelabel/stream/abcdef123456"))

        out = handler.wfile.getvalue().decode("utf-8")
        self.assertIn("/tmp/image.jpg", out)
        self.assertIn("data: null", out)


if __name__ == "__main__":
    unittest.main()
