"""Pinned Alpha50 candidate contract and preflight gate for A/B prelabel runs."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
import shutil
import sys
import inspect
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable
import xml.etree.ElementTree as ET

import numpy as np


class CandidatePreflightError(RuntimeError):
    """Raised before a candidate CVAT task can be created."""


MAX_ALPHA50_INPUT_PIXELS = 64_000_000
# Bounds apply after shortest-edge TTA scaling, before OpenCV can allocate output.
MAX_ALPHA50_RESIZED_DIMENSION = 16_384
MAX_ALPHA50_RESIZED_PIXELS = 128_000_000


@dataclass(frozen=True)
class Alpha50InferenceResult:
    """Geometry-aligned candidate output for one snapshot."""

    logits: np.ndarray
    mask: np.ndarray
    class_stats: dict[str, dict[str, int]]


class Alpha50Runtime:
    """Lazily load one verified model and reuse it across candidate snapshots.

    The predictor is deliberately injected: orchestration owns framework-specific
    input preparation while this module owns deterministic candidate semantics.
    """

    def __init__(self, model_loader: Callable[[], Any], predictor: Callable[..., Any]):
        self._model_loader = model_loader
        self._predictor = predictor
        self._model: Any | None = None

    def predict(self, image: np.ndarray, *, size: int, flip: bool, interpolation: str = "bilinear", input_normalization: dict[str, Any] | None = None) -> np.ndarray:
        """Predict from a BGR uint8 HxWx3 snapshot; predictor receives normalized RGB float32 HWC."""
        if self._model is None:
            self._model = self._model_loader()
        prepared = _prepare_predictor_input(image, input_normalization)
        if prepared.shape[0] * prepared.shape[1] > MAX_ALPHA50_INPUT_PIXELS:
            raise CandidatePreflightError("snapshot image exceeds Alpha50 input pixel limit")
        height, width = prepared.shape[:2]
        scale = size / min(height, width)
        destination_width, destination_height = round(width * scale), round(height * scale)
        if destination_width <= 0 or destination_height <= 0 or max(destination_width, destination_height) > MAX_ALPHA50_RESIZED_DIMENSION or destination_width * destination_height > MAX_ALPHA50_RESIZED_PIXELS:
            raise CandidatePreflightError("Alpha50 resized geometry limit exceeded")
        resized = _cv2().resize(prepared, (destination_width, destination_height), interpolation=_cv2().INTER_LINEAR)
        transformed = np.ascontiguousarray(resized[:, ::-1] if flip else resized)
        logits = np.asarray(self._predictor(self._model, transformed), dtype=np.float32)
        if logits.ndim != 3 or not np.isfinite(logits).all():
            raise CandidatePreflightError("Alpha50 runtime returned non-finite logits" if logits.ndim == 3 else "Alpha50 runtime must return CxHxW logits")
        aligned = _resize_logits(logits, height, width, interpolation)
        if not np.isfinite(aligned).all():
            raise CandidatePreflightError("Alpha50 runtime returned non-finite logits")
        return aligned[:, :, ::-1] if flip else aligned


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


FRAMEWORK_SOURCE_SUFFIXES = {".py", ".yaml", ".yml", ".json"}
FRAMEWORK_ARTIFACT_DIRS = {".git", "__pycache__", "output", "outputs", "data", "datasets", "logs", "log"}


def framework_tree_digest(framework_root: str | Path) -> str:
    """Hash every relevant framework source file using a stable relative-path manifest."""
    root = Path(framework_root).resolve()
    try:
        listed = subprocess.run(["git", "-C", str(root), "ls-files", "-co", "--exclude-standard"], check=True, capture_output=True, text=True).stdout.splitlines()
        files = [root / relative for relative in listed if Path(relative).suffix.lower() in FRAMEWORK_SOURCE_SUFFIXES and not (set(Path(relative).parts[:-1]) & FRAMEWORK_ARTIFACT_DIRS) and not any(part.startswith("output") for part in Path(relative).parts[:-1])]
        files = [path for path in files if path.is_file()]
    except (OSError, subprocess.CalledProcessError):
        files = []
        for directory, subdirectories, names in os.walk(root):
            subdirectories[:] = [name for name in subdirectories if name not in FRAMEWORK_ARTIFACT_DIRS and not name.startswith("output")]
            files.extend(Path(directory) / name for name in names if Path(name).suffix.lower() in FRAMEWORK_SOURCE_SUFFIXES)
    files.sort(key=lambda path: path.relative_to(root).as_posix())
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _verify_framework_revision(framework_root: Path, revision: str) -> None:
    if isinstance(revision, str) and revision.startswith("tree-sha256:"):
        expected = revision.removeprefix("tree-sha256:")
        matches = len(expected) == 64 and framework_tree_digest(framework_root) == expected
    elif isinstance(revision, str) and revision.startswith("git-head:"):
        expected = revision.removeprefix("git-head:")
        try:
            head = subprocess.run(["git", "-C", str(framework_root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
            dirty = subprocess.run(["git", "-C", str(framework_root), "status", "--porcelain"], check=True, capture_output=True, text=True).stdout.strip()
            matches = head == expected and not dirty
        except (OSError, subprocess.CalledProcessError):
            matches = False
    else:
        raise CandidatePreflightError("framework revision must be a tree-sha256 or git-head pin")
    if not matches:
        raise CandidatePreflightError("framework revision mismatch")


def _immutable(value: Any) -> Any:
    """Detach persisted provenance from the caller's mutable config object."""
    return json.loads(_canonical_json(value).decode("utf-8"))


