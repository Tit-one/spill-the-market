@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -NonInteractive -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/v1/bootstrap' -TimeoutSec 2; if ($r.capabilities -contains 'adaptive-media') { exit 0 } } catch {}; exit 1" >nul 2>nul
if not errorlevel 1 (
  start "" "http://127.0.0.1:8765"
  exit /b 0
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m spill_market.cli serve --open
  if errorlevel 1 pause
  exit /b
)
where uv >nul 2>nul
if errorlevel 1 (
  echo Installez uv ou suivez les instructions du README.
  pause
  exit /b 1
)
uv run spill-market serve --open
if errorlevel 1 pause
