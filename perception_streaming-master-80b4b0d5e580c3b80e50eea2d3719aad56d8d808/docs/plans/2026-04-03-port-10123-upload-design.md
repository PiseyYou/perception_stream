---
name: Special Path for Port 10123 Upload
description: Adjust image upload destination to /home/youfeng/debug/custom/0123/ for port 10123
type: project
---

# Design: Port 10123 Upload Customization

## Overview
When uploading images through the "Real-time Monitoring" (StereoAnalysis2Panel) tab, if the port is 10123, the images must be saved to a specific path using the last 4 digits of the port.

## Goals
- Redirect uploads for port 10123 to `/home/youfeng/debug/custom/0123/`.
- Create parent directories if they do not exist.
- Maintain existing behavior for other ports unless specified.

## Implementation Details

### Core Logic
In `robot_monitor/offline_server.py`:

1.  **`upload_images_from_robot` (Single Date)**:
    - Add a conditional check: `if port == 10123:`.
    - Set `local_dir = os.path.join("/home/youfeng/debug/custom", "0123", date_str)`.
    - Otherwise, keep `local_dir = os.path.join("/home/youfeng/debug/03", date_str)`.

2.  **`upload_images_range_from_robot` (Date Range)**:
    - This already uses `/home/youfeng/debug/custom/<port_suffix>`.
    - Ensure the logic consistently uses the last 4 digits (`0123`).

## Success Criteria
- Uploading from port 10123 results in files appearing in `/home/youfeng/debug/custom/0123/`.
- Folders are created automatically.
- Returns correct success status to the frontend.
