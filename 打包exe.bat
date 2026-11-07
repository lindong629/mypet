@echo off
chcp 65001 >nul
title 桌面宠物 - 打包成 EXE
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo 请先运行「安装依赖.bat」。
    pause
    exit /b 1
)

echo 正在安装打包工具 PyInstaller ...
".venv\Scripts\python.exe" -m pip install pyinstaller --quiet

echo.
echo 正在打包（第一次约 1-3 分钟，请别关窗口）...
echo.

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name DesktopPet ^
    --exclude-module PySide6.QtWebEngineCore ^
    --exclude-module PySide6.QtWebEngineWidgets ^
    --exclude-module PySide6.QtQuick ^
    --exclude-module PySide6.QtQuick3D ^
    --exclude-module PySide6.QtQml ^
    --exclude-module PySide6.Qt3DCore ^
    --exclude-module PySide6.QtMultimedia ^
    --exclude-module PySide6.QtCharts ^
    --exclude-module tkinter ^
    main.py

echo.
if exist "dist\DesktopPet.exe" (
    echo ================================================
    echo   打包完成：dist\DesktopPet.exe
    echo   这个 exe 可以单独拷到别的 Windows 电脑运行
    echo ================================================
    start "" "dist"
) else (
    echo 打包失败，请把上面的报错信息保存下来。
)
echo.
pause