@dataclass(frozen=True)
class Alpha50Candidate:
    framework_root: str
    framework_revision: str
    weights: tuple[dict[str, str], ...]
    tta: dict[str, Any]
    fusion: dict[str, Any]
    export: dict[str, Any]
    label_mapping: dict[str, dict[str, str]]
    expected_cvat_schema: dict[str, Any]
    output_path: str
    framework_imports: tuple[str, ...]
    min_vram_gb: float
    min_disk_gb: float

    @classmethod
    def from_mapping(cls, candidate: dict[str, Any]) -> "Alpha50Candidate":
        required = {"framework_root", "framework_revision", "weights", "tta", "fusion", "export", "label_mapping", "expected_cvat_schema", "output_path"}
        missing = sorted(required - set(candidate))
        if missing:
            raise CandidatePreflightError(f"candidate config missing: {', '.join(missing)}")
        weights = candidate["weights"]
        if not isinstance(weights, list) or not weights:
            raise CandidatePreflightError("candidate weights must be a non-empty list")
        for weight in weights:
            if not isinstance(weight, dict) or not isinstance(weight.get("path"), str) or not isinstance(weight.get("sha256"), str):
                raise CandidatePreflightError("each candidate weight needs path and sha256")
            if len(weight["sha256"]) != 64:
                raise CandidatePreflightError("candidate weight SHA-256 is invalid")
        tta = candidate["tta"]
        if tta.get("scales") != [768, 832] or tta.get("flip") is not True or not tta.get("interpolation"):
            raise CandidatePreflightError("candidate TTA must pin scales [768, 832], flip, and interpolation")
        export = candidate["export"]
        if not all(key in export for key in ("ignore_policy", "background_policy", "contours")):
            raise CandidatePreflightError("candidate export must pin ignore/background/contours policies")
        mapping = candidate["label_mapping"]
        if not isinstance(mapping, dict) or not mapping:
            raise CandidatePreflightError("candidate label mapping snapshot is required")
        for source_id, item in mapping.items():
            if not isinstance(source_id, str) or not isinstance(item, dict) or not item.get("canonical") or not item.get("cvat"):
                raise CandidatePreflightError("label mapping must be source-ID -> canonical -> CVAT")
            if not source_id.isdigit() or int(source_id) not in range(13):
                raise CandidatePreflightError(f"unknown source ID: {source_id}")
        schema = candidate["expected_cvat_schema"]
        if not isinstance(schema, dict) or not isinstance(schema.get("version"), int) or not isinstance(schema.get("labels"), list):
            raise CandidatePreflightError("versioned expected CVAT schema is required")
        schema_names = {item.get("name") for item in schema["labels"] if isinstance(item, dict)}
        if len(schema_names) != len(schema["labels"]) or not all(isinstance(item, dict) and item.get("name") and item.get("type") and isinstance(item.get("attributes"), list) for item in schema["labels"]):
            raise CandidatePreflightError("expected CVAT label definition requires name/type/attributes")
        for item in mapping.values():
            if item["cvat"] not in schema_names:
                raise CandidatePreflightError(f"mapping references missing CVAT label: {item['cvat']}")
        return cls(
            framework_root=candidate["framework_root"], framework_revision=candidate["framework_revision"],
            weights=tuple(copy.deepcopy(weights)), tta=copy.deepcopy(tta), fusion=copy.deepcopy(candidate["fusion"]),
            export=copy.deepcopy(export), label_mapping=copy.deepcopy(mapping),
            expected_cvat_schema=copy.deepcopy(schema),
            output_path=candidate["output_path"],
            framework_imports=tuple(candidate.get("framework_imports", ["torch", "detectron2"])),
            min_vram_gb=float(candidate.get("min_vram_gb", 0)), min_disk_gb=float(candidate.get("min_disk_gb", 0)),
        )


