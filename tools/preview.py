"""开发用：把各种姿态渲染成一张对照图，方便检查画得对不对。

    python tools/preview.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pet import config, painter  # noqa: E402
from pet.painter import Look  # noqa: E402

CELL = 220
COLS = 4
ROWS = 2
LABEL_H = 26


def main() -> None:
    app = QApplication(sys.argv)  # noqa: F841

    palette = config.PALETTES["奶油橘"]
    poses = [
        ("蛋（裂了）", Look(stage=0, egg_crack=2, t=0.3)),
        ("幼崽 · 普通", Look(stage=1, emotion="normal", breath=0.6, tail=0.4, t=1.0)),
        ("幼崽 · 开心", Look(stage=1, emotion="happy", breath=-0.4, tail=-0.6, t=2.0)),
        ("少年 · 爱心", Look(stage=2, emotion="love", breath=0.2, tail=0.8, t=3.0)),
        ("成年 · 开心", Look(stage=3, emotion="happy", breath=0.4, tail=-0.3, t=4.0)),
        ("睡觉", Look(stage=2, emotion="sleepy", sleeping=True, breath=0.9, tail=0.0, t=5.0)),
        ("洗澡", Look(stage=1, emotion="dizzy", washing=True, lean=0.3, t=6.0)),
        ("吃东西", Look(stage=2, emotion="eat", mouth=0.8, eating=True, t=7.0)),
    ]

    w = CELL * COLS
    h = (CELL + LABEL_H) * ROWS
    pm = QPixmap(w, h)
    pm.fill(QColor("#E8EEF6"))

    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    f = QFont()
    f.setFamilies(config.app_font_family())
    f.setPixelSize(13)

    for i, (label, look) in enumerate(poses):
        col = i % COLS
        row = i // COLS
        x = col * CELL
        y = row * (CELL + LABEL_H)
        # 卡片底
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#FFFFFF"))
        p.drawRoundedRect(QRectF(x + 8, y + 8, CELL - 16, CELL - 8), 12, 12)
        painter.draw_pet(p, QRectF(x + 10, y + 12, CELL - 20, CELL - 20), look, palette)
        p.setFont(f)
        p.setPen(QColor("#5A4A3F"))
        p.drawText(QRectF(x, y + CELL, CELL, LABEL_H), Qt.AlignCenter, label)

    p.end()

    out_dir = os.path.join(ROOT, "preview")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "poses.png")
    pm.save(out)
    print("saved:", out)


if __name__ == "__main__":
    main()
