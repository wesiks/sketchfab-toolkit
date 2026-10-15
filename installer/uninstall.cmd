@echo off
rem ASCII only: cmd.exe parses batch files in the OEM codepage.
chcp 65001 > nul
setlocal
rem SKETCHFAB_TOOLKIT_NO_PAUSE=1 disables the final pause (used by automated tests)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1" %*
echo.
if not defined SKETCHFAB_TOOLKIT_NO_PAUSE pause
exit /b 0