@dataclass(frozen=True)
class CandidatePreflightResult:
    ok: bool
    errors: tuple[str, ...]
    task_id: int | None
    cleanup_task_id: int | None
    cleanup_outcome: Any | None
    block_import: bool
    manifest: dict[str, Any]
    manifest_digest: str


def build_candidate_provenance(candidate_config: dict[str, Any], input_snapshot_hash: str) -> tuple[dict[str, Any], str]:
    candidate = Alpha50Candidate.from_mapping(candidate_config)
    mapping = _immutable(candidate.label_mapping)
    manifest = _immutable({
        "version": 1,
        "candidate": "alpha50",
        "framework": {"root": candidate.framework_root, "revision_or_image_digest": candidate.framework_revision},
        "output_path": candidate.output_path,
        "weights": list(candidate.weights),
        "tta": candidate.tta,
        "fusion": candidate.fusion,
        "export": candidate.export,
        "label_mapping": mapping,
        "label_mapping_sha256": hashlib.sha256(_canonical_json(mapping)).hexdigest(),
        "expected_cvat_schema": candidate.expected_cvat_schema,
        "input_snapshot_hash": input_snapshot_hash,
    })
    return manifest, hashlib.sha256(_canonical_json(manifest)).hexdigest()


def persist_candidate_provenance(path: str | Path, manifest: dict[str, Any], manifest_digest: str) -> Path:
    """Write a digest-bound provenance record once; existing records cannot be changed."""
    target = Path(path)
    expected = hashlib.sha256(_canonical_json(manifest)).hexdigest()
    if manifest_digest != expected:
        raise CandidatePreflightError("provenance digest does not match manifest")
    payload = _canonical_json({"manifest": _immutable(manifest), "manifest_digest": manifest_digest}) + b"\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError:
        existing = target.read_bytes()
        if existing != payload:
            raise CandidatePreflightError(f"immutable provenance already exists: {target}")
        return target
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        target.chmod(0o444)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def _default_import_checker(framework_root: str, imports: tuple[str, ...]) -> list[str]:
    if framework_root not in sys.path:
        sys.path.insert(0, framework_root)
    for module in imports:
        importlib.import_module(module)
    return list(imports)


def _default_gpu_checker() -> dict[str, Any]:
    torch = importlib.import_module("torch")
    return {"cuda": bool(torch.cuda.is_available()), "vram_gb": (torch.cuda.get_device_properties(0).total_memory / 1024**3 if torch.cuda.is_available() else 0)}


def _expected_labels(candidate: Alpha50Candidate) -> list[dict[str, Any]]:
    return _immutable(candidate.expected_cvat_schema["labels"])


