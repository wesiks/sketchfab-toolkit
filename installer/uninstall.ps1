<#
    Удаление sketchfab-toolkit, установленного install.ps1.

    Чистит PATH пользователя, ярлык в меню «Пуск», запись в «Приложениях и
    возможностях», затем удаляет папку установки (сама папка убирается отдельным
    процессом, потому что этот скрипт лежит внутри неё).
#>
[CmdletBinding()]
param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

$AppName = 'sketchfab-toolkit'
$InstallDir = $PSScriptRoot

function Say([string]$text, [string]$color = 'Gray') {
    if ($Quiet -and $color -ne 'Red') { return }
    Write-Host $text -ForegroundColor $color
}

function Remove-FromUserPath([string]$directory) {
    $key = 'HKCU:\Environment'
    if (-not (Test-Path $key)) { return $false }
    $raw = (Get-ItemProperty -Path $key -Name Path -ErrorAction SilentlyContinue).Path
    if ($null -eq $raw) { return $false }

    $parts = @([string]$raw -split ';' | Where-Object { $_ -ne '' })
    $kept = @($parts | Where-Object { $_.TrimEnd('\') -ine $directory.TrimEnd('\') })
    if ($kept.Count -eq $parts.Count) { return $false }

    Set-ItemProperty -Path $key -Name Path -Value ($kept -join ';') -Type ExpandString
    return $true
}

Say ''
Say '  sketchfab-toolkit — удаление' 'Cyan'
Say ''

if (Remove-FromUserPath $InstallDir) {
    Say '  [1/4] Путь убран из PATH пользователя' 'Green'
} else {
    Say '  [1/4] В PATH пользователя записи не было' 'DarkGray'
}

$link = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$AppName.lnk"
if (Test-Path $link) {
    Remove-Item -Path $link -Force -ErrorAction SilentlyContinue
    Say '  [2/4] Ярлык из меню «Пуск» удалён' 'Green'
} else {
    Say '  [2/4] Ярлыка не было' 'DarkGray'
}

$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppName"
if (Test-Path $uninstallKey) {
    Remove-Item -Path $uninstallKey -Recurse -Force -ErrorAction SilentlyContinue
    Say '  [3/4] Запись об установке удалена' 'Green'
} else {
    Say '  [3/4] Записи об установке не было' 'DarkGray'
}

Say '  [4/4] Удаляю папку установки...' 'Green'
# Папка не может удалить себя сама изнутри: отдаём это отдельному процессу с задержкой.
$cmd = "timeout /t 2 /nobreak >nul & rmdir /s /q `"$InstallDir`""
Start-Process -FilePath $env:ComSpec -ArgumentList '/c', $cmd -WindowStyle Hidden

Say ''
Say "  Готово. Папка $InstallDir будет удалена через пару секунд." 'Cyan'
Say ''
