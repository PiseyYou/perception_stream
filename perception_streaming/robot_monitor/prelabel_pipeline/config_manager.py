from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "prelabel_config.yaml"
_REQUIRED_KEYS = {"cvat_servers", "docker", "model"}


def load_config(config_path: str | Path | None = None) -> dict:
    path = Path(config_path) if config_path else CONFIG_PATH
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ValueError("prelabel config must be a mapping")

    for server in cfg.get("cvat_servers", []):
        sid = server["id"].upper().replace("-", "_")
        user = os.environ.get(f"CVAT_{sid}_USER", server.get("user", ""))
        password = os.environ.get(f"CVAT_{sid}_PASSWORD", server.get("password", ""))
        if not user or not password:
            raise ValueError(f"请设置环境变量 CVAT_{sid}_USER 和 CVAT_{sid}_PASSWORD")
        server["user"] = user
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
    for server in safe.get("cvat_servers", []):
        server.pop("user", None)
        server.pop("password", None)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(safe, f, allow_unicode=True, sort_keys=False)


def safe_cvat_servers(config: dict) -> list[dict]:
    return [
        {"id": s["id"], "name": s["name"], "host": s["host"], "port": s["port"]}
        for s in config.get("cvat_servers", [])
    ]
