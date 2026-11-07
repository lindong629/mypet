"""运行时生成的小图标（避免依赖外部素材文件）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap

from . import config

_cache: dict[str, str] = {}


def arrow_png(color: str = "#A08D7B") -> str:
    """下拉框用的小三角，生成到数据目录并缓存。"""
    key = f"arrow{color}"
    if key in _cache:
        return _cache[key]

    path = config.data_dir() / f"ui_arrow_{color.lstrip('#')}.png"
    pm = QPixmap(24, 24)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    tri = QPainterPath()
    tri.moveTo(7, 9.5)
    tri.lineTo(17, 9.5)
    tri.lineTo(12, 15)
    tri.closeSubpath()
    p.drawPath(tri)
    p.end()
    pm.save(str(path))

    _cache[key] = path.as_posix()
    return _cache[key]
