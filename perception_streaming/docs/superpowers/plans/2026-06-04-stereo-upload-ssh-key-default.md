# 双目分析上传图片默认 SSH 私钥调整 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将双目分析上传图片链路的默认 SSH 私钥从 `bestmow_rsa_202605` 调整为 `bestmow_rsa_202606`。

**Architecture:** 保持现有 `data/conf/ssh_config.json` 配置入口不变，只同步 `robot_monitor/config_loader.py` 在配置文件缺失时的默认值。后端 `offline_server.py` 继续通过 `get_ssh_key_path()` 获取绝对路径，不改上传图片函数和前端调用链路。

**Tech Stack:** Python 3 标准库、现有 Vite/Vue 开发服务、现有 SSH/rsync 上传图片链路。

---

## File Structure

- Modify: `robot_monitor/config_loader.py`
  - 责任：读取 `data/conf/ssh_config.json`，并在配置缺失时提供 SSH 默认配置。
  - 修改点：`load_ssh_config()` 的默认 `ssh_key_path`。
- Validate: `data/conf/ssh_config.json`
  - 责任：当前运行环境的 SSH 配置文件。
  - 验证点：确认 `ssh_key_path` 已是 `bestmow_rsa_202606`。
- No code changes: `robot_monitor/offline_server.py`
  - 责任：双目上传图片接口和 `ssh`/`rsync` 执行。
  - 不修改原因：它已统一使用 `get_ssh_key_path()` 解析后的 `SSH_KEY`。

## Task 1: Update default SSH key path

**Files:**
- Modify: `robot_monitor/config_loader.py:20-31`
- Validate: `data/conf/ssh_config.json:1-10`

- [ ] **Step 1: Verify current configured SSH key**

Run:

```bash
rg -n '"ssh_key_path": "bestmow_rsa_202606"' data/conf/ssh_config.json
```

Expected:

```text
data/conf/ssh_config.json:2:  "ssh_key_path": "bestmow_rsa_202606",
```

- [ ] **Step 2: Verify the fallback default still points at old key before the edit**

Run:

```bash
rg -n '"ssh_key_path": "bestmow_rsa_202605"' robot_monitor/config_loader.py
```

Expected before implementation:

```text
robot_monitor/config_loader.py:23:            "ssh_key_path": "bestmow_rsa_202605",
```

- [ ] **Step 3: Change fallback default key**

In `robot_monitor/config_loader.py`, replace this default:

```python
            "ssh_key_path": "bestmow_rsa_202605",
```

with:

```python
            "ssh_key_path": "bestmow_rsa_202606",
```

Do not change `get_ssh_key_path()` or any `offline_server.py` upload logic.

- [ ] **Step 4: Verify static references after the edit**

Run:

```bash
rg -n '"ssh_key_path": "bestmow_rsa_202606"' data/conf/ssh_config.json robot_monitor/config_loader.py
```

Expected:

```text
data/conf/ssh_config.json:2:  "ssh_key_path": "bestmow_rsa_202606",
robot_monitor/config_loader.py:23:            "ssh_key_path": "bestmow_rsa_202606",
```

- [ ] **Step 5: Verify resolved SSH key path**

Run:

```bash
python3 robot_monitor/config_loader.py
```

Expected output includes:

```text
SSH Key Path: /media/sda1/perception_process/perception_streaming/data/conf/bestmow_rsa_202606
SSH Host: 120.25.121.3
SSH User: root
```

- [ ] **Step 6: Report runtime restart requirement**

Because `robot_monitor/offline_server.py` assigns `SSH_KEY = get_ssh_key_path()` at module import time, any currently running backend/Vite dev server must be restarted before this change affects live upload attempts.

- [ ] **Step 7: Commit policy**

Do not commit automatically. The session policy requires an explicit user request before `git commit`.

## Self-Review

- Spec coverage: Task 1 covers the only code requirement: update the fallback SSH key default to `bestmow_rsa_202606`; validation confirms both configured and resolved paths.
- Placeholder scan: No TBD/TODO/placeholders remain.
- Type/signature consistency: No new functions or signatures are introduced; existing `load_ssh_config()` and `get_ssh_key_path()` behavior remains unchanged except the default string.
