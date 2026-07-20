@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
  echo No se encontro Python en el PATH.
  echo Instalalo desde https://python.org y marca "Add Python to PATH".
  pause
  exit /b
)
python "run.py"
