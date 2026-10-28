#!/usr/bin/env bash
# ============================================================================
# HB AI · Smart DNS — Автоматическая установка и сборка для macOS
# Запуск одной командой:
#   curl -sSL https://raw.githubusercontent.com/animesao/hb-ai-xbox-dns/main/install-mac.sh | bash
# ============================================================================
set -euo pipefail

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
RED="\033[0;31m"
RESET="\033[0m"

echo -e "${BOLD}${CYAN}======================================================${RESET}"
echo -e "${BOLD}${CYAN}   HB AI · Smart DNS — Установка для macOS (MacBook)  ${RESET}"
echo -e "${BOLD}${CYAN}======================================================${RESET}"

# 1. Проверка наличия компилятора Swift / Xcode Command Line Tools
if ! command -v swift >/dev/null 2>&1; then
    echo -e "\n${YELLOW}Инструменты сборки Swift/Xcode не обнаружены.${RESET}"
    echo -e "Запускаем установку Apple Command Line Tools..."
    xcode-select --install 2>/dev/null || true
    echo -e "\n${BOLD}Пожалуйста, завершите установку во всплывающем системном окне macOS,${RESET}"
    echo -e "${BOLD}а затем запустите эту команду снова.${RESET}"
    exit 1
fi

echo -e "\n${GREEN}✓${RESET} Компилятор Swift найден: $(swift --version | head -1)"

# 2. Создание временной папки для изолированной сборки
TMP_DIR="$(mktemp -d -t hbai_smart_dns_build_XXXXXX)"
cleanup() {
    echo -e "\n${CYAN}Очистка временных файлов и кэша сборки...${RESET}"
    rm -rf "$TMP_DIR"
    echo -e "${GREEN}✓${RESET} Весь сборочный мусор удалён."
}
trap cleanup EXIT INT TERM

# 3. Получение исходных файлов
SRC_DIR=""
if [ -f "$(dirname "$0")/mac/Package.swift" ]; then
    echo -e "${CYAN}Используем локальные исходники из текущей папки...${RESET}"
    SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
else
    echo -e "${CYAN}Загрузка актуального исходного кода из репозитория...${RESET}"
    if command -v git >/dev/null 2>&1; then
        git clone --depth 1 https://github.com/animesao/hb-ai-xbox-dns.git "$TMP_DIR/repo" >/dev/null 2>&1
        SRC_DIR="$TMP_DIR/repo"
    else
        mkdir -p "$TMP_DIR/repo"
        curl -sSL https://github.com/animesao/hb-ai-xbox-dns/archive/refs/heads/main.tar.gz | tar -xz -C "$TMP_DIR/repo" --strip-components=1
        SRC_DIR="$TMP_DIR/repo"
    fi
fi

# 4. Сборка приложения
echo -e "${CYAN}Компиляция приложения в Release-режиме...${RESET}"
cd "$SRC_DIR/mac"
swift build -c release >/dev/null

if [ ! -f ".build/release/HBAISmartDNS" ]; then
    echo -e "${RED}Ошибка: бинарный файл HBAISmartDNS не был скомпилирован.${RESET}" >&2
    exit 1
fi

# 5. Определение папки установки
INSTALL_DIR="/Applications"
if [ ! -w "$INSTALL_DIR" ]; then
    INSTALL_DIR="$HOME/Applications"
    mkdir -p "$INSTALL_DIR"
fi

APP_TARGET="$INSTALL_DIR/HB AI Smart DNS.app"
echo -e "${CYAN}Формирование пакета приложения: ${APP_TARGET}...${RESET}"

rm -rf "$APP_TARGET"
mkdir -p "$APP_TARGET/Contents/MacOS" "$APP_TARGET/Contents/Resources"
cp ".build/release/HBAISmartDNS" "$APP_TARGET/Contents/MacOS/"
cp "Info.plist" "$APP_TARGET/Contents/"
cp res/*.ttf "$APP_TARGET/Contents/Resources/"

# 6. Генерация иконки .icns из res/icon.png
if [ -f "res/icon.png" ]; then
    ICONSET="$TMP_DIR/app.iconset"
    mkdir -p "$ICONSET"
    for s in 16 32 128 256 512; do
        sips -z $s $s res/icon.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null 2>&1 || true
        d=$((s * 2))
        sips -z $d $d res/icon.png --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null 2>&1 || true
    done
    iconutil -c icns "$ICONSET" -o "$APP_TARGET/Contents/Resources/app.icns" >/dev/null 2>&1 || true
fi

# 7. Подпись ad-hoc и снятие карантина Gatekeeper
echo -e "${CYAN}Настройка безопасности и снятие карантина macOS...${RESET}"
codesign --force --deep -s - "$APP_TARGET" >/dev/null 2>&1 || true
xattr -dr com.apple.quarantine "$APP_TARGET" >/dev/null 2>&1 || true

# Если запускались из локальной папки, удаляем временный .build
if [ "$SRC_DIR" != "$TMP_DIR/repo" ]; then
    rm -rf "$SRC_DIR/mac/.build" "$SRC_DIR/mac/build" 2>/dev/null || true
fi

echo -e "\n${BOLD}${GREEN}======================================================${RESET}"
echo -e "${BOLD}${GREEN}   ✓ HB AI · Smart DNS успешно установлен!           ${RESET}"
echo -e "${BOLD}${GREEN}======================================================${RESET}"
echo -e "Расположение: ${BOLD}$APP_TARGET${RESET}"
echo -e "Вы можете запускать приложение из Launchpad или папки «Программы»."

# 8. Запуск приложения
echo -e "\n${CYAN}Запускаем приложение...${RESET}"
open "$APP_TARGET"
