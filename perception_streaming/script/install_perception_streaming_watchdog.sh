#!/bin/bash
set -euo pipefail

SERVICE_NAME="perception-streaming-watchdog.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_SERVICE="$SCRIPT_DIR/$SERVICE_NAME"
TARGET_SERVICE="/etc/systemd/system/$SERVICE_NAME"

if [ "$(id -u)" -ne 0 ]; then
    echo "请使用 sudo 运行: sudo $0"
    exit 1
fi

if [ ! -f "$SOURCE_SERVICE" ]; then
    echo "找不到服务文件: $SOURCE_SERVICE"
    exit 1
fi

install -m 0644 "$SOURCE_SERVICE" "$TARGET_SERVICE"
systemctl daemon-reload
systemctl enable --now perception-streaming-watchdog.service

echo "已安装并启动 perception-streaming-watchdog.service"
echo ""
echo "常用命令:"
echo "  sudo systemctl status perception-streaming-watchdog.service"
echo "  sudo systemctl restart perception-streaming-watchdog.service"
echo "  sudo journalctl -u perception-streaming-watchdog.service -f"
echo "  tail -f /tmp/vite-watchdog.log"
echo "  tail -f /tmp/vite-dev.log"
echo ""
systemctl status perception-streaming-watchdog.service --no-pager
