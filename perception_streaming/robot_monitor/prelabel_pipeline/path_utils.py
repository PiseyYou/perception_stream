from __future__ import annotations

import re
from pathlib import Path

_UPLOAD_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{16,64}$")
_RUN_ID_RE = re.compile(r"^[a-f0-9]{12}$")


class InvalidPathError(ValueError):
    pass


def resolve_under(path: str | Path, roots: list[str | Path]) -> Path:
    resolved = Path(path).expanduser().resolve()
    resolved_roots = [Path(root).expanduser().resolve() for root in roots]
    if not any(resolved == root or root in resolved.parents for root in resolved_roots):
        raise InvalidPathError(f"path outside allowed roots: {resolved}")
    return resolved


def validate_upload_id(value: str) -> str:
    if not value or not _UPLOAD_ID_RE.fullmatch(value):
        raise ValueError("invalid upload_id")
    return value


def validate_run_id(value: str) -> str:
    if not value or not _RUN_ID_RE.fullmatch(value):
        raise ValueError("invalid run_id")
    return value


def safe_filename(name: str) -> str:
    raw = Path((name or "").replace("\\", "/")).name
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")
    if not stem:
        raise ValueError("empty filename")
    return stem


def unique_path(directory: Path, filename: str) -> Path:
    safe_name = safe_filename(filename)
    candidate = directory / safe_name
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    index = 2
    while True:
        next_candidate = directory / f"{stem}_{index}{suffix}"
        if not next_candidate.exists():
            return next_candidate
        index += 1
