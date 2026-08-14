@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d %~dp0
REM Use project venv if available; otherwise fallback to system python.
if exist "venv\Scripts\python.exe" (
    set "PY=venv\Scripts\python.exe"
) else (
    set "PY=python"
)
echo Starting DocRAG (using %PY%)...
%PY% app.py
pause
