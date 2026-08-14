@echo off
cd /d %~dp0
REM 优先使用项目自带虚拟环境 venv\Scripts\python.exe（按 README 创建）；
REM 否则回退到系统 PATH 中的 python。
if exist "venv\Scripts\python.exe" (
    set "PY=venv\Scripts\python.exe"
) else (
    set "PY=python"
)
echo 正在启动 DocRAG（使用 %PY%）...
%PY% app.py
pause
