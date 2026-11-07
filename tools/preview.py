"""开发用：把各种姿态、毛色、表情渲染成对照图，方便检查画得对不对。

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

CELL = 250
LABEL_H = 26


def render_sheet(rows: list[tuple[str, list[tuple[str, Look, dict]]]], out_name: str) -> str:
    cols = max(len(r[1]) for r in rows)
    w = CELL * cols
    h = (CELL + LABEL_H) * len(rows) + 44
    pm = QPixmap(w, h)
    pm.fill(QColor("#EDE7DE"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    f = QFont()
    f.setFamilies(config.app_font_family())
    f.setPixelSize(13)
    fb = QFont(f)
    fb.setBold(True)
    fb.setPixelSize(15)

    y = 0
    for title, items in rows:
        p.setFont(fb)
        p.setPen(QColor("#5A4A3F"))
        p.drawText(QRectF(16, y + 6, w - 32, 32), Qt.AlignLeft | Qt.AlignVCenter, title)
        y += 44
        for i, (label, look, palette) in enumerate(items):
            x = i * CELL
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#FFFFFF"))
            p.drawRoundedRect(QRectF(x + 8, y + 4, CELL - 16, CELL - 8), 14, 14)
            painter.draw_pet(p, QRectF(x + 12, y + 10, CELL - 24, CELL - 20), look, palette)
            p.setFont(f)
            p.setPen(QColor("#6B5A4C"))
            p.drawText(QRectF(x, y + CELL - 8, CELL, LABEL_H), Qt.AlignCenter, label)
        y += CELL + LABEL_H

    p.end()
    out_dir = os.path.join(ROOT, "preview")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, out_name)
    pm.save(out)
    print("saved:", out)
    return out


def main() -> None:
    app = QApplication(sys.argv)  # noqa: F841
    orange = config.PALETTES["橘白猫"]

    poses = [
        ("默认坐姿", Look(stage=3, t=1.0)),
        ("走路", Look(stage=3, walk=1.0, walk_phase=0.9, t=1.0)),
        ("吃饭", Look(stage=3, emotion="eat", mouth=0.6, head_down=0.9,
                      prop="bowl", prop_t=0.4, t=1.0)),
        ("睡觉（趴卧）", Look(stage=3, emotion="sleepy", sleeping=True, pose="loaf",
                            t=1.0)),
        ("洗澡", Look(stage=3, emotion="dizzy", washing=True, wet=0.8, squash=0.15,
                      prop="tub", prop_t=0.5, t=1.0)),
        ("被抱起", Look(stage=3, emotion="scared", pose="dangle", ear_back=0.7,
                        leg_l=0.5, leg_r=0.4, tail_curl=0.8, t=1.0)),
    ]
    render_sheet([("真实感检查 · 姿态", [(a, b, orange) for a, b in poses])], "poses.png")

    palette_cells = []
    notes = {"橘白猫": "虎斑", "狸花猫": "虎斑", "蓝灰英短": "纯色",
             "奶牛猫": "奶牛", "布偶猫": "重点色"}
    for name, pal in config.PALETTES.items():
        palette_cells.append((f"{name}（{notes[name]}）", Look(stage=3, t=1.0), pal))
    render_sheet([("毛色", palette_cells)], "palettes.png")

    emo = [
        ("普通", Look(stage=3, t=1.0)),
        ("开心", Look(stage=3, emotion="happy", purr=1.0, t=1.0)),
        ("亲密（爱心高光）", Look(stage=3, emotion="love", purr=1.0, t=1.0)),
        ("难过", Look(stage=3, emotion="sad", t=1.0)),
        ("生气", Look(stage=3, emotion="angry", t=1.0)),
        ("被摸头", Look(stage=3, emotion="happy", purr=1.0, head_dy=3.0,
                        ear_back=0.35, hand=1.0, t=1.0)),
    ]
    render_sheet([("表情", [(a, b, orange) for a, b in emo])], "faces.png")

    stages = [
        ("蛋（裂开）", Look(stage=0, egg_crack=2, t=0.3)),
        ("幼崽", Look(stage=1, t=1.0)),
        ("少年", Look(stage=2, t=1.0)),
        ("成年", Look(stage=3, t=1.0)),
        ("幼崽·开心", Look(stage=1, emotion="happy", purr=1.0, t=1.0)),
    ]
    render_sheet([("成长阶段", [(a, b, orange) for a, b in stages])], "stages.png")


if __name__ == "__main__":
    main()
