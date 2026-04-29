#!/usr/bin/env python3
"""
Configuration Loader
从 data/conf/ 目录加载配置文件
"""

import json
import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
CONF_DIR = PROJECT_ROOT / "data" / "conf"


def load_ssh_config() -> dict:
    """加载 SSH 配置"""
    config_file = CONF_DIR / "ssh_config.json"

    if not config_file.exists():
        # 返回默认配置
        config = {
            "ssh_key_path": "bestmow_rsa_202604",
            "ssh_host": "120.25.121.3",
            "ssh_user": "root",
            "ssh_port": 22,
            "default_ports": {
                "realtime_monitor": 10015,
                "log_fetch": 10016,
                "stereo_analysis": 10115
            }
        }
    else:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

    config["ssh_key_path"] = _resolve_ssh_key(os.getenv("SSH_KEY", config.get("ssh_key_path", "")))

    config["ssh_host"] = os.getenv("ROBOT_HOST", config.get("ssh_host", "120.25.121.3"))
    config["ssh_user"] = os.getenv("ROBOT_USER", config.get("ssh_user", "root"))
    config["ssh_port"] = int(os.getenv("ROBOT_PORT", config.get("ssh_port", 22)))

    return config


def _resolve_ssh_key(path: str) -> str:
    if not path:
        return ""
    key_path = os.path.expanduser(path)
    if not os.path.isabs(key_path):
        return str((CONF_DIR / key_path).resolve())
    return str(Path(key_path).resolve())


def get_ssh_key_path() -> str:
    """获取 SSH 密钥的绝对路径"""
    config = load_ssh_config()
    env_key = os.getenv("SSH_KEY")
    if env_key:
        return _resolve_ssh_key(env_key)
    return _resolve_ssh_key(config.get("ssh_key_path", ""))


def get_ssh_host() -> str:
    """获取 SSH 主机地址"""
    config = load_ssh_config()
    return config.get("ssh_host", "120.25.121.3")


def get_ssh_port() -> int:
    """获取 SSH 端口"""
    config = load_ssh_config()
    return int(config.get("ssh_port", 22))


def get_ssh_user() -> str:
    """获取 SSH 用户名"""
    config = load_ssh_config()
    return config.get("ssh_user", "root")


def get_default_port(service: str) -> int:
    """获取指定服务的默认端口

    Args:
        service: 服务名称，可选值：
            - realtime_monitor: 实时监控
            - log_fetch: 日志拉取
            - stereo_analysis: 双目分析

    Returns:
        端口号
    """
    config = load_ssh_config()
    ports = config.get("default_ports", {})

    default_ports = {
        "realtime_monitor": 10015,
        "log_fetch": 10016,
        "stereo_analysis": 10115
    }

    return ports.get(service, default_ports.get(service, 10015))


if __name__ == "__main__":
    # 测试配置加载
    print("SSH Key Path:", get_ssh_key_path())
    print("SSH Host:", get_ssh_host())
    print("SSH User:", get_ssh_user())
    print("Default Ports:")
    print("  - Realtime Monitor:", get_default_port("realtime_monitor"))
    print("  - Log Fetch:", get_default_port("log_fetch"))
    print("  - Stereo Analysis:", get_default_port("stereo_analysis"))
