"""Pinned Alpha50 candidate contract and preflight gate for A/B prelabel runs."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class CandidatePreflightError(RuntimeError):
    """Raised before a candidate CVAT task can be created."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    framework_imports: tuple[str, ...]
    min_vram_gb: float
    min_disk_gb: float

    @classmethod
    def from_mapping(cls, candidate: dict[str, Any]) -> "Alpha50Candidate":
        required = {"framework_root", "framework_revision", "weights", "tta", "fusion", "export", "label_mapping", "expected_cvat_schema"}
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


def preflight_candidate(
    candidate_config: dict[str, Any],
    *,
    input_snapshot_hash: str,
    import_checker: Callable[[str], list[str]] | None = None,
    gpu_checker: Callable[[], dict[str, Any]] | None = None,
    disk_checker: Callable[[], float] | None = None,
    create_cvat_task: Callable[[list[dict[str, str]]], Any] | None = None,
    get_cvat_schema: Callable[[Any], Any] | None = None,
    cleanup_cvat_task: Callable[[int | None], Any] | None = None,
    provenance_path: str | Path | None = None,
    branch_record: dict[str, Any] | None = None,
) -> CandidatePreflightResult:
    """Validate all pre-create conditions, then create and validate the candidate task schema.

    A failed pre-create check raises, so no candidate task exists.  A schema mismatch
    occurs only after creation and returns cleanup_task_id plus block_import=True.
    """
    candidate = Alpha50Candidate.from_mapping(candidate_config)
    for weight in candidate.weights:
        path = Path(weight["path"])
        if not path.is_file():
            raise CandidatePreflightError(f"candidate weight missing: {path}")
        if _sha256_file(path) != weight["sha256"]:
            raise CandidatePreflightError(f"candidate weight hash mismatch: {path}")
    root = Path(candidate.framework_root)
    if not root.is_dir():
        raise CandidatePreflightError(f"candidate framework root missing: {root}")
    checked_imports = (import_checker or (lambda value: _default_import_checker(value, candidate.framework_imports)))(str(root))
    if not set(candidate.framework_imports).issubset(set(checked_imports)):
        raise CandidatePreflightError("candidate framework imports incomplete")
    gpu = (gpu_checker or _default_gpu_checker)()
    if not gpu.get("cuda") or float(gpu.get("vram_gb", 0)) < candidate.min_vram_gb:
        raise CandidatePreflightError("CUDA/VRAM capacity is insufficient")
    available_disk = (disk_checker or (lambda: shutil.disk_usage(root).free / 1024**3))()
    if float(available_disk) < candidate.min_disk_gb:
        raise CandidatePreflightError("disk capacity is insufficient")
    if create_cvat_task is None or get_cvat_schema is None:
        raise CandidatePreflightError("CVAT create/schema callbacks are required")

    manifest, digest = build_candidate_provenance(candidate_config, input_snapshot_hash)
    if provenance_path is not None:
        persisted = persist_candidate_provenance(provenance_path, manifest, digest)
        if branch_record is not None:
            branch_record["candidate_provenance_digest"] = digest
            branch_record["candidate_provenance_path"] = str(persisted)
    expected_labels = _expected_labels(candidate)
    task = create_cvat_task(expected_labels)
    task_id = task.get("id") if isinstance(task, dict) else getattr(task, "id", None)
    actual_schema = _normalized_schema(get_cvat_schema(task), expected_labels)
    expected_schema = sorted(expected_labels, key=lambda item: item["name"])
    if actual_schema != expected_schema:
        cleanup_outcome = cleanup_cvat_task(task_id) if cleanup_cvat_task is not None else {"status": "cleanup_callback_missing"}
        return CandidatePreflightResult(False, ("CVAT schema mismatch after task creation",), task_id, task_id, cleanup_outcome, True, manifest, digest)
    return CandidatePreflightResult(True, (), task_id, None, None, False, manifest, digest)
