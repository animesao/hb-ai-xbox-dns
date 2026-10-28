#!/usr/bin/env bash
# ============================================================================
# HB AI · Smart DNS — Автоматическая установка для Linux
# Запуск одной командой:
#   curl -sSL https://raw.githubusercontent.com/animesao/hb-ai-xbox-dns/main/install-linux.sh | bash
# ============================================================================
set -euo pipefail

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
RED="\033[0;31m"
RESET="\033[0m"

echo -e "${BOLD}${CYAN}======================================================${RESET}"
echo -e "${BOLD}${CYAN}   HB AI · Smart DNS — Установка для Linux           ${RESET}"
echo -e "${BOLD}${CYAN}======================================================${RESET}"

# 1. Проверка наличия Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo -e "${RED}Ошибка: Python 3 не установлен.${RESET}" >&2
    echo "Пожалуйста, установите Python 3 (например: sudo apt install python3) и повторите попытку." >&2
    exit 1
fi

echo -e "\n${GREEN}✓${RESET} Python 3 найден: $(python3 --version)"

# Проверка модуля tkinter
if ! python3 -c "import tkinter" >/dev/null 2>&1; then
    echo -e "${YELLOW}Предупреждение: модуль python3-tk не обнаружен.${RESET}"
    echo "Для работы графического интерфейса рекомендуется установить: sudo apt install python3-tk (или python3-tkinter)"
    echo "Консольный режим (--cli, --enable, --check) при этом будет работать сразу."
fi

# 2. Создание временной папки
TMP_DIR="$(mktemp -d -t hbai_linux_install_XXXXXX)"
cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT INT TERM

# 3. Получение файлов
SRC_DIR=""
if [ -f "$(dirname "$0")/linux/hb_ai_smart_dns.py" ]; then
    echo -e "${CYAN}Используем локальные файлы из текущей папки...${RESET}"
    SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
else
    echo -e "${CYAN}Загрузка актуальных файлов из репозитория...${RESET}"
    if command -v git >/dev/null 2>&1; then
        git clone --depth 1 https://github.com/animesao/hb-ai-xbox-dns.git "$TMP_DIR/repo" >/dev/null 2>&1
        SRC_DIR="$TMP_DIR/repo"
    else
        mkdir -p "$TMP_DIR/repo"
        curl -sSL https://github.com/animesao/hb-ai-xbox-dns/archive/refs/heads/main.tar.gz | tar -xz -C "$TMP_DIR/repo" --strip-components=1
        SRC_DIR="$TMP_DIR/repo"
    fi
fi

# 4. Установка (глобальная для root или локальная для обычного пользователя)
if [ "$(id -u)" -eq 0 ]; then
    APP_DIR="/opt/hb-ai-smart-dns"
    BIN_FILE="/usr/local/bin/hb-ai-smart-dns"
    DESKTOP_DIR="/usr/share/applications"
    ICON_DIR="/usr/share/icons/hicolor/256x256/apps"
else
    APP_DIR="$HOME/.local/share/hb-ai-smart-dns"
    BIN_FILE="$HOME/.local/bin/hb-ai-smart-dns"
    DESKTOP_DIR="$HOME/.local/share/applications"
    ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
fi

echo -e "${CYAN}Копирование файлов программы в ${APP_DIR}...${RESET}"
mkdir -p "$APP_DIR" "$(dirname "$BIN_FILE")" "$DESKTOP_DIR" "$ICON_DIR"

cp "$SRC_DIR/linux/hb_ai_smart_dns.py" "$APP_DIR/hb_ai_smart_dns.py"
chmod +x "$APP_DIR/hb_ai_smart_dns.py"

# Копирование ресурсов
if [ -d "$SRC_DIR/res" ]; then
    cp -r "$SRC_DIR/res" "$APP_DIR/"
elif [ -d "$SRC_DIR/linux/res" ]; then
    cp -r "$SRC_DIR/linux/res" "$APP_DIR/"
fi

# Копирование иконки
if [ -f "$APP_DIR/res/icon.png" ]; then
    cp "$APP_DIR/res/icon.png" "$ICON_DIR/hb-ai-smart-dns.png"
fi

# 5. Создание исполняемого скрипта-обертки
cat << EOF > "$BIN_FILE"
#!/bin/sh
exec python3 "$APP_DIR/hb_ai_smart_dns.py" "\$@"
EOF
chmod +x "$BIN_FILE"

# 6. Создание ярлыка .desktop
cat << EOF > "$DESKTOP_DIR/hb-ai-smart-dns.desktop"
[Desktop Entry]
Name=HB AI · Smart DNS
Comment=Обход блокировок нейросетей, YouTube, Discord, Roblox, Steam
Exec=$BIN_FILE
Icon=hb-ai-smart-dns
Terminal=false
Type=Application
Categories=Network;Utility;
Keywords=dns;smartdns;vpn;ai;chatgpt;youtube;discord;roblox;
EOF

# Обновление баз данных меню и иконок
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$(dirname "$ICON_DIR")" >/dev/null 2>&1 || true
fi

echo -e "\n${BOLD}${GREEN}======================================================${RESET}"
echo -e "${BOLD}${GREEN}   ✓ HB AI · Smart DNS успешно установлен!           ${RESET}"
echo -e "${BOLD}${GREEN}======================================================${RESET}"
echo -e "Исполняемый файл: ${BOLD}$BIN_FILE${RESET}"
echo -e "Программа добавлена в меню приложений и доступна по команде:"
echo -e "  ${BOLD}hb-ai-smart-dns${RESET}        — запуск графического интерфейса"
echo -e "  ${BOLD}hb-ai-smart-dns --status${RESET} — проверка статуса"
echo -e "  ${BOLD}hb-ai-smart-dns --help${RESET}   — консольные команды (CLI)"

# Проверка PATH для пользователя
if [ "$(id -u)" -ne 0 ] && [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo -e "\n${YELLOW}Примечание:${RESET} Добавьте ~/.local/bin в переменную PATH, если команда не находится сразу:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
