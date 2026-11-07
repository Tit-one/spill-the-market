@echo off
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo Installez uv ou suivez les instructions du README.
  pause
  exit /b 1
)
uv run spill-market serve --open
if errorlevel 1 pause