def _normalized_schema(schema: Any, expected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(schema, dict):
        schema = schema.get("labels", [])
    normalized = []
    for item in schema:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        normalized.append({"name": item["name"], "type": item.get("type"), "attributes": item.get("attributes")})
    return sorted(normalized, key=lambda item: item["name"])


def _cleanup_result(cleanup_cvat_task: Callable[[int | None], Any], task_id: int | None) -> Any:
    try:
        return cleanup_cvat_task(task_id)
    except Exception as exc:
        return {"status": "cleanup_failed", "error": str(exc)}


def _disk_target(output_path: Path) -> Path:
    target = output_path
    while not target.exists() and target != target.parent:
        target = target.parent
    return target


def _create_task(create_cvat_task: Callable[..., Any], labels: list[dict[str, Any]], identity: str, request_key: str) -> Any:
    """Pass idempotency data to integrations that explicitly support it."""
    try:
        signature = inspect.signature(create_cvat_task)
        supports_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values())
        supports_named = {"task_identity", "request_key"}.issubset(signature.parameters)
    except (TypeError, ValueError):
        supports_kwargs = supports_named = False
    if not (supports_kwargs or supports_named):
        raise CandidatePreflightError("CVAT create adapter must support idempotency task_identity/request_key")
    return create_cvat_task(labels, task_identity=identity, request_key=request_key)


def _resolved_task_id(resolved: Any) -> int | None:
    candidate = resolved.get("id") if isinstance(resolved, dict) else getattr(resolved, "id", None)
    return candidate if isinstance(candidate, int) and not isinstance(candidate, bool) and candidate > 0 else None


