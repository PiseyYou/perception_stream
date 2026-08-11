import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
ROBOT_MONITOR_DIR = TEST_DIR.parent
if str(ROBOT_MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(ROBOT_MONITOR_DIR))

from prelabel_pipeline import run_state


class PrelabelRunStateTest(unittest.TestCase):
    def test_restored_shadow_orphan_is_marked_cleanup_needed(self):
        restored = run_state._restore_history_record({"status": "running", "task_prefix": "x", "input_dirs": [], "created_at": "now", "shadow": {"branches": {"B": {"task_id": 9}}}})
        self.assertEqual(restored["shadow"]["branches"]["B"]["cleanup"]["status"], "needed")
        self.assertEqual(restored["shadow"]["branches"]["B"]["cleanup"]["reason"], "service_recovery")

    def test_shadow_attempt_history_survives_disk_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = run_state.make_runtime_run("x", [], shadow={"branches": {"A": {"attempt": 2, "attempt_history": [{"status": "failed"}]}}})
            run["status"] = "failed"; run["done"] = True
            run_state.runs["abcdef123456"] = run
            run_state.save_run("abcdef123456", tmp)
            run_state.runs.clear(); run_state.init_runs_from_history(tmp)
            self.assertEqual(run_state.runs["abcdef123456"]["shadow"]["branches"]["A"]["attempt"], 2)
    def test_shadow_idempotency_key_uses_batch_branch_and_snapshot(self):
        self.assertEqual(
            run_state.shadow_idempotency_key("batch", "A", "snapshot"),
            "batch:A:snapshot",
        )
    def setUp(self):
        run_state.runs.clear()

    def tearDown(self):
        run_state.runs.clear()

    def _make_run(self):
        return {
            "status": "running",
            "task_prefix": "demo",
            "input_dirs": ["/media/sdc2/lhx/MPformer/foo"],
            "created_at": "2026-04-29T12:00:00",
            "finished_at": None,
            "logs": [{"type": "log", "msg": "hello"}],
            "result": None,
            "owner_token": "token-1",
        }

    def test_serialize_run_redacts_paths_and_computes_ownership(self):
        run = self._make_run()
        data = run_state.serialize_run(
            "abcdef123456",
            run,
            expose_paths=False,
            include_logs=True,
            owner_token="token-1",
        )
        self.assertEqual(data["input_dirs"], ["foo"])
        self.assertTrue(data["owned_by_client"])
        self.assertNotIn("owner_token", data)
        self.assertEqual(data["logs"], [{"type": "log", "msg": "hello"}])

    def test_serialize_run_preserves_paths_when_exposed(self):
        run = self._make_run()
        data = run_state.serialize_run("abcdef123456", run, expose_paths=True)
        self.assertEqual(data["input_dirs"], ["/media/sdc2/lhx/MPformer/foo"])
        self.assertFalse(data["owned_by_client"])
        self.assertNotIn("logs", data)
        self.assertNotIn("owner_token", data)

    def test_run_json_path_rejects_invalid_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                run_state.run_json_path(Path(tmp), "../bad")

    def test_upload_metadata_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            upload_dir = Path(tmp)
            run_state.write_upload_meta(upload_dir, "owner-token")
            self.assertEqual(run_state.read_upload_owner(upload_dir), "owner-token")

    def test_read_upload_owner_returns_empty_for_missing_or_malformed_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            upload_dir = Path(tmp)
            self.assertEqual(run_state.read_upload_owner(upload_dir), "")
            (upload_dir / ".upload_meta.json").write_text("{bad json", encoding="utf-8")
            self.assertEqual(run_state.read_upload_owner(upload_dir), "")

    def test_save_run_persists_owner_token_for_restart_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_state.runs["abcdef123456"] = self._make_run()

            run_state.save_run("abcdef123456", Path(tmp))

            saved = json.loads((Path(tmp) / "abcdef123456.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["owner_token"], "token-1")

            api_data = run_state.serialize_run("abcdef123456", saved, expose_paths=False)
            self.assertNotIn("owner_token", api_data)

    def test_load_history_skips_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp)
            (runs_dir / "badbadbadbad.json").write_text("{bad json", encoding="utf-8")
            (runs_dir / "abcdef123456.json").write_text(
                json.dumps({
                    "run_id": "abcdef123456",
                    "status": "success",
                    "task_prefix": "demo",
                    "input_dirs": ["/tmp/foo"],
                    "created_at": "2026-04-29T12:00:00",
                    "finished_at": "2026-04-29T12:01:00",
                    "result": {"ok": True},
                    "owner_token": "token-1",
                }),
                encoding="utf-8",
            )

            history = run_state.load_history(runs_dir)

            self.assertEqual([record["run_id"] for record in history], ["abcdef123456"])

    def test_init_runs_from_history_recreates_completed_runtime_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp)
            (runs_dir / "abcdef123456.json").write_text(
                json.dumps({
                    "run_id": "abcdef123456",
                    "status": "success",
                    "task_prefix": "demo",
                    "input_dirs": ["/tmp/foo"],
                    "created_at": "2026-04-29T12:00:00",
                    "finished_at": "2026-04-29T12:01:00",
                    "logs": [],
                    "result": {"ok": True},
                    "owner_token": "token-1",
                }),
                encoding="utf-8",
            )

            run_state.init_runs_from_history(runs_dir)

            run = run_state.runs["abcdef123456"]
            self.assertTrue(run["done"])
            self.assertIsInstance(run["event"], threading.Event)
            self.assertTrue(run["event"].is_set())
            self.assertEqual(run["owner_token"], "token-1")

    def test_init_runs_from_history_normalizes_stale_running_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp)
            (runs_dir / "abcdef123456.json").write_text(
                json.dumps({
                    "run_id": "abcdef123456",
                    "status": "running",
                    "task_prefix": "demo",
                    "input_dirs": ["/tmp/foo"],
                    "created_at": "2026-04-29T12:00:00",
                    "finished_at": None,
                    "logs": [],
                    "result": None,
                    "owner_token": "token-1",
                }),
                encoding="utf-8",
            )

            run_state.init_runs_from_history(runs_dir)

            run = run_state.runs["abcdef123456"]
            self.assertEqual(run["status"], "failed")
            self.assertTrue(run["done"])
            self.assertTrue(run["event"].is_set())
            self.assertIsNotNone(run["finished_at"])
            self.assertIn("服务重启，运行中任务已中断", run["result"]["error"])
            self.assertTrue(any("服务重启，运行中任务已中断" in log["msg"] for log in run["logs"]))

    def test_init_runs_from_history_handles_stale_running_record_with_malformed_logs(self):
        for bad_logs in ({"msg": "not a list"}, "not a list"):
            with self.subTest(logs=bad_logs):
                run_state.runs.clear()
                with tempfile.TemporaryDirectory() as tmp:
                    runs_dir = Path(tmp)
                    (runs_dir / "abcdef123456.json").write_text(
                        json.dumps({
                            "run_id": "abcdef123456",
                            "status": "running",
                            "task_prefix": "demo",
                            "input_dirs": ["/tmp/foo"],
                            "created_at": "2026-04-29T12:00:00",
                            "finished_at": None,
                            "logs": bad_logs,
                            "result": "unexpected result shape",
                            "owner_token": "token-1",
                        }),
                        encoding="utf-8",
                    )

                    run_state.init_runs_from_history(runs_dir)

                    run = run_state.runs["abcdef123456"]
                    self.assertEqual(run["status"], "failed")
                    self.assertTrue(run["done"])
                    self.assertTrue(run["event"].is_set())
                    self.assertIsInstance(run["logs"], list)
                    self.assertIn("服务重启，运行中任务已中断", run["result"]["error"])
                    self.assertTrue(any("服务重启，运行中任务已中断" in log["msg"] for log in run["logs"]))
