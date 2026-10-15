<#
    Сборка артефактов sketchfab-toolkit:

      dist\sketchfab-toolkit.exe                  — портативный exe (PyInstaller, onefile)
      dist\sketchfab-toolkit-setup-<версия>.exe   — установщик (PyInstaller + payload.zip + PowerShell)
      dist\SHA256SUMS.txt                         — контрольные суммы

    Нужны: Python 3.9+ с pyinstaller, Pillow (только для иконки).

        powershell -ExecutionPolicy Bypass -File build.ps1
        powershell -ExecutionPolicy Bypass -File build.ps1 -Version 1.0.1 -SkipIcon
#>
[CmdletBinding()]
param(
    [string]$Version = '1.0.0',
    [switch]$SkipIcon
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
Set-Location $Root

if (Get-Command py -ErrorAction SilentlyContinue) {
    $pyExe = 'py'
    $pyArgs = @('-3')
} else {
    $pyExe = 'python'
    $pyArgs = @()
}

function Invoke-Python {
    & $pyExe @pyArgs @args
    if ($LASTEXITCODE -ne 0) {
        throw "python завершился с кодом $LASTEXITCODE"
    }
}

function Write-Step([string]$text) {
    Write-Host ''
    Write-Host "==> $text" -ForegroundColor Cyan
}

Write-Host ''
Write-Host "  сборка sketchfab-toolkit $Version" -ForegroundColor White

# Чистим dist, чтобы туда не попадали артефакты прошлых сборок.
Remove-Item -Recurse -Force (Join-Path $Root 'dist') -ErrorAction SilentlyContinue

# 1. иконка ------------------------------------------------------------------
if ($SkipIcon) {
    Write-Step 'Иконка: пропущена (-SkipIcon)'
} else {
    Write-Step 'Иконка'
    Invoke-Python build/make_icon.py
}

# 2. exe ---------------------------------------------------------------------
Write-Step 'PyInstaller: dist\sketchfab-toolkit.exe'
# Скрипты сборки лежат в build\, а весь мусор PyInstaller — в .pyinstaller\,
# чтобы рабочие файлы репозитория и временные каталоги не смешивались.
$iconPath = Join-Path $Root 'assets\sketchfab-toolkit.ico'
$versionFile = Join-Path $Root 'build\version_info.txt'
$distPath = Join-Path $Root 'dist'
$scratch = Join-Path $Root '.pyinstaller'
$workPath = Join-Path $scratch 'work'
$specPath = $scratch

Remove-Item -Recurse -Force $workPath -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $scratch -Force | Out-Null
Invoke-Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --console `
    --name sketchfab-toolkit `
    --icon $iconPath `
    --version-file $versionFile `
    --distpath $distPath `
    --workpath $workPath `
    --specpath $specPath `
    --exclude-module tkinter `
    --exclude-module PIL `
    --exclude-module numpy `
    --exclude-module pytest `
    --exclude-module pydoc `
    cli.py

$portable = Join-Path $Root 'dist\sketchfab-toolkit.exe'
if (-not (Test-Path $portable)) { throw 'exe не собран' }
Write-Host ("  готово: {0:N1} MB" -f ((Get-Item $portable).Length / 1MB)) -ForegroundColor Green

Write-Step 'Проверка exe'
& $portable --version
if ($LASTEXITCODE -ne 0) { throw "собранный exe не запускается (код $LASTEXITCODE)" }

# 3. установщик --------------------------------------------------------------
Write-Step 'Установщик: payload.zip'
$payloadDir = Join-Path $scratch 'payload'
Remove-Item -Recurse -Force $payloadDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $payloadDir -Force | Out-Null
Copy-Item $portable $payloadDir
foreach ($name in @('install.ps1', 'uninstall.ps1', 'uninstall.cmd')) {
    Copy-Item (Join-Path $Root "installer\$name") $payloadDir
}

$payloadZip = Join-Path $scratch 'payload.zip'
Remove-Item $payloadZip -Force -ErrorAction SilentlyContinue
Invoke-Python build/make_payload.py $payloadDir $payloadZip

Write-Step 'PyInstaller: установщик'
$setupIconPath = Join-Path $Root 'assets\sketchfab-toolkit.ico'
$setupVersionFile = Join-Path $Root 'build\version_info_setup.txt'
$setupWorkPath = Join-Path $scratch 'work-setup'
Remove-Item -Recurse -Force $setupWorkPath -ErrorAction SilentlyContinue

Invoke-Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --console `
    --name "sketchfab-toolkit-setup-$Version" `
    --icon $setupIconPath `
    --version-file $setupVersionFile `
    --distpath $distPath `
    --workpath $setupWorkPath `
    --specpath $specPath `
    --add-data "$payloadZip;." `
    --exclude-module tkinter `
    --exclude-module PIL `
    --exclude-module numpy `
    --exclude-module pytest `
    installer/make_installer.py

$setup = Join-Path $Root "dist\sketchfab-toolkit-setup-$Version.exe"
if (-not (Test-Path $setup)) { throw 'установщик не собран' }
Write-Host ("  готово: {0:N1} MB" -f ((Get-Item $setup).Length / 1MB)) -ForegroundColor Green

# 4. контрольные суммы -------------------------------------------------------
Write-Step 'SHA256'
$sums = Join-Path $Root 'dist\SHA256SUMS.txt'
$lines = foreach ($file in @($portable, $setup)) {
    $hash = (Get-FileHash -Algorithm SHA256 -Path $file).Hash.ToLower()
    "{0}  {1}" -f $hash, (Split-Path -Leaf $file)
}
Set-Content -Path $sums -Value $lines -Encoding ASCII
Get-Content $sums | ForEach-Object { Write-Host "  $_" }

Write-Host ''
Write-Host '  Артефакты в dist\:' -ForegroundColor White
Get-ChildItem 'dist' -File | ForEach-Object {
    Write-Host ("    {0,-42} {1,8:N1} MB" -f $_.Name, ($_.Length / 1MB))
}
Write-Host ''