def preflight_candidate(
    candidate_config: dict[str, Any],
    *,
    input_snapshot_hash: str,
    import_checker: Callable[[str], list[str]] | None = None,
    gpu_checker: Callable[[], dict[str, Any]] | None = None,
    disk_checker: Callable[[Path], float] | None = None,
    create_cvat_task: Callable[[list[dict[str, str]]], Any] | None = None,
    get_cvat_schema: Callable[[Any], Any] | None = None,
    cleanup_cvat_task: Callable[[int | None], Any] | None = None,
    resolve_cvat_task: Callable[[str, str], Any] | None = None,
    provenance_path: str | Path | None = None,
    branch_record: dict[str, Any] | None = None,
) -> CandidatePreflightResult:
    """Validate all pre-create conditions, then create and validate the candidate task schema.

    A failed pre-create check raises, so no candidate task exists.  A schema mismatch
    occurs only after creation and returns cleanup_task_id plus block_import=True.
    """
    candidate = Alpha50Candidate.from_mapping(candidate_config)
    if provenance_path is None or not isinstance(branch_record, dict):
        raise CandidatePreflightError("provenance persistence context is required")
    if not callable(cleanup_cvat_task):
        raise CandidatePreflightError("tracked cleanup callback is required")
    for weight in candidate.weights:
        path = Path(weight["path"])
        if not path.is_file():
            raise CandidatePreflightError(f"candidate weight missing: {path}")
        if _sha256_file(path) != weight["sha256"]:
            raise CandidatePreflightError(f"candidate weight hash mismatch: {path}")
    root = Path(candidate.framework_root)
    if not root.is_dir():
        raise CandidatePreflightError(f"candidate framework root missing: {root}")
    _verify_framework_revision(root, candidate.framework_revision)
    checked_imports = (import_checker or (lambda value: _default_import_checker(value, candidate.framework_imports)))(str(root))
    if not set(candidate.framework_imports).issubset(set(checked_imports)):
        raise CandidatePreflightError("candidate framework imports incomplete")
    gpu = (gpu_checker or _default_gpu_checker)()
    if not gpu.get("cuda") or float(gpu.get("vram_gb", 0)) < candidate.min_vram_gb:
        raise CandidatePreflightError("CUDA/VRAM capacity is insufficient")
    output_path = Path(candidate.output_path)
    available_disk = (disk_checker or (lambda path: shutil.disk_usage(_disk_target(path)).free / 1024**3))(output_path)
    if float(available_disk) < candidate.min_disk_gb:
        raise CandidatePreflightError("disk capacity is insufficient")
    if create_cvat_task is None or get_cvat_schema is None:
        raise CandidatePreflightError("CVAT create/schema callbacks are required")

    manifest, digest = build_candidate_provenance(candidate_config, input_snapshot_hash)
    persisted = persist_candidate_provenance(provenance_path, manifest, digest)
    branch_record["candidate_provenance_digest"] = digest
    branch_record["candidate_provenance_path"] = str(persisted)
    expected_labels = _expected_labels(candidate)
    task_identity = f"alpha50-{digest[:24]}"
    request_key = hashlib.sha256(f"{task_identity}:{digest}".encode("ascii")).hexdigest()
    branch_record["candidate_task_identity"] = task_identity
    branch_record["candidate_request_key"] = request_key
    try:
        task = _create_task(create_cvat_task, expected_labels, task_identity, request_key)
    except CandidatePreflightError:
        raise
    except Exception as exc:
        branch_record["candidate_preflight_status"] = "create_ambiguous"
        try:
            task = resolve_cvat_task(task_identity, request_key) if callable(resolve_cvat_task) else None
        except Exception as resolve_exc:
            branch_record["candidate_preflight_status"] = "cleanup_resolution_needed"
            branch_record["candidate_cleanup_lookup_key"] = request_key
            branch_record["candidate_cleanup_resolution_error"] = str(resolve_exc)
            return CandidatePreflightResult(False, (f"CVAT task create failed: {exc}",), None, None, {"status": "resolution_failed", "error": str(resolve_exc)}, True, manifest, digest)
        task_id = _resolved_task_id(task)
        if task_id is None:
            branch_record["candidate_preflight_status"] = "cleanup_resolution_needed"
            branch_record["candidate_cleanup_lookup_key"] = request_key
            return CandidatePreflightResult(False, (f"CVAT task create failed: {exc}",), None, None, {"status": "resolution_needed"}, True, manifest, digest)
        branch_record["candidate_cleanup_needed_task_id"] = task_id
        branch_record["candidate_preflight_status"] = "create_failed_resolved"
        cleanup_outcome = _cleanup_result(cleanup_cvat_task, task_id)
        branch_record["candidate_cleanup_outcome"] = cleanup_outcome
        return CandidatePreflightResult(False, (f"CVAT task create failed: {exc}",), task_id, task_id, cleanup_outcome, True, manifest, digest)
    task_id = _resolved_task_id(task)
    if not isinstance(task_id, int) or isinstance(task_id, bool) or task_id <= 0:
        branch_record["candidate_preflight_status"] = "task_id_invalid"
        try:
            task = resolve_cvat_task(task_identity, request_key) if callable(resolve_cvat_task) else None
        except Exception as exc:
            branch_record["candidate_preflight_status"] = "cleanup_resolution_needed"
            branch_record["candidate_cleanup_lookup_key"] = request_key
            branch_record["candidate_cleanup_resolution_error"] = str(exc)
            return CandidatePreflightResult(False, ("CVAT task id is invalid",), None, None, {"status": "resolution_failed", "error": str(exc)}, True, manifest, digest)
        task_id = _resolved_task_id(task)
        if task_id is None:
            branch_record["candidate_preflight_status"] = "cleanup_resolution_needed"
            branch_record["candidate_cleanup_lookup_key"] = request_key
            return CandidatePreflightResult(False, ("CVAT task id is invalid",), None, None, {"status": "resolution_needed"}, True, manifest, digest)
    branch_record["candidate_cleanup_needed_task_id"] = task_id
    branch_record["candidate_preflight_status"] = "schema_pending"
    try:
        actual_schema = _normalized_schema(get_cvat_schema(task), expected_labels)
    except Exception as exc:
        branch_record["candidate_preflight_status"] = "schema_failed"
        cleanup_outcome = _cleanup_result(cleanup_cvat_task, task_id)
        branch_record["candidate_cleanup_outcome"] = cleanup_outcome
        return CandidatePreflightResult(False, (f"CVAT schema read failed: {exc}",), task_id, task_id, cleanup_outcome, True, manifest, digest)
    expected_schema = sorted(expected_labels, key=lambda item: item["name"])
    if actual_schema != expected_schema:
        branch_record["candidate_preflight_status"] = "schema_failed"
        cleanup_outcome = _cleanup_result(cleanup_cvat_task, task_id)
        branch_record["candidate_cleanup_outcome"] = cleanup_outcome
        return CandidatePreflightResult(False, ("CVAT schema mismatch after task creation",), task_id, task_id, cleanup_outcome, True, manifest, digest)
    branch_record.pop("candidate_cleanup_needed_task_id", None)
    branch_record["candidate_preflight_status"] = "schema_verified"
    return CandidatePreflightResult(True, (), task_id, None, None, False, manifest, digest)


