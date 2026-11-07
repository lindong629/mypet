"""开发用：渲染 1024x1024 的应用图标，并生成 macOS .icns / Windows .ico。

    python tools/make_icon.py
"""
from __future__ import annotations

import os
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pet import config, painter  # noqa: E402
from pet.painter import Look  # noqa: E402

SIZE = 1024
ASSETS = os.path.join(ROOT, "assets")


def render() -> QPixmap:
    pm = QPixmap(SIZE, SIZE)
    pm.fill(Qt.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    # 圆角底板（macOS 图标规范：内容留出约 10% 边距）
    pad = int(SIZE * 0.08)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#FFF7EC"))
    p.drawRoundedRect(QRectF(pad, pad, SIZE - pad * 2, SIZE - pad * 2),
                      (SIZE - pad * 2) * 0.22, (SIZE - pad * 2) * 0.22)

    # 宠物本体，留出内边距
    inner = pad + int(SIZE * 0.055)
    look = Look(stage=2, emotion="happy", breath=-0.3, tail=-0.5, t=2.0)
    painter.draw_pet(p, QRectF(inner, inner, SIZE - inner * 2, SIZE - inner * 2),
                     look, config.PALETTES["奶油橘"])
    p.end()
    return pm


def make_icns(pm: QPixmap) -> str | None:
    if sys.platform != "darwin":
        return None  # iconutil 只有 macOS 上有
    iconset = os.path.join(ASSETS, "DesktopPet.iconset")
    os.makedirs(iconset, exist_ok=True)
    for size in (16, 32, 64, 128, 256, 512, 1024):
        for scale in (1, 2):
            px = size * scale
            if px > 1024:
                continue
            name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
            scaled = pm.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            scaled.save(os.path.join(iconset, name), "PNG")
    out = os.path.join(ASSETS, "DesktopPet.icns")
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", out], check=True)
    return out


def make_ico(pm: QPixmap) -> str | None:
    try:
        from PIL import Image  # 只有生成 .ico 时才需要
    except ImportError:
        return None
    tmp = os.path.join(ASSETS, "_icon_big.png")
    pm.save(tmp, "PNG")
    out = os.path.join(ASSETS, "DesktopPet.ico")
    img = Image.open(tmp)
    img.save(out, format="ICO",
             sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    os.remove(tmp)
    return out


def main() -> None:
    app = QApplication(sys.argv)  # noqa: F841
    os.makedirs(ASSETS, exist_ok=True)
    pm = render()
    base = os.path.join(ASSETS, "icon.png")
    pm.save(base, "PNG")
    print("png :", base)
    print("icns:", make_icns(pm) or "跳过（非 macOS）")
    ico = make_ico(pm)
    print("ico :", ico or "跳过（未安装 Pillow）")


if __name__ == "__main__":
    main()
