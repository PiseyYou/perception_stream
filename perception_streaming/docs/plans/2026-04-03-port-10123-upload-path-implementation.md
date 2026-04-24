# Port 10123 Special Upload Path Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure that when port 10123 is used, images are uploaded to `/home/youfeng/debug/custom/0123/` and directories are created automatically.

**Architecture:** Modify the upload functions in `robot_monitor/offline_server.py` to add a conditional base path check for port 10123.

**Tech Stack:** Python 3, subprocess, os, shutil.

---

### Task 1: Update `upload_images_from_robot` in `offline_server.py`

**Files:**
- Modify: `robot_monitor/offline_server.py:1016-1037`

**Step 1: Implement path override logic**

```python
def upload_images_from_robot(port: int, date_str: str) -> dict:
    if not date_str:
        return {"ok": False, "error": "未提供日期"}

    port_suffix = str(port)[-4:]
    if port == 10123:
        local_dir = os.path.join("/home/youfeng/debug/custom", port_suffix, date_str)
    else:
        local_dir = os.path.join(LOCAL_IMAGE_BASE, date_str)

    os.makedirs(local_dir, exist_ok=True)
    # ... existing scp logic ...
```

**Step 2: Verify code syntax**

Run: `python3 -m py_compile robot_monitor/offline_server.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add robot_monitor/offline_server.py
git commit -m "feat: implement special upload path for port 10123 in upload_images_from_robot"
```

---

### Task 2: Verify `upload_images_range_from_robot` in `offline_server.py`

**Files:**
- Modify: `robot_monitor/offline_server.py:1059-1137`

**Step 1: Ensure logic handles port 10123 correctly**

Verify that `port_suffix = str(port)[-4:]` and `local_base = os.path.join(LOCAL_IMAGE_CUSTOM_BASE, port_suffix)` correctly results in `/home/youfeng/debug/custom/0123` for port 10123.

**Step 2: Commit**

```bash
git add robot_monitor/offline_server.py
git commit -m "feat: ensure upload_images_range_from_robot uses correct custom path for port 10123"
```