def _cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - deployment dependency diagnostic
        raise CandidatePreflightError("OpenCV is required for Alpha50 candidate export") from exc
    return cv2


def _candidate_value(candidate_config: dict[str, Any], key: str) -> dict[str, Any]:
    value = candidate_config.get(key)
    if not isinstance(value, dict):
        raise CandidatePreflightError(f"candidate {key} configuration is required")
    return value


def _prepare_predictor_input(image: np.ndarray, input_normalization: dict[str, Any] | None) -> np.ndarray:
    """Implement the pinned snapshot contract before any Alpha50 predictor call."""
    if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[0] <= 0 or image.shape[1] <= 0 or image.shape[2] != 3:
        raise CandidatePreflightError("snapshot image must be a nonempty HxWx3 BGR image")
    if image.dtype != np.uint8:
        raise CandidatePreflightError("snapshot image must use uint8 pixels")
    if not isinstance(input_normalization, dict) or input_normalization.get("color_order") != "RGB" or input_normalization.get("pixel_range") != "0_1":
        raise CandidatePreflightError("candidate input normalization must pin RGB and 0_1")
    mean, std = np.asarray(input_normalization.get("mean"), dtype=np.float32), np.asarray(input_normalization.get("std"), dtype=np.float32)
    if mean.shape != (3,) or std.shape != (3,) or not np.isfinite(mean).all() or not np.isfinite(std).all() or np.any(std <= 0):
        raise CandidatePreflightError("candidate input normalization mean/std must be three finite positive values")
    rgb = image[:, :, ::-1].astype(np.float32) / 255.0
    return (rgb - mean) / std


def _resize_logits(logits: np.ndarray, height: int, width: int, interpolation: str) -> np.ndarray:
    if logits.ndim != 3:
        raise CandidatePreflightError("Alpha50 runtime must return CxHxW logits")
    cv2 = _cv2()
    interpolation_code = {"nearest": cv2.INTER_NEAREST, "bilinear": cv2.INTER_LINEAR, "bicubic": cv2.INTER_CUBIC}.get(interpolation)
    if interpolation_code is None:
        raise CandidatePreflightError(f"unsupported logits interpolation: {interpolation}")
    resized = np.empty((logits.shape[0], height, width), dtype=np.float32)
    for index, channel in enumerate(logits):
        resized[index] = cv2.resize(channel, (width, height), interpolation=interpolation_code)
    return resized


def _softmax(logits: np.ndarray) -> np.ndarray:
    stable = logits - np.max(logits, axis=0, keepdims=True)
    exponent = np.exp(stable)
    return exponent / np.sum(exponent, axis=0, keepdims=True)


