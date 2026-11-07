"""跨平台小工具：开机自启（Windows 注册表）。"""
from __future__ import annotations

import os
import sys

try:  # winreg 只在 Windows 上存在
    import winreg  # type: ignore
except ImportError:  # pragma: no cover - 非 Windows 平台
    winreg = None  # type: ignore

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "DesktopPet"


def supported() -> bool:
    return winreg is not None


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    main_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    return f'"{sys.executable}" "{main_py}"'


def set_autostart(enabled: bool) -> tuple[bool, str]:
    """写入/删除 HKCU 启动项，返回 (是否成功, 提示文本)。"""
    if winreg is None:
        return False, "该功能仅在 Windows 上可用"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _launch_command())
                return True, "已设置为开机自启"
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
            return True, "已取消开机自启"
    except OSError as e:
        return False, f"设置失败：{e}"
