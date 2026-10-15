@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  set PY=py -3
) else (
  set PY=python
)

%PY% -c "import requests, rich" >nul 2>&1
if errorlevel 1 (
  echo [INFO] Installing dependencies...
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
  )
)

%PY% cli.py %*

endlocal
