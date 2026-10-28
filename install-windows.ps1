# ============================================================================
# HB AI · Smart DNS — Автоматическая установка для Windows
# Запуск одной командой в PowerShell:
#   irm https://raw.githubusercontent.com/animesao/hb-ai-xbox-dns/main/install-windows.ps1 | iex
# ============================================================================
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "   HB AI · Smart DNS — Установка для Windows          " -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

$installDir = Join-Path $env:LOCALAPPDATA "Programs\HB AI Smart DNS"
if (!(Test-Path $installDir)) {
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
}
$targetExe = Join-Path $installDir "HB_AI_Xbox_DNS.exe"

$sourceExe = $null

# 1. Проверяем локальный файл в текущей папке
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "HB_AI_Xbox_DNS.exe"))) {
    $sourceExe = Join-Path $PSScriptRoot "HB_AI_Xbox_DNS.exe"
    Write-Host "`n[+] Используем локальный файл: $sourceExe" -ForegroundColor Green
}
# 2. Если есть исходники, можно быстро собрать через csc.exe
elseif ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "XboxDns.cs"))) {
    $csc = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    if (Test-Path $csc) {
        Write-Host "`n[+] Компиляция из локального исходного кода..." -ForegroundColor Cyan
        & "$PSScriptRoot\build.bat" | Out-Null
        if (Test-Path (Join-Path $PSScriptRoot "HB_AI_Xbox_DNS.exe")) {
            $sourceExe = Join-Path $PSScriptRoot "HB_AI_Xbox_DNS.exe"
        }
    }
}

# 3. Если локального файла нет, скачиваем актуальный релиз с GitHub
if (!$sourceExe) {
    Write-Host "`n[+] Загрузка последней версии с GitHub Releases..." -ForegroundColor Cyan
    $tempExe = Join-Path $env:TEMP "HB_AI_Xbox_DNS_download.exe"
    $url = "https://github.com/animesao/hb-ai-xbox-dns/releases/latest/download/HB_AI_Xbox_DNS.exe"
    
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $wc = New-Object System.Net.WebClient
    try {
        $wc.DownloadFile($url, $tempExe)
        $sourceExe = $tempExe
        Write-Host "[+] Файл успешно загружен." -ForegroundColor Green
    } catch {
        Write-Host "[-] Не удалось загрузить файл из $url : $_" -ForegroundColor Red
        exit 1
    }
}

# 4. Копирование в каталог установки
Write-Host "[+] Установка в: $targetExe" -ForegroundColor Cyan
try {
    # Завершаем запущенный процесс, если он открыт
    Get-Process "HB_AI_Xbox_DNS" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 300
    Copy-Item -Path $sourceExe -Destination $targetExe -Force
} catch {
    Write-Host "[-] Ошибка копирования: $_" -ForegroundColor Red
    exit 1
}

# 5. Создание ярлыков (Рабочий стол и меню «Пуск»)
Write-Host "[+] Создание ярлыков..." -ForegroundColor Cyan
$wsh = New-Object -ComObject WScript.Shell

# Ярлык на Рабочем столе
$desktop = [Environment]::GetFolderPath("Desktop")
$desktopShortcut = Join-Path $desktop "HB AI · Smart DNS.lnk"
$sc = $wsh.CreateShortcut($desktopShortcut)
$sc.TargetPath = $targetExe
$sc.WorkingDirectory = $installDir
$sc.IconLocation = "$targetExe,0"
$sc.Description = "HB AI · Smart DNS — Обход блокировок нейросетей, YouTube, Discord, Roblox, Steam"
$sc.Save()

# Ярлык в меню «Пуск»
$programs = [Environment]::GetFolderPath("Programs")
$startMenuShortcut = Join-Path $programs "HB AI · Smart DNS.lnk"
$sc2 = $wsh.CreateShortcut($startMenuShortcut)
$sc2.TargetPath = $targetExe
$sc2.WorkingDirectory = $installDir
$sc2.IconLocation = "$targetExe,0"
$sc2.Description = "HB AI · Smart DNS — Обход блокировок нейросетей, YouTube, Discord, Roblox, Steam"
$sc2.Save()

# Очистка временного файла
if ($sourceExe -and $sourceExe.StartsWith($env:TEMP)) {
    Remove-Item -Path $sourceExe -Force -ErrorAction SilentlyContinue
}

Write-Host "`n======================================================" -ForegroundColor Green
Write-Host "   ✓ HB AI · Smart DNS успешно установлен!           " -ForegroundColor Green
Write-Host "======================================================" -ForegroundColor Green
Write-Host "Расположение: $targetExe"
Write-Host "Ярлыки созданы на Рабочем столе и в меню «Пуск»."

Write-Host "`nЗапускаем программу..." -ForegroundColor Cyan
Start-Process $targetExe
