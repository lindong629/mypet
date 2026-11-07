"""开发用：把每个互动动作渲染成一帧，检查姿态和道具是否对得上。

    python tools/actions.py
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

from pet import config, painter, props  # noqa: E402
from pet.painter import Look  # noqa: E402

CELL = 250
LABEL_H = 26
COLS = 4


def sheet(items: list[tuple[str, Look]], palette: dict, out_name: str) -> str:
    rows = (len(items) + COLS - 1) // COLS
    w = CELL * COLS
    h = (CELL + LABEL_H) * rows + 16
    pm = QPixmap(w, h)
    pm.fill(QColor("#EFE9E0"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    f = QFont()
    f.setFamilies(config.app_font_family())
    f.setPixelSize(13)

    for i, (label, look) in enumerate(items):
        x = (i % COLS) * CELL
        y = (i // COLS) * (CELL + LABEL_H) + 8
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#FFFFFF"))
        p.drawRoundedRect(QRectF(x + 8, y + 4, CELL - 16, CELL - 8), 14, 14)
        rect = QRectF(x + 12, y + 10, CELL - 24, CELL - 20)
        painter.draw_pet(p, rect, look, palette)
        if look.prop:
            p.save()
            p.translate(rect.x(), rect.y())
            p.scale(rect.width() / 200.0, rect.height() / 200.0)
            props.draw_props(p, look, palette)
            p.restore()
        p.setFont(f)
        p.setPen(QColor("#6B5A4C"))
        p.drawText(QRectF(x, y + CELL - 10, CELL, LABEL_H), Qt.AlignCenter, label)

    p.end()
    out_dir = os.path.join(ROOT, "preview")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, out_name)
    pm.save(out)
    print("saved:", out)
    return out


def main() -> None:
    app = QApplication(sys.argv)  # noqa: F841
    pal = config.PALETTES["橘白猫"]

    items = [
        ("摸头", Look(stage=3, emotion="happy", hand=1.0, head_dy=3.2, head_down=0.16,
                     ear_back=0.2, purr=1.0, prop="hand", prop_t=1.0, t=1.0)),
        ("吃东西", Look(stage=3, emotion="eat", pose="eat", head_down=0.18,
                      mouth=0.45, prop="bowl", prop_t=0.45, t=1.0,
                      extra={"food_color": "#E8A15C"})),
        ("玩毛线球·伏低", Look(stage=3, emotion="happy", pose="crouch", head_down=0.55,
                            tail_up=1.0, prop="yarn", prop_t=0.1, t=1.0,
                            extra={"yarn_x": 26})),
        ("玩毛线球·扑", Look(stage=3, emotion="happy", jump=0.6, paw_fwd=0.9,
                          leg_l=0.7, leg_r=0.5, head_down=0.3, prop="yarn",
                          prop_t=0.4, t=1.0, extra={"yarn_x": -18})),
        ("逗猫棒", Look(stage=3, emotion="happy", prop="wand", prop_t=0.4,
                      paw_fwd=0.85, head_down=0.22, head_dx=4, look_y=-0.4,
                      extra={"wand_angle": -8.0}, t=1.0)),
        ("洗澡", Look(stage=3, emotion="dizzy", washing=True, wet=1.0, squash=0.1,
                    lean=0.4, head_down=0.3, prop="tub", prop_t=0.55, t=1.0)),
        ("睡觉", Look(stage=3, emotion="sleepy", sleeping=True, pose="loaf",
                    tail_curl=0.6, breath=0.4, t=1.0)),
        ("被拎起", Look(stage=3, emotion="scared", pose="dangle", ear_back=0.85,
                      tail_curl=0.9, leg_l=0.45, leg_r=0.55, t=1.0)),
        ("走路", Look(stage=3, walk=1.0, walk_phase=1.2, bob=1.4, lean=0.4, t=1.0)),
        ("舔毛", Look(stage=3, emotion="happy", leg_r=1.0, head_down=0.22,
                    head_tilt=0.5, tongue=1.0, mouth=0.12, t=1.0)),
        ("打哈欠", Look(stage=3, emotion="sleepy", mouth=1.0, eye_open=0.15,
                     ear_back=0.3, t=1.0)),
        ("伸懒腰", Look(stage=3, emotion="sleepy", pose="stretch", head_down=0.35,
                     tail_up=0.8, paw_fwd=0.5, t=1.0)),
    ]
    sheet(items, pal, "actions.png")


if __name__ == "__main__":
    main()
