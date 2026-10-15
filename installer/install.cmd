@echo off
rem ASCII only: cmd.exe parses batch files in the OEM codepage, so Russian text
rem belongs to install.ps1 (UTF-8 with BOM) and not here.
chcp 65001 > nul
setlocal
rem SKETCHFAB_TOOLKIT_NO_PAUSE=1 disables the final pause (used by automated tests)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set CODE=%ERRORLEVEL%
if not "%CODE%"=="0" (
  echo.
  echo [ERROR] Installation failed with exit code %CODE%.
  if not defined SKETCHFAB_TOOLKIT_NO_PAUSE pause
  exit /b %CODE%
)
echo.
if not defined SKETCHFAB_TOOLKIT_NO_PAUSE pause
exit /b 0
