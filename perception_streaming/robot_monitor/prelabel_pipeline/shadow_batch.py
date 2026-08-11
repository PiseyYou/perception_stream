"""Immutable image snapshots and isolated inputs for A/B shadow prelabel runs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image, UnidentifiedImageError


SUPPORTED_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
MANIFEST_NAME = "manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _image_metadata(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ValueError(f"corrupt image: {path}") from exc
    return width, height


def _canonical_hash(files: list[dict[str, Any]]) -> str:
    payload = json.dumps(files, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _atomic_json_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def freeze_batch(source: str | Path, snapshot_root: str | Path) -> dict[str, str]:
    """Copy an image batch into an immutable, content-addressed snapshot."""
    source_path = Path(source).resolve()
    if not source_path.is_dir():
        raise ValueError(f"source is not a directory: {source}")

    files: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for image_path in sorted((path for path in source_path.rglob("*") if path.is_file()), key=lambda p: p.relative_to(source_path).as_posix()):
        relative = image_path.relative_to(source_path).as_posix()
        if image_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"unsupported image: {relative}")
        width, height = _image_metadata(image_path)
        content_hash = _sha256(image_path)
        if content_hash in seen_hashes:
            raise ValueError(f"duplicate image: {relative}")
        seen_hashes.add(content_hash)
        files.append({"path": relative, "sha256": content_hash, "width": width, "height": height})

    if not files:
        raise ValueError("source contains no images")
    snapshot_hash = _canonical_hash(files)
    batch_id = snapshot_hash[:16]
    snapshot_path = Path(snapshot_root).resolve() / batch_id
    manifest_path = snapshot_path / MANIFEST_NAME
    manifest = {"version": 1, "batch_id": batch_id, "snapshot_hash": snapshot_hash, "files": files}

    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing != manifest:
            raise ValueError(f"snapshot collision: {snapshot_path}")
    else:
        images_path = snapshot_path / "images"
        for item in files:
            destination = images_path / item["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path / item["path"], destination)
            destination.chmod(0o444)
        _atomic_json_write(manifest_path, manifest)
        manifest_path.chmod(0o444)
        for directory in sorted((path for path in images_path.rglob("*") if path.is_dir()), reverse=True):
            directory.chmod(0o555)
        images_path.chmod(0o555)
        snapshot_path.chmod(0o555)

    return {"batch_id": batch_id, "snapshot_hash": snapshot_hash, "snapshot_path": str(snapshot_path)}


def _load_snapshot(snapshot: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    try:
        snapshot_path = Path(snapshot["snapshot_path"]).resolve()
        manifest = json.loads((snapshot_path / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (KeyError, OSError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError("invalid snapshot") from exc
    if snapshot.get("batch_id") != manifest.get("batch_id") or snapshot.get("snapshot_hash") != manifest.get("snapshot_hash"):
        raise ValueError("snapshot identity does not match manifest")
    if manifest.get("snapshot_hash") != _canonical_hash(manifest.get("files", [])):
        raise ValueError("snapshot manifest hash mismatch")
    return snapshot_path, manifest


def materialize_branch_input(snapshot: dict[str, Any], branch: str, work_root: str | Path) -> Path:
    """Create a branch-private writable copy of a verified frozen snapshot."""
    if not isinstance(branch, str) or not branch or branch in {".", ".."} or "/" in branch or "\\" in branch:
        raise ValueError("invalid branch")
    snapshot_path, manifest = _load_snapshot(snapshot)
    destination_root = Path(work_root).resolve() / manifest["batch_id"] / branch
    try:
        destination_root.relative_to(snapshot_path)
    except ValueError:
        pass
    else:
        raise ValueError("work root cannot be inside snapshot")
    destination_root.mkdir(parents=True, exist_ok=True)
    if destination_root.is_symlink():
        raise ValueError("symlinked branch output is not allowed")

    for item in manifest["files"]:
        relative = PurePosixPath(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("invalid manifest path")
        source_file = snapshot_path / "images" / Path(*relative.parts)
        if not source_file.is_file() or _sha256(source_file) != item.get("sha256"):
            raise ValueError(f"snapshot image integrity check failed: {item['path']}")
        destination_file = destination_root / Path(*relative.parts)
        parent = destination_root
        for part in relative.parts[:-1]:
            parent = parent / part
            if parent.is_symlink():
                raise ValueError("symlinked branch output is not allowed")
            parent.mkdir(exist_ok=True)
        if destination_file.is_symlink():
            raise ValueError("symlinked branch output is not allowed")
        shutil.copy2(source_file, destination_file)
        destination_file.chmod(0o644)
    return destination_root
