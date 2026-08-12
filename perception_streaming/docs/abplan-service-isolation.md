# A/B shadow service isolation

The original project is kept on `perception-streaming.service` with its original
directory and ports: frontend `5173`, API `8769`.

The A/B shadow-prelabel worktree runs separately as
`perception-streaming-abplan.service`:

| Component | Bind | Port |
| --- | --- | --- |
| A/B frontend | `0.0.0.0` | `5174` |
| A/B API | `127.0.0.1` | `8770` |

Access the A/B UI at `http://192.168.55.245:5174`. Its Vite proxy routes API
requests to the loopback-only port `8770`; the API is intentionally not exposed
directly to the LAN.

The service definition is versioned at
`deploy/systemd/perception-streaming-abplan.service`. The installed user unit
uses the same content. CVAT credentials remain in the existing mode-600
environment file and are attached only to the A/B service.
