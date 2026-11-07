@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo 还没有安装运行环境。
    echo 请先双击「安装依赖.bat」，完成后再运行本文件。
    echo.
    pause
    exit /b 1
)

start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py"
exit /b 0
