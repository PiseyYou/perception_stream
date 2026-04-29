from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent
STREAMING_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MPFORMER_ROOT = STREAMING_DIR.parent.parent / "MPformer"
CONFIG_PATH = BASE_DIR / "prelabel_config.yaml"
_REQUIRED_KEYS = {"cvat_servers", "docker", "model"}


def _expand_placeholders(value):
    if isinstance(value, dict):
        return {key: _expand_placeholders(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_placeholders(item) for item in value]
    if isinstance(value, str):
        replacements = {
            "STREAMING_DIR": str(STREAMING_DIR),
            "PROJECT_ROOT": str(STREAMING_DIR.parent),
            "MPFORMER_ROOT": os.environ.get("MPFORMER_ROOT", str(DEFAULT_MPFORMER_ROOT)),
        }
        expanded = value
        for key, replacement in replacements.items():
            expanded = expanded.replace(f"${{{key}}}", replacement).replace(f"${key}", replacement)
        return os.path.expandvars(expanded)
    return value


def load_config(
    config_path: str | Path | None = None,
    *,
    expand_placeholders: bool = True,
    require_credentials: bool = False,
) -> dict:
    path = Path(config_path) if config_path else CONFIG_PATH
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ValueError("prelabel config must be a mapping")
    if expand_placeholders:
        cfg = _expand_placeholders(cfg)

    for server in cfg.get("cvat_servers", []):
        sid = server["id"].upper().replace("-", "_")
        user = os.environ.get(f"CVAT_{sid}_USER", server.get("user", ""))
        password = os.environ.get(f"CVAT_{sid}_PASSWORD", server.get("password", ""))
        if require_credentials and (not user or not password):
            raise ValueError(f"请设置环境变量 CVAT_{sid}_USER 和 CVAT_{sid}_PASSWORD")
        if user:
            server["user"] = user
        if password:
            server["password"] = password
    return cfg


def save_config(config: dict, config_path: str | Path | None = None) -> None:
    path = Path(config_path) if config_path else CONFIG_PATH
    if not isinstance(config, dict):
        raise ValueError("prelabel config must be a mapping")
    missing = _REQUIRED_KEYS - set(config)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"prelabel config missing required keys: {missing_text}")
    safe = copy.deepcopy(config)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(safe, f, allow_unicode=True, sort_keys=False)


def safe_cvat_servers(config: dict) -> list[dict]:
    return [
        {
            "id": s["id"],
            "name": s["name"],
            "host": s["host"],
            "port": s["port"],
            "user": s.get("user", ""),
            "has_password": bool(s.get("password")),
        }
        for s in config.get("cvat_servers", [])
    ]
