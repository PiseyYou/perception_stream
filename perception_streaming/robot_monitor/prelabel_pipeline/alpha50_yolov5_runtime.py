"""Real Alpha50 YOLOv5-segmentation runtime adapter.

The Alpha50 batch contract owns image resizing and normalization.  This module
only turns that normalized RGB HWC array into the framework's NCHW tensor and
extracts the segmentation logits from the validated YOLOv5 model API.
"""

from __future__ import annotations

import sys
import threading
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np


@dataclass(frozen=True)
class LoadedAlpha50Model:
    """Cached framework model and the device/dtype required to invoke it."""

    model: Any
    device: Any
    use_half: bool


_model_cache: dict[tuple[str, str, str], LoadedAlpha50Model] = {}
_model_cache_lock = threading.Lock()


def clear_model_cache() -> None:
    """Clear cached models; intended for controlled tests and process teardown."""
    with _model_cache_lock:
        _model_cache.clear()


def _load_backend(framework_root: str | Path) -> tuple[Any, Any]:
    root = str(Path(framework_root).resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    from models.experimental import attempt_load
    from utils.torch_utils import select_device

    return attempt_load, select_device


def _runtime_paths(runtime_config: Mapping[str, Any]) -> tuple[str, str, str]:
    framework_root = runtime_config.get("framework_root")
    checkpoint = runtime_config.get("checkpoint")
    device_request = runtime_config.get("device", "auto")
    if not isinstance(framework_root, str) or not framework_root:
        raise ValueError("Alpha50 runtime requires a framework_root")
    if not isinstance(checkpoint, str) or not checkpoint:
        raise ValueError("Alpha50 runtime requires a checkpoint")
    if not isinstance(device_request, str) or not device_request:
        raise ValueError("Alpha50 runtime device must be a non-empty string")
    return str(Path(framework_root).resolve()), str(Path(checkpoint)), device_request


def load_alpha50_model(runtime_config: Mapping[str, Any]) -> LoadedAlpha50Model:
    """Load the pinned checkpoint once, selecting CPU safely when CUDA is absent."""
    framework_root, checkpoint, device_request = _runtime_paths(runtime_config)
    expected_sha = runtime_config.get("checkpoint_sha256")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ValueError("Alpha50 runtime requires checkpoint_sha256")
    digest = hashlib.sha256(Path(checkpoint).read_bytes()).hexdigest()
    if digest != expected_sha:
        raise ValueError("Alpha50 checkpoint hash mismatch")
    key = (framework_root, checkpoint, device_request)
    with _model_cache_lock:
        cached = _model_cache.get(key)
        if cached is not None:
            return cached
        attempt_load, select_device = _load_backend(framework_root)
        # The evaluator's fixed "0" is unsafe for online use.  YOLOv5's empty
        # request picks CUDA when available and otherwise returns CPU.
        device = select_device("" if device_request == "auto" else device_request, batch_size=1)
        model = attempt_load(checkpoint, map_location=device)
        model = model.to(device).eval()
        use_half = getattr(device, "type", "cpu") != "cpu"
        if use_half:
            model.half()
        else:
            model.float()
        loaded = LoadedAlpha50Model(model=model, device=device, use_half=use_half)
        _model_cache[key] = loaded
        return loaded


def predict_alpha50_logits(loaded: LoadedAlpha50Model, normalized_rgb_hwc: np.ndarray) -> np.ndarray:
    """Run one normalized RGB HWC float32 image and return finite CxHxW logits."""
    if not isinstance(loaded, LoadedAlpha50Model):
        raise TypeError("Alpha50 predictor requires a LoadedAlpha50Model")
    image = np.asarray(normalized_rgb_hwc)
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.float32:
        raise ValueError("Alpha50 predictor requires normalized RGB HWC float32 input")
    if not np.isfinite(image).all():
        raise ValueError("Alpha50 predictor input must be finite")
    import torch

    tensor = torch.from_numpy(np.ascontiguousarray(image.transpose(2, 0, 1))).unsqueeze(0)
    tensor = tensor.to(loaded.device)
    tensor = tensor.half() if loaded.use_half else tensor.float()
    with torch.inference_mode():
        output = loaded.model(tensor)
    if not isinstance(output, (tuple, list)) or len(output) < 2:
        raise ValueError("Alpha50 YOLOv5 model did not return segmentation logits at output[1]")
    logits = output[1]
    if not isinstance(logits, torch.Tensor) or logits.ndim != 4 or logits.shape[0] != 1:
        raise ValueError("Alpha50 YOLOv5 segmentation logits must be 1xCxHxW")
    result = logits[0].detach().float().cpu().numpy()
    if not np.isfinite(result).all():
        raise ValueError("Alpha50 YOLOv5 segmentation logits are non-finite")
    return result
