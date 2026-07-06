# Perception Streaming Watchdog Systemd Design

## Goal

Keep the Perception Streaming web service at `http://192.168.55.247:5173/` available after machine reboot and recover automatically when the Vite dev server exits or stops responding.

## Current State

The project already has a Vite watchdog:

- `watchdog.sh` checks the Vite process, port `5173`, and HTTP status.
- `start-watchdog.sh` starts the watchdog with `nohup` and a PID file.
- `stop-watchdog.sh` stops the watchdog and Vite.
- `WATCHDOG.md` documents manual usage and a `crontab @reboot` option.

This is useful for manual recovery, but it is not a robust long-running system service. If the watchdog process itself exits, `nohup` and `crontab @reboot` do not provide runtime supervision.

## Selected Approach

Use systemd to manage the watchdog process.

Systemd will:

- start the watchdog on boot;
- restart the watchdog if it crashes;
- provide standard service status through `systemctl status`;
- centralize operational commands for enable/start/stop/restart.

The watchdog will continue to manage the Vite process and restart Vite when health checks fail.

## Components

### `script/perception-streaming-watchdog.service`

A systemd unit that runs the project watchdog script from the repository directory.

Key behavior:

- `After=network-online.target`
- `Wants=network-online.target`
- `WorkingDirectory=/media/sda1/perception_process/perception_streaming`
- `ExecStart=/bin/bash /media/sda1/perception_process/perception_streaming/watchdog.sh`
- `Restart=always`
- `RestartSec=10`

### `script/install_perception_streaming_watchdog.sh`

An installation helper that:

1. copies the service file to `/etc/systemd/system/`;
2. reloads systemd;
3. enables and starts the service;
4. prints status and log commands.

This script requires root privileges or `sudo`.

### `watchdog.sh` hardening

Make the existing watchdog easier to reuse under systemd:

- allow `PROJECT_DIR`, `LOG_FILE`, `VITE_LOG`, `CHECK_INTERVAL`, `VITE_URL`, and startup timeout values to be overridden through environment variables;
- keep current defaults so existing manual usage continues to work;
- use the existing HTTP default `http://127.0.0.1:5173/`.

### Documentation

Update `WATCHDOG.md` and README deployment notes to recommend systemd for long-running use, while keeping manual `start-watchdog.sh` usage for temporary debugging.

## Operational Commands

Expected commands after installation:

```bash
sudo systemctl status perception-streaming-watchdog
sudo systemctl restart perception-streaming-watchdog
sudo systemctl stop perception-streaming-watchdog
sudo journalctl -u perception-streaming-watchdog -f
 tail -f /tmp/vite-watchdog.log
 tail -f /tmp/vite-dev.log
```

## Error Handling

- If Vite exits or port `5173` is not listening, `watchdog.sh` restarts Vite.
- If Vite returns a non-200 HTTP response, `watchdog.sh` restarts Vite.
- If `watchdog.sh` exits unexpectedly, systemd restarts it.
- If Vite repeatedly fails to start, the watchdog applies its existing cooldown behavior; systemd keeps the watchdog process itself alive.

## Testing

Verification should include:

1. shell syntax check for edited scripts;
2. service file syntax verification with `systemd-analyze verify` when available;
3. install and enable the service;
4. check `systemctl is-enabled` and `systemctl is-active`;
5. open `http://192.168.55.247:5173/` in browser;
6. simulate Vite failure with `pkill -f vite` and verify the page recovers.

## Scope Boundaries

This design does not convert the app to a production static build or Docker deployment. The goal is to stabilize the existing Vite-based service with the smallest operational change.