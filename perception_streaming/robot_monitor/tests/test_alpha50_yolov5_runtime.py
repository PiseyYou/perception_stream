import sys
import tempfile
import unittest
import hashlib
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import torch
import yaml


TEST_DIR = Path(__file__).resolve().parent
ROBOT_MONITOR_DIR = TEST_DIR.parent
if str(ROBOT_MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(ROBOT_MONITOR_DIR))

from prelabel_pipeline import core


class Alpha50YoloV5RuntimeTest(unittest.TestCase):
    def setUp(self):
        from prelabel_pipeline import alpha50_yolov5_runtime as runtime

        runtime.clear_model_cache()
        self.runtime = runtime

    def test_loader_uses_framework_backend_once_and_predictor_converts_normalized_rgb_hwc_to_nchw_tensor(self):
        model = Mock()
        model.return_value = (None, torch.arange(26, dtype=torch.float32).reshape(1, 13, 1, 2))
        model.eval.return_value = model
        model.to.return_value = model
        attempt_load = Mock(return_value=model)
        select_device = Mock(return_value=torch.device("cpu"))
        config = {"framework_root": "/framework", "checkpoint": "/weights/alpha50.pt", "checkpoint_sha256": hashlib.sha256(b"").hexdigest(), "device": "auto"}
        image = np.array([[[0.25, -0.5, 1.75]]], dtype=np.float32)

        with patch.object(self.runtime, "_load_backend", return_value=(attempt_load, select_device)), \
             patch.object(self.runtime.Path, "read_bytes", return_value=b""):
            loaded = self.runtime.load_alpha50_model(config)
            logits = self.runtime.predict_alpha50_logits(loaded, image)
            self.assertIs(loaded, self.runtime.load_alpha50_model(config))

        select_device.assert_called_once_with("", batch_size=1)
        attempt_load.assert_called_once_with("/weights/alpha50.pt", map_location=torch.device("cpu"))
        tensor = model.call_args.args[0]
        self.assertEqual(tuple(tensor.shape), (1, 3, 1, 1))
        self.assertEqual(tensor.dtype, torch.float32)
        np.testing.assert_allclose(tensor.cpu().numpy(), image.transpose(2, 0, 1)[None])
        self.assertEqual(tuple(logits.shape), (13, 1, 2))
        self.assertTrue(np.isfinite(logits).all())

    def test_predictor_rejects_nonfinite_or_nonsegmentation_outputs(self):
        class Model:
            def __call__(self, _tensor):
                return (None, torch.tensor([[[[float("nan")]]]]))

        loaded = self.runtime.LoadedAlpha50Model(Model(), torch.device("cpu"), False)
        with self.assertRaisesRegex(ValueError, "non-finite"):
            self.runtime.predict_alpha50_logits(loaded, np.zeros((1, 1, 3), dtype=np.float32))

    def test_config_declares_importable_runtime_without_python_callable_injection(self):
        config_path = ROBOT_MONITOR_DIR / "prelabel_pipeline" / "prelabel_config.yaml"
        candidate = yaml.safe_load(config_path.read_text(encoding="utf-8"))["alpha50_candidate"]
        runtime_config = candidate["runtime"]

        self.assertEqual(runtime_config["module"], "prelabel_pipeline.alpha50_yolov5_runtime")
        self.assertEqual(runtime_config["loader"], "load_alpha50_model")
        self.assertEqual(runtime_config["predictor"], "predict_alpha50_logits")
        self.assertEqual(runtime_config["framework_root"], candidate["framework_root"])
        self.assertEqual(runtime_config["checkpoint"], candidate["weights"][0]["path"])

        adapters = core.build_shadow_adapters({
            "alpha50_candidate": candidate,
            "cvat_servers": [{"id": "test", "host": "localhost", "port": 8080, "user": "u", "password": "p"}],
        })
        runtime = adapters["resolve_alpha50_runtime"]()
        self.assertIsInstance(runtime, __import__("prelabel_pipeline.alpha50_batch", fromlist=["Alpha50Runtime"]).Alpha50Runtime)


if __name__ == "__main__":
    unittest.main()
