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
    if supports_kwargs or supports_named:
        return create_cvat_task(labels, task_identity=identity, request_key=request_key)
    return create_cvat_task(labels)


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
