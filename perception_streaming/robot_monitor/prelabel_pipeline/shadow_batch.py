"""Immutable image snapshots and isolated inputs for A/B shadow prelabel runs."""

from __future__ import annotations

import errno
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
UPLOAD_METADATA_NAME = ".upload_meta.json"


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


def _remove_staging(path: Path) -> None:
    """Remove a staging tree even after its files were made read-only."""
    if not path.exists():
        return
    for directory, _subdirs, files in os.walk(path, topdown=False):
        for name in files:
            (Path(directory) / name).chmod(0o600)
        Path(directory).chmod(0o700)
    shutil.rmtree(path, ignore_errors=True)


def freeze_batch(source: str | Path, snapshot_root: str | Path) -> dict[str, str]:
    """Copy images without transformation into an immutable, content-addressed snapshot.

    ``normalized_dimensions`` deliberately equals ``original_dimensions``: Task 1
    stores the original image geometry, and later preprocessing must make any
    geometry change explicit in a new snapshot contract.
    """
    source_path = Path(source).resolve()
    if not source_path.is_dir():
        raise ValueError(f"source is not a directory: {source}")

    files: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for image_path in sorted((path for path in source_path.rglob("*") if path.is_file()), key=lambda p: p.relative_to(source_path).as_posix()):
        relative = image_path.relative_to(source_path).as_posix()
        # Upload ownership metadata lives beside user images.  It is internal
        # control-plane state, not input data, and must never enter the frozen
        # image manifest.  All other unsupported files remain fail-closed.
        if relative == UPLOAD_METADATA_NAME:
            continue
        if image_path.is_symlink():
            raise ValueError(f"source image symlink is not allowed: {relative}")
        try:
            image_path.resolve().relative_to(source_path)
        except ValueError as exc:
            raise ValueError(f"source image resolves outside source root: {relative}") from exc
        if image_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"unsupported image: {relative}")
        width, height = _image_metadata(image_path)
        content_hash = _sha256(image_path)
        if content_hash in seen_hashes:
            raise ValueError(f"duplicate image: {relative}")
        seen_hashes.add(content_hash)
        dimensions = {"width": width, "height": height}
        files.append(
            {
                "path": relative,
                "sha256": content_hash,
                "original_dimensions": dimensions,
                "normalized_dimensions": dimensions.copy(),
            }
        )

    if not files:
        raise ValueError("source contains no images")
    snapshot_hash = _canonical_hash(files)
    batch_id = snapshot_hash[:16]
    snapshots_path = Path(snapshot_root).resolve()
    snapshot_path = snapshots_path / batch_id
    manifest_path = snapshot_path / MANIFEST_NAME
    manifest = {"version": 1, "batch_id": batch_id, "snapshot_hash": snapshot_hash, "files": files}

    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing != manifest:
            raise ValueError(f"snapshot collision: {snapshot_path}")
    else:
        snapshots_path.mkdir(parents=True, exist_ok=True)
        staging_path = Path(tempfile.mkdtemp(prefix=f".{batch_id}.", dir=snapshots_path))
        try:
            images_path = staging_path / "images"
            for item in files:
                destination = images_path / item["path"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path / item["path"], destination)
                staged_dimensions = dict(zip(("width", "height"), _image_metadata(destination)))
                if (
                    _sha256(destination) != item["sha256"]
                    or staged_dimensions != item["original_dimensions"]
                    or staged_dimensions != item["normalized_dimensions"]
                ):
                    raise ValueError(f"snapshot staging integrity check failed: {item['path']}")
                destination.chmod(0o444)
            _atomic_json_write(staging_path / MANIFEST_NAME, manifest)
            (staging_path / MANIFEST_NAME).chmod(0o444)
            for directory in sorted((path for path in images_path.rglob("*") if path.is_dir()), reverse=True):
                directory.chmod(0o555)
            images_path.chmod(0o555)
            staging_path.chmod(0o555)
            try:
                staging_path.rename(snapshot_path)
            except OSError as exc:
                if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                    raise
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
                if existing != manifest:
                    raise ValueError(f"snapshot collision: {snapshot_path}")
        finally:
            _remove_staging(staging_path)

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
    work_root_path = Path(work_root).absolute()
    destination_root = work_root_path / manifest["batch_id"] / branch
    try:
        destination_root.relative_to(snapshot_path)
    except ValueError:
        pass
    else:
        raise ValueError("work root cannot be inside snapshot")
    for directory in (work_root_path, work_root_path / manifest["batch_id"], destination_root):
        if directory.is_symlink():
            raise ValueError("symlinked branch output is not allowed")
        directory.mkdir(exist_ok=True)

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