def infer_alpha50_snapshot(image: np.ndarray, runtime: Alpha50Runtime | Callable[..., Any], candidate_config: dict[str, Any]) -> Alpha50InferenceResult:
    """Run the pinned 768/832 plus flipped-logit TTA and return a raw class mask."""
    if not isinstance(image, np.ndarray) or image.ndim < 2:
        raise CandidatePreflightError("snapshot image must have height and width")
    tta = _candidate_value(candidate_config, "tta")
    if tta.get("scales") != [768, 832] or tta.get("flip") is not True:
        raise CandidatePreflightError("candidate inference requires pinned scales [768, 832] and flip")
    if _candidate_value(candidate_config, "fusion").get("method") != "mean_logits":
        raise CandidatePreflightError("candidate fusion method must be mean_logits")
    if not isinstance(runtime, Alpha50Runtime):
        raise CandidatePreflightError("candidate inference requires an Alpha50Runtime")
    export = _candidate_value(candidate_config, "export")
    input_normalization = _candidate_value(export, "input_normalization")
    fused: np.ndarray | None = None
    for size in (768, 832):
        for flip in (False, True):
            aligned = runtime.predict(image, size=size, flip=flip, interpolation=str(tta.get("interpolation", "bilinear")), input_normalization=input_normalization)
            if not np.isfinite(aligned).all():
                raise CandidatePreflightError("Alpha50 TTA returned non-finite logits")
            if fused is None:
                fused = aligned.astype(np.float32, copy=True)
            elif aligned.shape != fused.shape:
                raise CandidatePreflightError("Alpha50 TTA logits have inconsistent class geometry")
            else:
                fused += aligned
            del aligned
    if fused is None:  # pragma: no cover - fixed TTA loop always has four passes
        raise CandidatePreflightError("Alpha50 TTA produced no logits")
    fused /= 4.0
    if not np.isfinite(fused).all():
        raise CandidatePreflightError("Alpha50 TTA fusion produced non-finite logits")
    mapping = _candidate_value(candidate_config, "label_mapping")
    unknown_classes = sorted(set(range(fused.shape[0])) - {int(source_id) for source_id in mapping})
    if unknown_classes:
        raise CandidatePreflightError(f"unknown source class IDs: {unknown_classes}")
    probabilities = _softmax(fused)
    mask = np.argmax(probabilities, axis=0).astype(np.uint8)
    if export.get("background_policy") != "exclude":
        raise CandidatePreflightError("candidate background policy must be exclude")
    if export.get("confidence_policy") != "per-class-softmax-threshold":
        raise CandidatePreflightError("candidate confidence policy must be per-class-softmax-threshold")
    threshold = float(export.get("confidence_threshold", 0.50))
    confidence = np.max(probabilities, axis=0)
    mask[confidence < threshold] = 0
    stats: dict[str, dict[str, int]] = {}
    for source_id, item in sorted(mapping.items(), key=lambda pair: int(pair[0])):
        canonical = item.get("canonical") if isinstance(item, dict) else None
        if isinstance(canonical, str):
            stats[canonical] = {"pixels": int(np.count_nonzero(mask == int(source_id)))}
    return Alpha50InferenceResult(fused, mask, stats)


