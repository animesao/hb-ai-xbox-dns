#!/usr/bin/env bash
# Удаление HB AI · Smart DNS из Linux
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Скрипт удаления необходимо запускать от имени root (sudo ./uninstall.sh)" >&2
  exit 1
fi

echo "Удаление HB AI · Smart DNS..."
if command -v hb-ai-smart-dns >/dev/null 2>&1; then
  hb-ai-smart-dns --disable >/dev/null 2>&1 || true
fi

rm -rf /opt/hb-ai-smart-dns
rm -f /usr/local/bin/hb-ai-smart-dns
rm -f /usr/share/icons/hicolor/256x256/apps/hb-ai-smart-dns.png
rm -f /usr/share/applications/hb-ai-smart-dns.desktop
rm -rf /var/lib/hb-ai-smart-dns

echo "HB AI · Smart DNS успешно удалён."
