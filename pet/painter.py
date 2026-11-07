"""宠物外观绘制：全部用 QPainter 矢量绘制，无需外部图片素材。

逻辑坐标系固定为 200x200，脚底在 y=180，绘制时按目标矩形等比缩放。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

INK = QColor("#4A3B34")
WHITE = QColor("#FFFFFF")

CANVAS = 200.0
FEET_Y = 180.0


@dataclass
class Look:
    """一帧的视觉状态，由动画系统喂给绘制函数。"""

    t: float = 0.0
    emotion: str = "normal"      # normal / happy / love / sad / sleepy / angry / eat / dizzy
    stage: int = 1               # 0 蛋, 1 幼崽, 2 少年, 3 成年
    breath: float = 0.0          # -1..1
    blink: float = 0.0           # 0 睁眼 .. 1 闭眼
    mouth: float = 0.0           # 0 闭嘴 .. 1 张嘴
    lean: float = 0.0            # -1..1 身体倾斜
    bob: float = 0.0             # 上下浮动像素
    tail: float = 0.0            # -1..1 尾巴摆动
    look_x: float = 0.0          # -1..1 眼珠左右
    look_y: float = 0.0
    sleeping: bool = False
    egg_crack: int = 0
    washing: bool = False
    eating: bool = False
    jump: float = 0.0            # 0..1 跳起高度比例
    squash: float = 0.0
    extra: dict = field(default_factory=dict)


# ------------------------------------------------------------------ 小工具
def _pen(color: QColor, width: float) -> QPen:
    p = QPen(color, width)
    p.setCapStyle(Qt.RoundCap)
    p.setJoinStyle(Qt.RoundJoin)
    return p


def _ell(p: QPainter, cx: float, cy: float, rx: float, ry: float,
         fill: QColor | None = None, outline: QColor | None = None, w: float = 2.6):
    rect = QRectF(cx - rx, cy - ry, rx * 2, ry * 2)
    if fill is not None:
        p.setBrush(QBrush(fill))
    else:
        p.setBrush(Qt.NoBrush)
    p.setPen(_pen(outline, w) if outline is not None else Qt.NoPen)
    p.drawEllipse(rect)


def _stroke_path(p: QPainter, path: QPainterPath, color: QColor, w: float):
    p.setBrush(Qt.NoBrush)
    p.setPen(_pen(color, w))
    p.drawPath(path)


def _heart_path(cx: float, cy: float, s: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(cx, cy + s * 0.75)
    path.cubicTo(cx - s * 1.5, cy - s * 0.25, cx - s * 0.55, cy - s * 1.15, cx, cy - s * 0.35)
    path.cubicTo(cx + s * 0.55, cy - s * 1.15, cx + s * 1.5, cy - s * 0.25, cx, cy + s * 0.75)
    path.closeSubpath()
    return path


# ------------------------------------------------------------------ 主体
def draw_pet(p: QPainter, rect: QRectF, look: Look, palette: dict) -> None:
    """把宠物画到 rect（设备坐标）里。"""
    if rect.width() <= 1 or rect.height() <= 1:
        return

    body = QColor(palette["body"])
    dark = QColor(palette["dark"])
    belly = QColor(palette["belly"])
    ear = QColor(palette["ear"])
    blush = QColor(palette["blush"])
    accent = QColor(palette["accent"])

    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.translate(rect.x(), rect.y())
    p.scale(rect.width() / CANVAS, rect.height() / CANVAS)

    cx = 100.0

    # 影子（不随呼吸/跳跃变化太多）
    shadow_scale = 1.0 - 0.25 * look.jump
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(60, 45, 40, int(46 * (1 - 0.4 * look.jump))))
    p.drawEllipse(QRectF(cx - 44 * shadow_scale, FEET_Y - 6,
                         88 * shadow_scale, 14 * shadow_scale))

    # 整体轻微倾斜 + 呼吸 + 跳跃
    p.save()
    p.translate(cx, FEET_Y)
    p.rotate(look.lean * 3.0)
    p.translate(-cx, -FEET_Y)
    p.translate(0, -look.bob - look.jump * 16)

    b = look.breath
    p.translate(cx, FEET_Y)
    p.scale(1 + 0.008 * b * (1 - 0.5 * look.squash), 1 + 0.018 * b * (1 + look.squash))
    p.translate(-cx, -FEET_Y)

    if look.stage == 0:
        _draw_egg(p, look, belly, dark, accent)
        p.restore()
        p.restore()
        return

    _draw_cat(p, look, body, dark, belly, ear, blush, accent, cx)
    p.restore()
    p.restore()


def _draw_cat(p: QPainter, look: Look, body: QColor, dark: QColor, belly: QColor,
              ear: QColor, blush: QColor, accent: QColor, cx: float) -> None:
    # ---- 尾巴
    tail = look.tail
    tp = QPainterPath()
    tp.moveTo(cx + 38, 156)
    tp.cubicTo(cx + 68, 158 + tail * 5, cx + 84, 130 + tail * 9, cx + 68 + tail * 7, 100 + tail * 12)
    _stroke_path(p, tp, dark, 15)
    _stroke_path(p, tp, body, 9)

    # ---- 耳朵（先画，身体盖住根部）
    for side in (-1, 1):
        outer = QPainterPath()
        outer.moveTo(cx + side * 38, 78)
        outer.cubicTo(cx + side * 47, 60, cx + side * 47, 44, cx + side * 37, 37)
        outer.cubicTo(cx + side * 27, 42, cx + side * 17, 57, cx + side * 10, 67)
        outer.closeSubpath()
        p.setPen(_pen(dark, 3))
        p.setBrush(body)
        p.drawPath(outer)

        inner = QPainterPath()
        inner.moveTo(cx + side * 34, 72)
        inner.cubicTo(cx + side * 41, 58, cx + side * 41, 48, cx + side * 36, 44)
        inner.cubicTo(cx + side * 29, 48, cx + side * 21, 59, cx + side * 15, 67)
        inner.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(ear)
        p.drawPath(inner)

    # ---- 身体
    bp = QPainterPath()
    bp.moveTo(cx - 45, 170)
    bp.cubicTo(cx - 56, 132, cx - 52, 84, cx - 30, 70)
    bp.cubicTo(cx - 18, 62, cx + 18, 62, cx + 30, 70)
    bp.cubicTo(cx + 52, 84, cx + 56, 132, cx + 45, 170)
    bp.cubicTo(cx + 34, 181, cx - 34, 181, cx - 45, 170)
    bp.closeSubpath()
    p.setPen(_pen(dark, 3))
    p.setBrush(body)
    p.drawPath(bp)

    # 肚子
    p.setPen(Qt.NoPen)
    p.setBrush(belly)
    p.drawEllipse(QRectF(cx - 29, 116, 58, 58))

    # ---- 前爪
    for side in (-1, 1):
        _ell(p, cx + side * 23, 170, 15, 9, belly, dark, 2.4)
        p.setPen(_pen(QColor(dark.red(), dark.green(), dark.blue(), 120), 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(cx + side * 23 - 3, 173), QPointF(cx + side * 23 + 3, 173))

    # ---- 口鼻区
    p.setPen(Qt.NoPen)
    p.setBrush(belly)
    p.drawEllipse(QRectF(cx - 27, 88, 54, 40))

    # ---- 花纹
    p.setPen(_pen(QColor(dark.red(), dark.green(), dark.blue(), 150), 3.4))
    p.drawLine(QPointF(cx - 8, 68), QPointF(cx - 5, 76))
    p.drawLine(QPointF(cx, 66), QPointF(cx, 74))
    p.drawLine(QPointF(cx + 8, 68), QPointF(cx + 5, 76))

    # ---- 眼睛
    emo = look.emotion
    if look.sleeping:
        emo = "sleepy"
    blink_closed = look.blink > 0.55
    for side in (-1, 1):
        ex = cx + side * 20
        ey = 84 + look.look_y * 2
        _draw_eye(p, emo, blink_closed, ex, ey, look.look_x, side, body, dark, look)

    # ---- 腮红
    if emo not in ("angry",):
        ba = 105 if emo in ("happy", "love") else 78
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(blush.red(), blush.green(), blush.blue(), ba))
        p.drawEllipse(QRectF(cx - 40, 94, 17, 9))
        p.drawEllipse(QRectF(cx + 23, 94, 17, 9))

    # ---- 嘴
    _draw_mouth(p, emo, look, cx, 106)

    # ---- 胡须
    p.setPen(_pen(QColor(INK.red(), INK.green(), INK.blue(), 90), 1.6))
    p.drawLine(QPointF(cx - 34, 98), QPointF(cx - 47, 95))
    p.drawLine(QPointF(cx - 34, 104), QPointF(cx - 47, 106))
    p.drawLine(QPointF(cx + 34, 98), QPointF(cx + 47, 95))
    p.drawLine(QPointF(cx + 34, 104), QPointF(cx + 47, 106))

    # ---- 阶段装饰
    _draw_accessory(p, look, cx, accent, belly, dark)


def _draw_eye(p: QPainter, emo: str, blink: bool, ex: float, ey: float,
              look_x: float, side: int, body: QColor, dark: QColor, look: Look) -> None:
    if emo == "love":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#F0567A"))
        p.drawPath(_heart_path(ex, ey, 8.5))
        return
    if emo == "sleepy" or blink:
        path = QPainterPath()
        if emo == "sleepy":
            path.moveTo(ex - 8, ey - 3)
            path.quadTo(ex, ey + 5, ex + 8, ey - 3)
        else:
            path.moveTo(ex - 8, ey)
            path.quadTo(ex, ey + 2.5, ex + 8, ey)
        _stroke_path(p, path, INK, 2.8)
        return
    if emo == "happy":
        path = QPainterPath()
        path.moveTo(ex - 8, ey + 3)
        path.quadTo(ex, ey - 7, ex + 8, ey + 3)
        _stroke_path(p, path, INK, 3.0)
        return
    if emo == "angry":
        _ell(p, ex, ey, 7.4, 8.6, INK)
        p.setBrush(WHITE)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(ex - 5.6, ey - 5.4, 4.0, 4.0))
        p.setPen(_pen(INK, 3.0))
        p.drawLine(QPointF(ex - side * 9, ey - 13), QPointF(ex + side * 7, ey - 9))
        return

    # 普通/开心/难过 的睁眼
    lift = -1.5 if emo == "sad" else 0.0
    _ell(p, ex, ey + lift, 7.6, 9.0, INK)
    p.setBrush(WHITE)
    p.setPen(Qt.NoPen)
    hx = ex + look_x * 2.6 - 2.2
    p.drawEllipse(QRectF(hx, ey + lift - 5.6, 4.2, 4.2))
    p.setBrush(QColor(255, 255, 255, 150))
    p.drawEllipse(QRectF(hx + 5.0, ey + lift + 1.6, 2.2, 2.2))
    if emo == "sad":
        p.setPen(_pen(INK, 2.6))
        p.drawLine(QPointF(ex - 9, ey - 8), QPointF(ex + 9, ey - 11))


def _draw_mouth(p: QPainter, emo: str, look: Look, cx: float, my: float) -> None:
    if lick := look.mouth:
        rx = 5.4 + lick * 1.8
        ry = 3.4 + lick * 4.6
        p.setPen(_pen(INK, 2.2))
        p.setBrush(QColor("#E87B82"))
        p.drawEllipse(QRectF(cx - rx, my - 1, rx * 2, ry * 2))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#F7A7AE"))
        p.drawEllipse(QRectF(cx - rx * 0.55, my + ry * 0.85, rx * 1.1, ry * 0.8))
        return

    path = QPainterPath()
    if emo in ("sad", "dizzy"):
        path.moveTo(cx - 6, my + 4)
        path.quadTo(cx, my - 3, cx + 6, my + 4)
    elif emo == "angry":
        path.moveTo(cx - 7, my + 3)
        path.quadTo(cx, my - 2, cx + 7, my + 3)
    elif emo in ("happy", "love"):
        path.moveTo(cx - 7.5, my)
        path.quadTo(cx - 3.5, my + 6, cx, my + 1.2)
        path.quadTo(cx + 3.5, my + 6, cx + 7.5, my)
    else:
        path.moveTo(cx - 6.5, my)
        path.quadTo(cx - 3.2, my + 4.5, cx, my + 1.0)
        path.quadTo(cx + 3.2, my + 4.5, cx + 6.5, my)
    _stroke_path(p, path, INK, 2.6)

    if emo == "happy":
        # 一点小舌头
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#F08C93"))
        p.drawEllipse(QRectF(cx - 3.2, my + 2.4, 6.4, 3.6))


def _draw_accessory(p: QPainter, look: Look, cx: float, accent: QColor,
                    belly: QColor, dark: QColor) -> None:
    stage = look.stage
    if stage == 1:
        # 围兜
        path = QPainterPath()
        path.moveTo(cx - 26, 118)
        path.cubicTo(cx - 26, 140, cx - 14, 152, cx, 152)
        path.cubicTo(cx + 14, 152, cx + 26, 140, cx + 26, 118)
        path.closeSubpath()
        p.setPen(_pen(QColor(accent.red(), accent.green(), accent.blue(), 170), 2.0))
        p.setBrush(QColor(255, 255, 255, 220))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(accent)
        p.drawPath(_heart_path(cx, 133, 5.2))
    elif stage == 2:
        # 铃铛项圈
        p.setPen(_pen(QColor(dark.red(), dark.green(), dark.blue(), 150), 1.6))
        p.setBrush(accent)
        p.drawRoundedRect(QRectF(cx - 32, 119, 64, 11), 5.5, 5.5)
        p.setPen(_pen(QColor("#C9862E"), 1.8))
        p.setBrush(QColor("#FFD86B"))
        p.drawEllipse(QRectF(cx - 6, 126, 12, 12))
        p.setPen(_pen(QColor("#C9862E"), 1.4))
        p.drawLine(QPointF(cx - 2.6, 131), QPointF(cx + 2.6, 131))
    else:
        # 小皇冠
        path = QPainterPath()
        path.moveTo(cx - 20, 46)
        path.lineTo(cx - 17, 28)
        path.lineTo(cx - 7, 37)
        path.lineTo(cx, 22)
        path.lineTo(cx + 7, 37)
        path.lineTo(cx + 17, 28)
        path.lineTo(cx + 20, 46)
        path.closeSubpath()
        p.setPen(_pen(QColor("#D9A03A"), 2.2))
        p.setBrush(QColor("#FFD86B"))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#FF6F8E"))
        p.drawEllipse(QRectF(cx - 3.4, 38, 6.8, 6.8))


def _draw_egg(p: QPainter, look: Look, belly: QColor, dark: QColor, accent: QColor) -> None:
    # 蛋壳
    p.save()
    p.translate(100, 180)
    wob = math.sin(look.t * 7.0) * (3.4 if look.egg_crack else 1.0)
    p.rotate(wob)
    p.translate(-100, -180)

    shell = QColor("#FFF7E8")
    edge = QColor("#E4C9A0")
    p.setPen(_pen(edge, 3))
    p.setBrush(shell)
    path = QPainterPath()
    path.moveTo(100, 74)
    path.cubicTo(128, 74, 146, 104, 146, 132)
    path.cubicTo(146, 162, 126, 180, 100, 180)
    path.cubicTo(74, 180, 54, 162, 54, 132)
    path.cubicTo(54, 104, 72, 74, 100, 74)
    path.closeSubpath()
    p.drawPath(path)

    # 斑点
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#F2DFC0"))
    for (x, y, r) in ((82, 108, 7), (118, 120, 9), (96, 148, 8), (120, 152, 5), (76, 138, 4)):
        p.drawEllipse(QRectF(x - r, y - r * 0.8, r * 2, r * 1.6))

    # 裂纹
    if look.egg_crack >= 1:
        p.setPen(_pen(edge, 2.6))
        p.setBrush(Qt.NoBrush)
        c = QPainterPath()
        c.moveTo(76, 96)
        c.lineTo(88, 104)
        c.lineTo(80, 114)
        c.lineTo(94, 120)
        p.drawPath(c)
    if look.egg_crack >= 2:
        c2 = QPainterPath()
        c2.moveTo(124, 92)
        c2.lineTo(114, 102)
        c2.lineTo(124, 110)
        c2.lineTo(112, 122)
        c2.lineTo(122, 130)
        p.drawPath(c2)
    if look.egg_crack >= 3:
        p.setPen(_pen(edge, 2.2))
        c3 = QPainterPath()
        c3.moveTo(70, 128)
        c3.lineTo(84, 134)
        c3.lineTo(74, 144)
        p.drawPath(c3)

    # 高光
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 150))
    p.drawEllipse(QRectF(74, 92, 16, 26))
    p.restore()


# ------------------------------------------------------------------ 小图标
def food_pixmap(icon: str, size: int = 28) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.scale(size / 32.0, size / 32.0)
    ink = QColor("#8A6A52")
    if icon == "fish":
        p.setPen(_pen(ink, 1.8))
        p.setBrush(QColor("#FFB877"))
        p.drawEllipse(QRectF(6, 12, 18, 11))
        path = QPainterPath()
        path.moveTo(24, 17.5)
        path.lineTo(30, 11)
        path.lineTo(30, 24)
        path.closeSubpath()
        p.setBrush(QColor("#FF9E55"))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(INK)
        p.drawEllipse(QRectF(9.5, 15, 2.6, 2.6))
    elif icon == "milk":
        p.setPen(_pen(ink, 1.8))
        p.setBrush(QColor("#F2FAFF"))
        p.drawRoundedRect(QRectF(10, 10, 12, 18), 3, 3)
        p.setBrush(QColor("#BEE3F8"))
        p.drawRect(QRectF(10, 13, 12, 4))
        p.setBrush(QColor("#8EC9E8"))
        p.drawRoundedRect(QRectF(12, 5, 8, 5), 1.5, 1.5)
    elif icon == "cake":
        p.setPen(_pen(ink, 1.8))
        p.setBrush(QColor("#FFEFD8"))
        p.drawRoundedRect(QRectF(6, 16, 20, 11), 2, 2)
        p.setBrush(QColor("#FFC2CE"))
        p.drawRect(QRectF(6, 16, 20, 4))
        p.setBrush(QColor("#E8405A"))
        p.drawEllipse(QRectF(14, 9, 5, 6))
    elif icon == "apple":
        p.setPen(_pen(ink, 1.8))
        p.setBrush(QColor("#F2604F"))
        p.drawEllipse(QRectF(7, 11, 18, 16))
        p.setBrush(QColor("#7CC576"))
        p.drawEllipse(QRectF(18, 7, 8, 5))
        p.setPen(_pen(QColor("#8A6A52"), 1.6))
        p.drawLine(QPointF(16, 12), QPointF(16, 8))
    else:  # pudding
        p.setPen(_pen(ink, 1.8))
        p.setBrush(QColor("#FFE7A8"))
        path = QPainterPath()
        path.moveTo(8, 15)
        path.lineTo(24, 15)
        path.lineTo(21, 27)
        path.lineTo(11, 27)
        path.closeSubpath()
        p.drawPath(path)
        p.setBrush(QColor("#C98B4B"))
        p.drawEllipse(QRectF(8, 11, 16, 6))
    p.end()
    return pm


def render_pixmap(size: int, look: Look, palette: dict) -> QPixmap:
    """把宠物渲染成静态图片（托盘图标、状态面板头像用）。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    draw_pet(p, QRectF(0, 0, size, size), look, palette)
    p.end()
    return pm


def tray_icon_pixmap(size: int, palette: dict) -> QPixmap:
    look = Look(stage=3, emotion="happy", t=0.4)
    return render_pixmap(size, look, palette)
