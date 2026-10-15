<#
    Установщик sketchfab-toolkit для текущего пользователя.
    Права администратора не нужны: всё ставится в профиль пользователя.

    Запускается из распакованного SFX-архива — рядом со скриптом должен лежать
    sketchfab-toolkit.exe. Что делает:

      1. копирует sketchfab-toolkit.exe в папку установки;
      2. добавляет папку установки в PATH пользователя;
      3. создаёт ярлык в меню «Пуск»;
      4. регистрирует запись в «Приложения и возможности» (ветка HKCU);
      5. кладёт рядом uninstall.cmd для удаления.

    Параметры нужны в основном для автотестов:
      -InstallDir <path>   куда ставить (по умолчанию %LOCALAPPDATA%\Programs\sketchfab-toolkit)
      -SkipPath            не трогать PATH
      -SkipShortcut        не создавать ярлык
      -SkipRegistry        не писать запись об удалении
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [switch]$SkipPath,
    [switch]$SkipShortcut,
    [switch]$SkipRegistry
)

$ErrorActionPreference = 'Stop'

$AppName = 'sketchfab-toolkit'
$Version = '1.0.0'
$Publisher = 'wesiks'

function Say([string]$text, [string]$color = 'Gray') {
    Write-Host $text -ForegroundColor $color
}

function Get-UserPathRaw {
    $key = 'HKCU:\Environment'
    if (-not (Test-Path $key)) { return '' }
    $value = (Get-ItemProperty -Path $key -Name Path -ErrorAction SilentlyContinue).Path
    if ($null -eq $value) { return '' }
    return [string]$value
}

function Add-ToUserPath([string]$directory) {
    # Правим именно REG_EXPAND_SZ в реестре, чтобы не развернуть %USERPROFILE% и т.п.
    $raw = Get-UserPathRaw
    $parts = @($raw -split ';' | Where-Object { $_ -ne '' })
    foreach ($part in $parts) {
        if ($part.TrimEnd('\') -ieq $directory.TrimEnd('\')) {
            return $false
        }
    }
    $updated = (@($parts) + $directory) -join ';'
    if (-not (Test-Path 'HKCU:\Environment')) {
        New-Item -Path 'HKCU:\Environment' -Force | Out-Null
    }
    Set-ItemProperty -Path 'HKCU:\Environment' -Name Path -Value $updated -Type ExpandString
    return $true
}

function New-StartMenuShortcut([string]$target) {
    $menu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
    if (-not (Test-Path $menu)) {
        New-Item -ItemType Directory -Path $menu -Force | Out-Null
    }
    $link = Join-Path $menu "$AppName.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($link)
    $shortcut.TargetPath = $target
    $shortcut.WorkingDirectory = (Split-Path -Parent $target)
    $shortcut.Description = 'Sketchfab Data API v3 + конвертер OSG.js'
    $shortcut.IconLocation = "$target,0"
    $shortcut.Save()
    return $link
}

Say ''
Say '  sketchfab-toolkit 1.0.0 — установка' 'Cyan'
Say '  ---------------------------------' 'DarkGray'
Say ''

$sourceExe = Join-Path $PSScriptRoot "$AppName.exe"
if (-not (Test-Path $sourceExe)) {
    Say "  [!] Рядом со скриптом нет $AppName.exe — установка прервана." 'Red'
    exit 1
}

if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\$AppName"
}
$InstallDir = [System.IO.Path]::GetFullPath($InstallDir)

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
$targetExe = Join-Path $InstallDir "$AppName.exe"
Copy-Item -Path $sourceExe -Destination $targetExe -Force
Say "  [1/4] Файлы скопированы в $InstallDir" 'Green'

Copy-Item -Path (Join-Path $PSScriptRoot 'uninstall.ps1') -Destination (Join-Path $InstallDir 'uninstall.ps1') -Force
Copy-Item -Path (Join-Path $PSScriptRoot 'uninstall.cmd') -Destination (Join-Path $InstallDir 'uninstall.cmd') -Force

if ($SkipPath) {
    Say '  [2/4] PATH не изменялся (-SkipPath)' 'DarkGray'
} else {
    if (Add-ToUserPath $InstallDir) {
        Say '  [2/4] Папка добавлена в PATH пользователя' 'Green'
    } else {
        Say '  [2/4] Папка уже была в PATH пользователя' 'DarkGray'
    }
}

if ($SkipShortcut) {
    Say '  [3/4] Ярлык не создавался (-SkipShortcut)' 'DarkGray'
} else {
    try {
        $link = New-StartMenuShortcut $targetExe
        Say "  [3/4] Ярлык в меню «Пуск»: $link" 'Green'
    } catch {
        Say "  [3/4] Ярлык создать не удалось: $($_.Exception.Message)" 'Yellow'
    }
}

if ($SkipRegistry) {
    Say '  [4/4] Запись об удалении не создавалась (-SkipRegistry)' 'DarkGray'
} else {
    $uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppName"
    New-Item -Path $uninstallKey -Force | Out-Null
    $sizeKb = [int]((Get-ChildItem -Path $InstallDir -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1KB)
    $uninstallPs = Join-Path $InstallDir 'uninstall.ps1'
    Set-ItemProperty -Path $uninstallKey -Name DisplayName -Value "$AppName $Version"
    Set-ItemProperty -Path $uninstallKey -Name DisplayVersion -Value $Version
    Set-ItemProperty -Path $uninstallKey -Name Publisher -Value $Publisher
    Set-ItemProperty -Path $uninstallKey -Name InstallLocation -Value $InstallDir
    Set-ItemProperty -Path $uninstallKey -Name DisplayIcon -Value $targetExe
    Set-ItemProperty -Path $uninstallKey -Name UninstallString -Value "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$uninstallPs`""
    Set-ItemProperty -Path $uninstallKey -Name QuietUninstallString -Value "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$uninstallPs`" -Quiet"
    Set-ItemProperty -Path $uninstallKey -Name NoModify -Value 1 -Type DWord
    Set-ItemProperty -Path $uninstallKey -Name NoRepair -Value 1 -Type DWord
    Set-ItemProperty -Path $uninstallKey -Name EstimatedSize -Value $sizeKb -Type DWord
    Say '  [4/4] Программа появилась в «Приложениях и возможностях»' 'Green'
}

Say ''
Say '  Готово. Проверьте установку:' 'Cyan'
Say "    `"$targetExe`" --version" 'White'
Say "    `"$targetExe`" info 68157cd455c34ca4a186b659469e78b3" 'White'
Say ''
Say '  Токен Sketchfab положите в .env рядом с exe:' 'Cyan'
Say "    $InstallDir\.env  ->  SKETCHFAB_API_TOKEN=ваш_токен" 'White'
Say ''
if (-not $SkipPath) {
    Say '  PATH обновится в новых окнах терминала (или перезапустите проводник).' 'DarkGray'
    Say "  В текущем окне: `$env:Path += `";$InstallDir`"" 'DarkGray'
    Say ''
}
Say "  Удалить: `"$InstallDir\uninstall.cmd`" или «Приложения и возможности»." 'DarkGray'
Say ''