def _exclusive_write(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def save_alpha50_artifacts(result: Alpha50InferenceResult, image_name: str, output_directory: str | Path) -> dict[str, Any]:
    """Persist raw, unmodified mask bytes and per-class pixel statistics."""
    if not isinstance(image_name, str) or not image_name:
        raise CandidatePreflightError("image identity must be a validated relative path")
    identity = PurePosixPath(image_name)
    if identity.is_absolute() or ".." in identity.parts:
        raise CandidatePreflightError("image identity must be a validated relative path")
    target = Path(output_directory)
    target.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(image_name.encode("utf-8")).hexdigest()
    stem = identity.stem or "image"
    mask_path = target / f"{stem}-{digest}.png"
    stats_path = target / f"{stem}-{digest}.stats.json"
    identity_path = target / f"{stem}-{digest}.identity.json"
    identity_manifest = _canonical_json({"image_name": image_name, "mask": mask_path.name, "stats": stats_path.name}) + b"\n"
    try:
        _exclusive_write(identity_path, identity_manifest)
    except FileExistsError:
        try:
            existing_identity = json.loads(identity_path.read_text(encoding="utf-8")).get("image_name")
        except (OSError, json.JSONDecodeError):
            existing_identity = None
        if existing_identity != image_name:
            raise CandidatePreflightError("artifact identity conflict")
        raise CandidatePreflightError("artifact identity already exists")
    try:
        encoded_ok, encoded_mask = _cv2().imencode(".png", result.mask)
        if not encoded_ok:
            raise CandidatePreflightError(f"failed to encode raw mask: {mask_path}")
        _exclusive_write(mask_path, encoded_mask.tobytes())
        _exclusive_write(stats_path, _canonical_json(result.class_stats) + b"\n")
    except BaseException:
        mask_path.unlink(missing_ok=True)
        stats_path.unlink(missing_ok=True)
        identity_path.unlink(missing_ok=True)
        raise
    return {"mask_path": str(mask_path), "stats_path": str(stats_path), "class_stats": result.class_stats}


def _polygon_points(contour: np.ndarray) -> str:
    return ";".join(f"{float(point[0][0]):.1f},{float(point[0][1]):.1f}" for point in contour)


def build_cvat_images_xml(images: Iterable[dict[str, Any]], candidate_config: dict[str, Any]) -> bytes:
    """Convert raw masks to deterministic CVAT Images 1.1 polygons."""
    export = _candidate_value(candidate_config, "export")
    contours_config = _candidate_value(export, "contours")
    mapping = _candidate_value(candidate_config, "label_mapping")
    min_area, epsilon = int(contours_config.get("min_area", 0)), float(contours_config.get("approx_epsilon", 0.0))
    root = ET.Element("annotations")
    ET.SubElement(root, "version").text = "1.1"
    cv2 = _cv2()
    image_items = list(images)
    seen: set[str] = set()
    for item in image_items:
        name, width, height, mask = item.get("name"), item.get("width"), item.get("height"), item.get("mask")
        if not isinstance(name, str) or name in seen or not isinstance(width, int) or not isinstance(height, int):
            raise CandidatePreflightError("image name/dimensions must be unique and explicit")
        seen.add(name)
        if not isinstance(mask, np.ndarray) or mask.shape != (height, width):
            raise CandidatePreflightError("raw mask geometry does not match image dimensions")
    for index, item in enumerate(sorted(image_items, key=lambda item: item["name"])):
        name, width, height, mask = item["name"], item["width"], item["height"], item["mask"]
        image_element = ET.SubElement(root, "image", {"id": str(index), "name": name, "width": str(width), "height": str(height)})
        for class_id, label in sorted(((int(key), value.get("cvat")) for key, value in mapping.items() if key != "0" and isinstance(value, dict)), key=lambda pair: pair[0]):
            if not isinstance(label, str):
                continue
            component_count, components, component_stats, _ = cv2.connectedComponentsWithStats((mask == class_id).astype(np.uint8), connectivity=8)
            contours: list[tuple[int, int, int, np.ndarray]] = []
            for component_id in range(1, component_count):
                area = int(component_stats[component_id, cv2.CC_STAT_AREA])
                if area < min_area:
                    continue
                component_mask = (components == component_id).astype(np.uint8)
                found, _ = cv2.findContours(component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for contour in found:
                    simplified = cv2.approxPolyDP(contour, epsilon, True) if epsilon > 0 else contour
                    if len(simplified) >= 3:
                        contours.append((int(simplified[:, 0, 1].min()), int(simplified[:, 0, 0].min()), area, simplified))
            for _, _, _, contour in sorted(contours, key=lambda value: (value[0], value[1], value[2], _polygon_points(value[3]))):
                ET.SubElement(image_element, "polygon", {"label": label, "source": "auto", "occluded": "0", "points": _polygon_points(contour), "z_order": "0"})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def validate_cvat_images_xml(xml: bytes | str, images: Iterable[dict[str, Any]], expected_schema: dict[str, Any]) -> None:
    """Reject imports whose image identity, labels, or polygon geometry drifted."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise CandidatePreflightError("invalid CVAT XML") from exc
    if root.findtext("version") != "1.1":
        raise CandidatePreflightError("CVAT XML must be Images 1.1")
    image_manifest = tuple(images)
    expected_images = {item.get("name"): (item.get("width"), item.get("height")) for item in image_manifest}
    if len(expected_images) != len(image_manifest):
        raise CandidatePreflightError("expected images must have unique names")
    labels = {item.get("name") for item in expected_schema.get("labels", []) if isinstance(item, dict) and item.get("type") == "polygon"}
    actual_images = root.findall("image")
    if len(actual_images) != len(expected_images):
        raise CandidatePreflightError("image uniqueness mismatch")
    seen: set[str] = set()
    for image in actual_images:
        name = image.get("name")
        if name not in expected_images or name in seen:
            raise CandidatePreflightError("image name mismatch")
        seen.add(name)
        try:
            width, height = int(image.get("width", "")), int(image.get("height", ""))
        except ValueError as exc:
            raise CandidatePreflightError("invalid image dimensions") from exc
        if (width, height) != expected_images[name]:
            raise CandidatePreflightError("image dimensions mismatch")
        for polygon in image.findall("polygon"):
            if polygon.get("label") not in labels:
                raise CandidatePreflightError("label schema mismatch")
            try:
                points = [tuple(map(float, pair.split(","))) for pair in polygon.get("points", "").split(";")]
            except ValueError as exc:
                raise CandidatePreflightError("invalid polygon points") from exc
            if len(points) < 3 or any(len(point) != 2 or not (0 <= point[0] < width and 0 <= point[1] < height) for point in points):
                raise CandidatePreflightError("polygon bounds mismatch")
