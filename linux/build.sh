#!/usr/bin/env bash
# Сборка HB AI · Smart DNS для Linux: тесты → tar.gz / бинарник.
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Запуск тестов ==="
python3 tests.py

echo "=== Сборка дистрибутива Linux ==="
BUILD_DIR="build/HB_AI_Smart_DNS_linux"
rm -rf build && mkdir -p "$BUILD_DIR/res"

# Если доступен PyInstaller, собираем автономный бинарный файл ELF
if command -v pyinstaller >/dev/null 2>&1; then
  echo "Сборка standalone бинарника через PyInstaller..."
  pyinstaller --onefile --noconfirm \
    --name hb-ai-smart-dns \
    --add-data "res:res" \
    hb_ai_smart_dns.py
  cp dist/hb-ai-smart-dns "$BUILD_DIR/"
  rm -rf build_pyinstaller dist hb-ai-smart-dns.spec
else
  echo "PyInstaller не найден, создаём универсальный скриптовый пакет..."
  cp hb-ai-smart-dns "$BUILD_DIR/"
  chmod +x "$BUILD_DIR/hb-ai-smart-dns"
fi

cp hb_ai_smart_dns.py "$BUILD_DIR/"
cp install.sh "$BUILD_DIR/"
cp uninstall.sh "$BUILD_DIR/"
chmod +x "$BUILD_DIR/install.sh" "$BUILD_DIR/uninstall.sh"
cp res/icon.png "$BUILD_DIR/res/"
cp res/hb-ai-smart-dns.desktop "$BUILD_DIR/res/"

cat << 'EOF' > "$BUILD_DIR/README.txt"
HB AI · Smart DNS для Linux

ChatGPT, Claude, Gemini, ElevenLabs, Discord и YouTube одной кнопкой.

УСТАНОВКА:
  sudo ./install.sh

ЗАПУСК:
  hb-ai-smart-dns            # Запуск графического интерфейса
  hb-ai-smart-dns --status   # Статус DNS
  hb-ai-smart-dns --check    # Проверка доступности сайтов
  hb-ai-smart-dns --best     # Найти лучший сервис
  hb-ai-smart-dns --help     # Все параметры CLI

УДАЛЕНИЕ:
  sudo ./uninstall.sh
EOF

cd build
tar -czvf "HB_AI_Smart_DNS_linux.tar.gz" "HB_AI_Smart_DNS_linux"
ls -la "HB_AI_Smart_DNS_linux.tar.gz"
sha256sum "HB_AI_Smart_DNS_linux.tar.gz" || shasum -a 256 "HB_AI_Smart_DNS_linux.tar.gz" || true
echo "Сборка завершена: build/HB_AI_Smart_DNS_linux.tar.gz"
