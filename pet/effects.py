"""粒子特效：爱心、Zzz、星星、气泡、碎屑。

坐标与宠物一致（200x200 逻辑空间，脚底 y=180）。
"""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen


class Effects:
    def __init__(self) -> None:
        self.items: list[dict] = []

    # ---------------------------------------------------------------- 生成
    def _add(self, **kw) -> None:
        base = {
            "kind": "heart", "x": 100.0, "y": 140.0,
            "vx": 0.0, "vy": -22.0, "life": 0.0, "ttl": 1.4,
            "size": 6.0, "color": QColor("#FF7E9B"), "rot": 0.0,
        }
        base.update(kw)
        self.items.append(base)

    def hearts(self, n: int = 3, x: float = 100.0, y: float = 90.0) -> None:
        for _ in range(n):
            self._add(kind="heart", x=x + random.uniform(-26, 26), y=y + random.uniform(-6, 10),
                      vx=random.uniform(-8, 8), vy=random.uniform(-40, -26),
                      ttl=random.uniform(1.2, 1.9), size=random.uniform(4.5, 7.5),
                      color=QColor("#FF7E9B"))

    def hearts_big(self, x: float = 100.0, y: float = 90.0) -> None:
        for _ in range(9):
            self._add(kind="heart", x=x + random.uniform(-34, 34), y=y + random.uniform(-14, 14),
                      vx=random.uniform(-16, 16), vy=random.uniform(-58, -34),
                      ttl=random.uniform(1.4, 2.2), size=random.uniform(4.0, 8.5))

    def zzz(self) -> None:
        self._add(kind="zzz", x=132 + random.uniform(-6, 6), y=110,
                  vx=9, vy=-16, ttl=2.6, size=random.uniform(9, 14),
                  color=QColor(120, 140, 180, 220))

    def sparkles(self, n: int = 12) -> None:
        colors = ["#FFD86B", "#FFB3C8", "#9BE0C8", "#B9C8F5"]
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            speed = random.uniform(40, 110)
            self._add(kind="sparkle", x=100, y=110,
                      vx=math.cos(ang) * speed, vy=math.sin(ang) * speed - 20,
                      ttl=random.uniform(0.8, 1.5), size=random.uniform(4, 9),
                      color=QColor(random.choice(colors)), rot=random.uniform(0, 90))

    def bubbles(self, n: int = 14) -> None:
        for _ in range(n):
            self._add(kind="bubble", x=random.uniform(52, 148), y=random.uniform(70, 176),
                      vx=random.uniform(-10, 10), vy=random.uniform(-52, -20),
                      ttl=random.uniform(0.9, 1.8), size=random.uniform(3, 8),
                      color=QColor(255, 255, 255, 200))

    def crumbs(self, n: int = 6) -> None:
        for _ in range(n):
            self._add(kind="crumb", x=100 + random.uniform(-14, 14), y=112,
                      vx=random.uniform(-30, 30), vy=random.uniform(-10, 20),
                      ttl=random.uniform(0.6, 1.1), size=random.uniform(2, 3.6),
                      color=QColor("#E2B07A"))

    def drops(self, n: int = 3) -> None:
        for _ in range(n):
            self._add(kind="drop", x=random.uniform(70, 130), y=random.uniform(120, 172),
                      vx=random.uniform(-26, 26), vy=random.uniform(-46, -10),
                      ttl=random.uniform(0.5, 0.9), size=random.uniform(1.6, 2.8),
                      color=QColor(150, 208, 238, 225))

    def dust(self, n: int = 6) -> None:
        for _ in range(n):
            self._add(kind="dust", x=100 + random.uniform(-26, 26), y=175,
                      vx=random.uniform(-34, 34), vy=random.uniform(-18, -4),
                      ttl=random.uniform(0.5, 0.9), size=random.uniform(2.5, 5.0),
                      color=QColor(206, 196, 180, 170))

    def crumb_at(self, x: float, y: float, color: QColor) -> None:
        self._add(kind="crumb", x=x, y=y, vx=random.uniform(-18, 18),
                  vy=random.uniform(-16, 2), ttl=random.uniform(0.4, 0.8),
                  size=random.uniform(1.3, 2.2), color=color)

    def shake_sparkles(self, n: int = 8) -> None:
        for _ in range(n):
            ang = random.uniform(-math.pi, 0)
            self._add(kind="sparkle", x=100 + random.uniform(-30, 30),
                      y=random.uniform(110, 160),
                      vx=math.cos(ang) * random.uniform(30, 70),
                      vy=math.sin(ang) * random.uniform(20, 50),
                      ttl=random.uniform(0.5, 0.9), size=random.uniform(2.5, 5.5),
                      color=QColor(random.choice(["#BFE3F5", "#FFFFFF", "#D8F0FA"])),
                      rot=random.uniform(0, 90))

    def sweat(self) -> None:
        self._add(kind="bubble", x=140, y=76, vx=6, vy=6, ttl=1.0, size=5.5,
                  color=QColor(160, 210, 240, 220))

    def clear(self) -> None:
        self.items.clear()

    # ---------------------------------------------------------------- 更新
    def update(self, dt: float) -> None:
        alive = []
        for it in self.items:
            it["life"] += dt
            if it["life"] >= it["ttl"]:
                continue
            gravity = 120 if it["kind"] == "drop" else (34 if it["kind"] == "crumb" else -4)
            it["vy"] += gravity * dt
            it["x"] += it["vx"] * dt
            it["y"] += it["vy"] * dt
            alive.append(it)
        self.items = alive

    # ---------------------------------------------------------------- 绘制
    def draw(self, p: QPainter) -> None:
        for it in self.items:
            k = it["life"] / it["ttl"]
            alpha = max(0.0, min(1.0, 1.0 - k * k))
            s = it["size"]
            p.save()
            p.translate(it["x"], it["y"])
            kind = it["kind"]
            if kind == "heart":
                p.scale(1 + k * 0.25, 1 + k * 0.25)
                col = QColor(it["color"])
                col.setAlphaF(alpha)
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawPath(_heart(s))
            elif kind == "zzz":
                col = QColor(it["color"])
                col.setAlphaF(alpha * 0.9)
                f = QFont("Segoe UI")
                f.setPixelSize(int(s))
                f.setBold(True)
                p.setFont(f)
                p.setPen(QPen(col))
                p.drawText(QRectF(-12, -s, 24, s * 1.4), Qt.AlignCenter, "Z")
            elif kind == "sparkle":
                col = QColor(it["color"])
                col.setAlphaF(alpha)
                p.rotate(it["rot"] + k * 120)
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawPath(_star(s))
            elif kind == "bubble":
                col = QColor(it["color"])
                col.setAlphaF(alpha * 0.85)
                p.setPen(QPen(col, 1.6))
                p.setBrush(QColor(255, 255, 255, int(70 * alpha)))
                p.drawEllipse(QRectF(-s, -s, s * 2, s * 2))
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, int(200 * alpha)))
                p.drawEllipse(QRectF(-s * 0.55, -s * 0.6, s * 0.4, s * 0.4))
            elif kind == "drop":
                col = QColor(it["color"])
                col.setAlphaF(alpha * 0.9)
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.save()
                p.rotate(14)
                p.drawEllipse(QRectF(-s * 0.55, -s, s * 1.1, s * 2.0))
                p.restore()
            elif kind == "dust":
                col = QColor(it["color"])
                col.setAlphaF(alpha * 0.55)
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawEllipse(QRectF(-s, -s * 0.8, s * 2, s * 1.6))
            elif kind == "crumb":
                col = QColor(it["color"])
                col.setAlphaF(alpha)
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawEllipse(QRectF(-s, -s, s * 2, s * 2))
            p.restore()


def _heart(s: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(0, s * 0.8)
    path.cubicTo(-s * 1.5, -s * 0.25, -s * 0.6, -s * 1.15, 0, -s * 0.35)
    path.cubicTo(s * 0.6, -s * 1.15, s * 1.5, -s * 0.25, 0, s * 0.8)
    path.closeSubpath()
    return path


def _star(s: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(0, -s)
    path.quadTo(0, 0, s, 0)
    path.quadTo(0, 0, 0, s)
    path.quadTo(0, 0, -s, 0)
    path.quadTo(0, 0, 0, -s)
    path.closeSubpath()
    return path
