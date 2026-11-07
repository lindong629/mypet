"""互动道具：饭盆、毛线球、逗猫棒、洗澡盆、摸头的手。

全部画在 200x200 的逻辑坐标里（地面 y=180），和宠物共用一套缩放。
道具由 pet_window 的动作状态机驱动，k 表示动作进度 0..1。
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

CX = 100.0
GROUND = 180.0


def _pen(color: QColor, w: float) -> QPen:
    p = QPen(color, w)
    p.setCapStyle(Qt.RoundCap)
    p.setJoinStyle(Qt.RoundJoin)
    return p


def _rgba(c: QColor, a: int) -> QColor:
    out = QColor(c)
    out.setAlpha(a)
    return out


# ------------------------------------------------------------------ 饭盆
def draw_bowl(p: QPainter, k: float, food_color: QColor) -> None:
    """k: 0 满 → 1 吃完。"""
    cx = CX
    rim_y = 160.0
    w = 17.5

    # 盆身
    body = QPainterPath()
    body.moveTo(cx - w, rim_y)
    body.cubicTo(cx - w * 0.94, rim_y + 11, cx - w * 0.7, rim_y + 18, cx - w * 0.5, rim_y + 18)
    body.lineTo(cx + w * 0.5, rim_y + 18)
    body.cubicTo(cx + w * 0.7, rim_y + 18, cx + w * 0.94, rim_y + 11, cx + w, rim_y)
    body.closeSubpath()
    gr = QLinearGradient(0, rim_y, 0, rim_y + 18)
    gr.setColorAt(0.0, QColor("#F4F7FA"))
    gr.setColorAt(1.0, QColor("#C9D6E2"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(gr))
    p.drawPath(body)
    p.setPen(_pen(QColor("#A9BCCD"), 1.1))
    p.setBrush(Qt.NoBrush)
    p.drawPath(body)

    # 盆口
    rim = QRectF(cx - w, rim_y - 6, w * 2, 12)
    p.setPen(_pen(QColor("#A9BCCD"), 1.1))
    p.setBrush(QColor("#E8F0F7"))
    p.drawEllipse(rim)

    # 里面的食物
    if k < 0.94:
        fill = 1.0 - k
        fw = w * (0.52 + 0.34 * fill)
        fh = 6.0 * fill + 1.2
        mound = QPainterPath()
        mound.moveTo(cx - fw, rim_y + 1)
        mound.cubicTo(cx - fw * 0.8, rim_y - fh * 1.5,
                      cx + fw * 0.8, rim_y - fh * 1.5, cx + fw, rim_y + 1)
        mound.cubicTo(cx + fw * 0.6, rim_y + 3.4, cx - fw * 0.6, rim_y + 3.4,
                      cx - fw, rim_y + 1)
        mound.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(food_color)
        p.drawPath(mound)
        # 颗粒
        for i in range(5):
            fx = cx - fw * 0.7 + fw * 1.4 * (i / 4)
            fy = rim_y - 1.2 - (1.6 if i % 2 else 0)
            p.setBrush(_rgba(_shade(food_color, 0.18), 200))
            p.drawEllipse(QRectF(fx - 1.3, fy - 1.2, 2.6, 2.4))


# ------------------------------------------------------------------ 毛线球
def draw_yarn(p: QPainter, x: float, y: float, rot: float, scale: float = 1.0) -> None:
    r = 10.0 * scale
    p.save()
    p.translate(x, y)
    p.rotate(rot)
    # 球体
    g = QRadialGradient(QPointF(-r * 0.35, -r * 0.4), r * 1.5)
    g.setColorAt(0.0, QColor("#F2857F"))
    g.setColorAt(0.65, QColor("#D65552"))
    g.setColorAt(1.0, QColor("#9E3330"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QRectF(-r, -r, r * 2, r * 2))
    # 缠绕的线
    p.setPen(_pen(_rgba(QColor("#7E2725"), 90), 1.0))
    p.setBrush(Qt.NoBrush)
    for i in range(4):
        ang = i * math.pi / 4
        p.save()
        p.rotate(ang * 57.3)
        p.drawEllipse(QRectF(-r * 0.92, -r * 0.34, r * 1.84, r * 0.68))
        p.restore()
    p.setPen(_pen(_rgba(QColor("#FFD9D7"), 130), 1.0))
    p.drawArc(QRectF(-r * 0.7, -r * 0.78, r * 1.1, r * 0.9), 30 * 16, 110 * 16)
    p.restore()


def draw_yarn_trail(p: QPainter, x0: float, x1: float, y: float) -> None:
    """毛线球滚过留下的一段线。"""
    path = QPainterPath(QPointF(x0, y))
    path.cubicTo((x0 + x1) / 2, y + 5, (x0 + x1) / 2, y - 5, x1, y - 1)
    p.setPen(_pen(_rgba(QColor("#C24E4B"), 150), 1.2))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)


# ------------------------------------------------------------------ 逗猫棒
def draw_wand(p: QPainter, k: float, angle: float) -> None:
    """从右上角伸进来的逗猫棒：杆子斜插下来，羽毛吊在猫爪子前面晃。"""
    pivot = QPointF(198, 4)
    pole = QPointF(-80, 104)         # 杆子相对支点的偏移
    a = math.radians(angle)
    ex = pivot.x() + pole.x() * math.cos(a) - pole.y() * math.sin(a)
    ey = pivot.y() + pole.x() * math.sin(a) + pole.y() * math.cos(a)

    p.save()
    # 杆
    p.setPen(QPen(QColor("#C09462"), 3.4, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(pivot, QPointF(ex, ey))
    p.setPen(QPen(QColor("#F0E2C8"), 1.4, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(ex, ey), QPointF(ex, ey + 15))
    p.restore()

    fx, fy = ex, ey + 15
    # 羽毛
    p.save()
    p.translate(fx, fy)
    p.rotate(math.sin(k * 12) * 14)
    for i, (dx, dy, ln, wd) in enumerate(((-6, 2, 20, 6), (2, 0, 24, 6.5), (8, 4, 17, 5))):
        path = QPainterPath()
        path.moveTo(0, 0)
        path.cubicTo(dx * 0.4, dy - wd, dx + ln * 0.6, dy - wd - ln * 0.3,
                     dx + ln * 0.5, dy + ln * 0.25)
        path.cubicTo(dx, dy + wd * 0.5, -2, dy + 2, 0, 0)
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#E88A9A") if i != 1 else QColor("#F2B0BE"))
        p.drawPath(path)
    p.restore()
    # 小铃铛
    p.setPen(_pen(QColor("#B8862F"), 1.0))
    p.setBrush(QColor("#F2C14E"))
    p.drawEllipse(QRectF(fx - 3.4, fy + 5, 6.8, 6.8))


# ------------------------------------------------------------------ 洗澡
def draw_tub(p: QPainter, k: float) -> None:
    """洗澡盆：猫坐在里面，水面到腰，边缘挂着两只前爪。"""
    cx = CX
    top = 148.0
    half = 46.0

    # 盆身（上宽下窄的圆桶）
    tub = QPainterPath()
    tub.moveTo(cx - half, top - 4)
    tub.cubicTo(cx - half * 0.95, top + 18, cx - half * 0.74, top + 32,
                cx - half * 0.56, top + 32)
    tub.lineTo(cx + half * 0.56, top + 32)
    tub.cubicTo(cx + half * 0.74, top + 32, cx + half * 0.95, top + 18,
                cx + half, top - 4)
    tub.closeSubpath()
    gr = QLinearGradient(0, top, 0, top + 32)
    gr.setColorAt(0.0, QColor("#FBF4E6"))
    gr.setColorAt(0.55, QColor("#EFE0C6"))
    gr.setColorAt(1.0, QColor("#D3BE9C"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(gr))
    p.drawPath(tub)
    p.setPen(_pen(QColor("#C0AA8C"), 1.2))
    p.setBrush(Qt.NoBrush)
    p.drawPath(tub)

    # 盆口
    rim = QRectF(cx - half, top - 10, half * 2, 16)
    p.setPen(_pen(QColor("#C0AA8C"), 1.3))
    p.setBrush(QColor("#FDF8EE"))
    p.drawEllipse(rim)

    # 水面
    p.save()
    p.setClipPath(tub)
    p.setPen(Qt.NoPen)
    wg = QLinearGradient(0, top - 6, 0, top + 8)
    wg.setColorAt(0.0, QColor(158, 214, 236, 208))
    wg.setColorAt(1.0, QColor(96, 168, 204, 226))
    p.setBrush(QBrush(wg))
    p.drawEllipse(QRectF(cx - half * 0.92, top - 9, half * 1.84, 17))
    p.restore()

    # 泡沫
    p.setPen(Qt.NoPen)
    for i in range(11):
        fx = cx - half * 0.78 + i * (half * 1.56 / 10) + math.sin(k * 8 + i) * 1.6
        fy = top - 6 + math.sin(i * 2.1) * 2.4
        r = 3.0 + (i % 3) * 1.5
        p.setBrush(QColor(255, 255, 255, 208))
        p.drawEllipse(QRectF(fx - r, fy - r, r * 2, r * 2))
        p.setBrush(QColor(255, 255, 255, 120))
        p.drawEllipse(QRectF(fx - r * 0.5, fy - r * 0.72, r * 0.7, r * 0.7))

    # 挂在盆沿上的两只前爪
    for side in (-1, 1):
        px = cx + side * 17
        p.setPen(Qt.NoPen)
        pg = QLinearGradient(0, top - 8, 0, top + 4)
        pg.setColorAt(0.0, QColor("#FBF1E2"))
        pg.setColorAt(1.0, QColor("#E7D6BE"))
        p.setBrush(QBrush(pg))
        p.drawEllipse(QRectF(px - 8, top - 7, 16, 11))
        p.setPen(_pen(QColor("#C9B294"), 0.9))
        p.setBrush(Qt.NoBrush)
        for kk in (-2.6, 0.0, 2.6):
            p.drawLine(QPointF(px + kk, top - 4), QPointF(px + kk, top + 1))


def draw_sponge(p: QPainter, x: float, y: float, rot: float) -> None:
    p.save()
    p.translate(x, y)
    p.rotate(rot)
    p.setPen(_pen(QColor("#C9A86E"), 1.2))
    p.setBrush(QColor("#F5D98F"))
    p.drawRoundedRect(QRectF(-9, -6, 18, 12), 3.5, 3.5)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#E8C878"))
    for i in range(4):
        p.drawEllipse(QRectF(-6 + i * 3.4, -3 + (i % 2) * 3, 1.6, 1.6))
    p.restore()


# ------------------------------------------------------------------ 摸头的手
def draw_hand(p: QPainter, k: float, cx: float, y: float) -> None:
    """从右上角伸下来的手，掌心扣在猫头顶上。k: 0 远处 → 1 贴住。"""
    if k <= 0.02:
        return
    drop = (1.0 - k) * 26.0
    skin = QColor("#F3C9AC")
    skin_dark = QColor("#DCA985")
    skin_light = QColor("#FBE0CC")
    outline = QColor(150, 104, 78, 190)

    p.save()
    p.translate(cx + 9, y + 18 + drop)
    p.rotate(-20 + 4 * k)
    p.scale(0.92, 0.92)

    # 袖子（往画面外延伸，不要画成一个小方块）
    p.setPen(Qt.NoPen)
    sleeve = QLinearGradient(0, -46, 0, -2)
    sleeve.setColorAt(0.0, QColor("#8FB2D2"))
    sleeve.setColorAt(1.0, QColor("#A8C6E0"))
    p.setBrush(QBrush(sleeve))
    p.drawRoundedRect(QRectF(-19, -48, 38, 44), 9, 9)
    p.setBrush(QColor("#7EA2C4"))
    p.drawRoundedRect(QRectF(-20, -8, 40, 8), 4, 4)

    # 手背
    palm = QPainterPath()
    palm.moveTo(-16, 2)
    palm.cubicTo(-17, -8, -9, -13, 1, -13)
    palm.cubicTo(12, -13, 18, -7, 17, 3)
    palm.cubicTo(16, 11, 7, 15, -2, 14)
    palm.cubicTo(-10, 13, -15, 10, -16, 2)
    palm.closeSubpath()
    pg = QLinearGradient(-16, -12, 16, 14)
    pg.setColorAt(0.0, skin_light)
    pg.setColorAt(0.55, skin)
    pg.setColorAt(1.0, skin_dark)
    p.setPen(_pen(outline, 1.0))
    p.setBrush(QBrush(pg))
    p.drawPath(palm)

    # 手指：向下弯，指尖落在猫的额头上
    for i, (dx, ln, wd, ang) in enumerate(((-11.0, 19, 6.6, -6.0), (-3.6, 22, 7.0, -2.0),
                                           (4.0, 21, 6.8, 3.0), (11.2, 17, 6.0, 9.0))):
        p.save()
        p.translate(dx, 5)
        p.rotate(ang)
        finger = QPainterPath()
        finger.addRoundedRect(QRectF(-wd / 2, 0, wd, ln), wd / 2, wd / 2)
        fg = QLinearGradient(-wd / 2, 0, wd / 2, 0)
        fg.setColorAt(0.0, skin_light)
        fg.setColorAt(0.6, skin)
        fg.setColorAt(1.0, skin_dark)
        p.setPen(_pen(outline, 0.9))
        p.setBrush(QBrush(fg))
        p.drawPath(finger)
        # 指关节的褶皱
        p.setPen(_pen(_rgba(skin_dark, 120), 0.8))
        p.drawLine(QPointF(-wd * 0.30, ln * 0.52), QPointF(wd * 0.30, ln * 0.5))
        p.restore()

    # 拇指
    p.save()
    p.translate(-15.5, 4)
    p.rotate(38)
    p.setPen(_pen(outline, 0.9))
    p.setBrush(skin)
    p.drawRoundedRect(QRectF(-3.2, 0, 6.4, 13), 3.2, 3.2)
    p.restore()
    p.restore()


# ------------------------------------------------------------------ 小工具
def _shade(c: QColor, k: float) -> QColor:
    h, s, v, a = c.getHsvF()
    v = max(0.0, min(1.0, v * (1 + k)))
    return QColor.fromHsvF(max(0.0, h), s, v, a)


# ------------------------------------------------------------------ 统一入口
def draw_props(p: QPainter, look, palette: dict) -> None:
    """按 look.prop 画出当前互动道具。"""
    kind = getattr(look, "prop", "")
    if not kind:
        return
    k = max(0.0, min(1.0, getattr(look, "prop_t", 0.0)))
    if kind == "bowl":
        color = (getattr(look, "extra", {}) or {}).get("food_color") or "#E8A15C"
        draw_bowl(p, k, QColor(color))
    elif kind == "yarn":
        x = 100 + (getattr(look, "extra", {}) or {}).get("yarn_x", 0.0)
        draw_yarn_trail(p, 118, x, 172)
        draw_yarn(p, x, 171, k * 720, 1.0)
    elif kind == "wand":
        draw_wand(p, k, (getattr(look, "extra", {}) or {}).get("wand_angle", 0.0))
    elif kind == "tub":
        draw_tub(p, k)
        sx = 100 + math.sin(k * 10) * 20
        draw_sponge(p, sx, 150 + math.cos(k * 9) * 6, math.sin(k * 12) * 20)
    elif kind == "hand":
        draw_hand(p, k, 100.0, 16.0)
