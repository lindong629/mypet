@echo off
chcp 65001 >nul
title 桌面宠物 - 安装依赖
cd /d "%~dp0"

echo ================================================
echo   桌面宠物 · 安装运行环境
echo ================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 没有找到 python 命令。
    echo.
    echo 请先安装 Python 3.10 或更高版本：
    echo     https://www.python.org/downloads/
    echo 安装时请务必勾选 "Add python.exe to PATH"，然后重新运行本文件。
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo 正在创建虚拟环境 .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败。
        pause
        exit /b 1
    )
)

echo 正在升级 pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet

echo 正在安装 PySide6（约 100MB，请耐心等待）...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo 默认源安装失败，改用清华镜像重试 ...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo [错误] 安装失败，请检查网络后重试。
        pause
        exit /b 1
    )
)

echo.
echo ================================================
echo   安装完成！双击「启动.bat」就能看到它了。
echo ================================================
echo.
pause
