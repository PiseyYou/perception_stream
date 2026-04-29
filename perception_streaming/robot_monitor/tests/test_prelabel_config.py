import sys
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

TEST_DIR = Path(__file__).resolve().parent
ROBOT_MONITOR_DIR = TEST_DIR.parent
if str(ROBOT_MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(ROBOT_MONITOR_DIR))

from prelabel_pipeline.config_manager import load_config, safe_cvat_servers, save_config


class PrelabelConfigTest(unittest.TestCase):
    def _write_config(self, path: Path):
        path.write_text(yaml.safe_dump({
            "cvat_servers": [{"id": "remote", "name": "Remote", "host": "127.0.0.1", "port": 8080}],
            "docker": {"container": "MPformer"},
            "model": {
                "demo_dir": "/media/sdc2/lhx/MPformer/MP-Former/demo",
                "config": "/cfg.yaml",
                "weights": "/weights.pth",
                "min_area": 50,
            },
            "labels_csv": "/labels.csv",
            "output_base": "/tmp/output",
            "upload_dir": "/tmp/uploads",
            "runs_dir": "/tmp/runs",
            "browse_roots": ["/tmp"],
            "segment_size": 1000,
        }, allow_unicode=True), encoding="utf-8")

    def test_load_config_injects_env_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "prelabel_config.yaml"
            self._write_config(config_path)
            with patch.dict(os.environ, {
                "CVAT_REMOTE_USER": "alice",
                "CVAT_REMOTE_PASSWORD": "secret",
            }, clear=False):
                cfg = load_config(config_path)
            self.assertEqual(cfg["cvat_servers"][0]["user"], "alice")
            self.assertEqual(cfg["cvat_servers"][0]["password"], "secret")

    def test_load_config_expands_project_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "prelabel_config.yaml"
            config_path.write_text(yaml.safe_dump({
                "cvat_servers": [{"id": "remote", "name": "Remote", "host": "127.0.0.1", "port": 8080}],
                "docker": {"container": "MPformer"},
                "model": {
                    "demo_dir": "${MPFORMER_ROOT}/MP-Former/demo",
                    "config": "${MPFORMER_ROOT}/MP-Former/output/config.yaml",
                    "weights": "${MPFORMER_ROOT}/MP-Former/output/model.pth",
                },
                "labels_csv": "${MPFORMER_ROOT}/MP-Former/demo/lhx/labels.csv",
                "output_base": "${MPFORMER_ROOT}/MP-Former/demo/output",
                "upload_dir": "${STREAMING_DIR}/data/prelabel_uploads",
                "runs_dir": "${PROJECT_ROOT}/perception_streaming/data/prelabel_runs",
                "browse_roots": ["${MPFORMER_ROOT}"],
                "segment_size": 1000,
            }, allow_unicode=True), encoding="utf-8")

            with patch.dict(os.environ, {
                "CVAT_REMOTE_USER": "alice",
                "CVAT_REMOTE_PASSWORD": "secret",
                "MPFORMER_ROOT": "/opt/mpformer",
            }, clear=False):
                cfg = load_config(config_path)

            self.assertEqual(cfg["model"]["demo_dir"], "/opt/mpformer/MP-Former/demo")
            self.assertEqual(cfg["browse_roots"], ["/opt/mpformer"])
            self.assertTrue(cfg["upload_dir"].endswith("/perception_streaming/data/prelabel_uploads"))

    def test_load_config_can_preserve_placeholders_for_settings_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "prelabel_config.yaml"
            config_path.write_text(yaml.safe_dump({
                "cvat_servers": [{"id": "remote", "name": "Remote", "host": "127.0.0.1", "port": 8080}],
                "docker": {"container": "MPformer"},
                "model": {"demo_dir": "${MPFORMER_ROOT}/MP-Former/demo"},
            }, allow_unicode=True), encoding="utf-8")

            cfg = load_config(config_path, expand_placeholders=False, require_credentials=False)

            self.assertEqual(cfg["model"]["demo_dir"], "${MPFORMER_ROOT}/MP-Former/demo")
            self.assertNotIn("user", cfg["cvat_servers"][0])

    def test_load_config_requires_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "prelabel_config.yaml"
            self._write_config(config_path)
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ValueError):
                    load_config(config_path)

    def test_load_config_requires_mapping_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "prelabel_config.yaml"
            config_path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(config_path)

    def test_safe_servers_redacts_credentials(self):
        servers = [{"id": "remote", "name": "Remote", "host": "h", "port": 1, "user": "u", "password": "p"}]
        self.assertEqual(safe_cvat_servers({"cvat_servers": servers}), [
            {"id": "remote", "name": "Remote", "host": "h", "port": 1}
        ])

    def test_save_config_redacts_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "prelabel_config.yaml"
            cfg = {
                "cvat_servers": [{
                    "id": "remote",
                    "name": "Remote",
                    "host": "127.0.0.1",
                    "port": 8080,
                    "user": "alice",
                    "password": "secret",
                }],
                "docker": {"container": "MPformer"},
                "model": {
                    "demo_dir": "/media/sdc2/lhx/MPformer/MP-Former/demo",
                    "config": "/cfg.yaml",
                    "weights": "/weights.pth",
                    "min_area": 50,
                },
                "labels_csv": "/labels.csv",
                "output_base": "/tmp/output",
                "upload_dir": "/tmp/uploads",
                "runs_dir": "/tmp/runs",
                "browse_roots": ["/tmp"],
                "segment_size": 1000,
            }

            save_config(cfg, config_path)

            saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["cvat_servers"], [{
                "id": "remote",
                "name": "Remote",
                "host": "127.0.0.1",
                "port": 8080,
            }])
            self.assertNotIn("user", saved["cvat_servers"][0])
            self.assertNotIn("password", saved["cvat_servers"][0])

    def test_save_config_rejects_partial_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "prelabel_config.yaml"
            with self.assertRaises(ValueError):
                save_config({"cvat_servers": []}, config_path)
            self.assertFalse(config_path.exists())
