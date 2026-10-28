#!/usr/bin/env bash
# Установка HB AI · Smart DNS в Linux
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Скрипт установки необходимо запускать от имени root (sudo ./install.sh)" >&2
  exit 1
fi

DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Установка HB AI · Smart DNS..."
mkdir -p /opt/hb-ai-smart-dns
cp "$DIR/hb_ai_smart_dns.py" /opt/hb-ai-smart-dns/
cp -r "$DIR/res" /opt/hb-ai-smart-dns/
chmod +x /opt/hb-ai-smart-dns/hb_ai_smart_dns.py

# Ссылка в /usr/local/bin
cat << 'EOF' > /usr/local/bin/hb-ai-smart-dns
#!/bin/sh
exec python3 /opt/hb-ai-smart-dns/hb_ai_smart_dns.py "$@"
EOF
chmod +x /usr/local/bin/hb-ai-smart-dns

# Иконка
mkdir -p /usr/share/icons/hicolor/256x256/apps
if [ -f "$DIR/res/icon.png" ]; then
  cp "$DIR/res/icon.png" /usr/share/icons/hicolor/256x256/apps/hb-ai-smart-dns.png
fi

# Ярлык в меню приложений
mkdir -p /usr/share/applications
cp "$DIR/res/hb-ai-smart-dns.desktop" /usr/share/applications/

echo "Установка успешно завершена!"
echo "Вы можете запускать HB AI · Smart DNS командой hb-ai-smart-dns или из меню приложений."
