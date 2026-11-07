"""宠物外观绘制：程序化矢量，按真实猫的体态与毛色分层渲染。

逻辑坐标系固定 200x200，地面 y=180，绘制时按目标矩形等比缩放。

分层顺序（从后到前）：
    地面阴影 → 尾巴 → 后腿/后臀 → 身体 → 前腿 → 胸腹浅色区
    → 头部（耳朵、头骨、面颊毛、口鼻）→ 五官 → 胡须 → 装饰/道具

为了"真实感"，用了这些手段：
    * 三色渐变填充（受光面 / 固有色 / 暗部），而不是平涂
    * 轮廓上的绒毛（沿路径法线画短毛，颜色随机微变）
    * 叠加的程序化毛流纹理（一次生成、全局复用）
    * 猫眼用虹膜渐变 + 竖瞳 + 双高光，而不是一颗黑豆
    * 阴影用径向渐变，边缘柔和
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)

CANVAS = 200.0
FEET_Y = 180.0
CX = 100.0

INK = QColor("#3A2E28")


# ------------------------------------------------------------------ 视觉状态
@dataclass
class Look:
    """一帧的视觉状态，由动画系统喂给绘制函数。"""

    t: float = 0.0
    emotion: str = "normal"      # normal/happy/love/sad/sleepy/angry/eat/dizzy/scared
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

    # ---- 姿态（互动动作靠这些参数摆出来）----
    pose: str = "sit"            # sit / stand / loaf / crouch / dangle / stretch
    head_dx: float = 0.0         # 头部相对位移
    head_dy: float = 0.0
    head_tilt: float = 0.0       # 歪头角度
    head_down: float = 0.0       # 0..1 低头（吃饭、蹭手）
    ear_back: float = 0.0        # 0..1 飞机耳
    eye_open: float = 1.0        # 0..1 眼裂开合
    pupil: float = 0.35          # 0..1 瞳孔放大程度
    tongue: float = 0.0          # 0..1 伸舌头/舔
    leg_l: float = 0.0           # 左前爪抬起 0..1
    leg_r: float = 0.0           # 右前爪抬起 0..1
    paw_fwd: float = 0.0         # 前爪前伸 0..1（扑/抓）
    walk: float = 0.0            # 0..1 行走强度
    walk_phase: float = 0.0
    tail_up: float = 0.0         # 0..1 尾巴竖直
    tail_curl: float = 0.0       # 0..1 尾尖卷曲
    purr: float = 0.0            # 0..1 呼噜（身体细密抖动）
    wet: float = 0.0             # 0..1 湿身（毛贴服）
    hand: float = 0.0            # 0..1 摸头的手
    prop: str = ""               # 当前道具名，交给 props 模块
    prop_t: float = 0.0          # 道具动画进度 0..1
    prop_extra: float = 0.0
    extra: dict = field(default_factory=dict)


# ------------------------------------------------------------------ 小工具
def _pen(color: QColor, width: float) -> QPen:
    p = QPen(color, width)
    p.setCapStyle(Qt.RoundCap)
    p.setJoinStyle(Qt.RoundJoin)
    return p


def _ell(p: QPainter, cx: float, cy: float, rx: float, ry: float,
         fill: QColor | None = None, outline: QColor | None = None, w: float = 2.0):
    if fill is not None:
        p.setBrush(QBrush(fill))
    else:
        p.setBrush(Qt.NoBrush)
    p.setPen(_pen(outline, w) if outline is not None else Qt.NoPen)
    p.drawEllipse(QRectF(cx - rx, cy - ry, rx * 2, ry * 2))


def _shade(c: QColor, k: float, a: int | None = None) -> QColor:
    """k<0 变暗，k>0 变亮。"""
    h, s, v, al = c.getHsvF()
    v = max(0.0, min(1.0, v * (1 + k)))
    s = max(0.0, min(1.0, s * (1 - 0.35 * k) if k > 0 else s * (1 + 0.1 * k)))
    out = QColor.fromHsvF(max(0, h), s, v, al if a is None else a / 255)
    if a is not None:
        out.setAlpha(a)
    return out


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    """按比例混合两个颜色，用来把"白爪子"压回毛色。"""
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() * (1 - t) + b.red() * t),
        int(a.green() * (1 - t) + b.green() * t),
        int(a.blue() * (1 - t) + b.blue() * t),
        a.alpha(),
    )


def _rgba(c: QColor, a: int) -> QColor:
    out = QColor(c)
    out.setAlpha(a)
    return out


def _vgrad(path: QPainterPath, c_top: QColor, c_mid: QColor, c_bot: QColor,
           y0: float, y1: float, x: float = CX) -> QBrush:
    g = QLinearGradient(x, y0, x, y1)
    g.setColorAt(0.0, c_top)
    g.setColorAt(0.42, c_mid)
    g.setColorAt(1.0, c_bot)
    return QBrush(g)


def _fill_path(p: QPainter, path: QPainterPath, brush) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(brush)
    p.drawPath(path)


def _bez(p0, p1, p2, p3, n: int = 22) -> list[tuple[float, float]]:
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        x = (mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0]
             + 3 * mt * t * t * p2[0] + t ** 3 * p3[0])
        y = (mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1]
             + 3 * mt * t * t * p2[1] + t ** 3 * p3[1])
        pts.append((x, y))
    return pts


def _ribbon(pts: list[tuple[float, float]], w0: float, w1: float,
            taper_mid: float = 1.0) -> QPainterPath:
    """把中心线加粗成一条带收窄的"丝带"，用于腿、尾巴。"""
    n = len(pts)
    left: list[tuple[float, float]] = []
    right: list[tuple[float, float]] = []
    for i, (x, y) in enumerate(pts):
        if i == 0:
            tx, ty = pts[1][0] - x, pts[1][1] - y
        elif i == n - 1:
            tx, ty = x - pts[-2][0], y - pts[-2][1]
        else:
            tx, ty = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
        ln = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / ln, tx / ln
        t = i / (n - 1)
        # 中段可以略鼓（腿部肌肉），两端收窄
        bulge = 1.0 + (taper_mid - 1.0) * math.sin(math.pi * min(1.0, t * 1.15))
        w = (w0 + (w1 - w0) * t) * 0.5 * bulge
        left.append((x + nx * w, y + ny * w))
        right.append((x - nx * w, y - ny * w))

    path = QPainterPath()
    path.moveTo(*left[0])
    for pt in left[1:]:
        path.lineTo(*pt)
    for pt in reversed(right):
        path.lineTo(*pt)
    path.closeSubpath()
    return path


# ------------------------------------------------------------------ 毛流纹理
_TEX_CACHE: dict[str, QPixmap] = {}


def _fur_tex(color: QColor) -> QPixmap:
    """生成一张可平铺的毛流噪声，叠在毛色上让表面不那么"塑料"。"""
    key = color.name()
    tex = _TEX_CACHE.get(key)
    if tex is not None:
        return tex
    size = 48
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    qp = QPainter(img)
    qp.setRenderHint(QPainter.Antialiasing, True)
    rnd = random.Random(11)
    # 毛流：短、密、基本竖直。放大时也不会变成"划痕"
    for _ in range(900):
        x = rnd.uniform(0, size)
        y = rnd.uniform(0, size)
        ln = rnd.uniform(1.8, 4.2)
        ang = math.pi / 2 + rnd.uniform(-0.22, 0.22)
        light = rnd.random() < 0.52
        c = _shade(color, 0.09 if light else -0.10, rnd.randint(10, 26))
        qp.setPen(QPen(c, rnd.uniform(0.45, 0.8)))
        qp.drawLine(QPointF(x, y), QPointF(x + math.cos(ang) * ln, y + math.sin(ang) * ln))
    qp.end()
    tex = QPixmap.fromImage(img)
    _TEX_CACHE[key] = tex
    return tex


def _fur_edge(p: QPainter, path: QPainterPath, base: QColor, *,
              count: int = 34, length: float = 4.2, seed: int = 3,
              only_bottom: bool = False, alpha: int = 150) -> None:
    """沿轮廓法线画一圈短毛，做出毛茸茸的边缘。"""
    rnd = random.Random(seed)
    for i in range(count):
        u = (i + 0.5) / count
        if only_bottom and u < 0.42:
            continue
        try:
            pt = path.pointAtPercent(u)
            nxt = path.pointAtPercent(min(0.999, u + 0.012))
        except Exception:
            continue
        tx, ty = nxt.x() - pt.x(), nxt.y() - pt.y()
        ln = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / ln, tx / ln
        # 只在下缘/侧面长毛，朝上的轮廓不加（不然像划痕）
        if ny < -0.15:
            continue
        L = length * rnd.uniform(0.6, 1.25)
        c = _shade(base, 0.12 if rnd.random() < 0.45 else -0.14, alpha)
        p.setPen(_pen(c, rnd.uniform(1.0, 1.9)))
        p.setBrush(Qt.NoBrush)
        sp = QPainterPath(QPointF(pt.x(), pt.y()))
        sp.quadTo(pt.x() + nx * L * 0.6 - tx * 0.02,
                  pt.y() + ny * L * 0.6 + ty * 0.02,
                  pt.x() + nx * L + tx * 0.05,
                  pt.y() + ny * L + ty * 0.05)
        p.drawPath(sp)


# ------------------------------------------------------------------ 主入口
def draw_pet(p: QPainter, rect: QRectF, look: Look, palette: dict) -> None:
    """把宠物画到 rect（设备坐标）里。"""
    if rect.width() <= 1 or rect.height() <= 1:
        return

    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.translate(rect.x(), rect.y())
    p.scale(rect.width() / CANVAS, rect.height() / CANVAS)

    # 目标尺寸太小时降低细节，避免糊成一团
    detail = 1.0 if rect.width() >= 140 else max(0.35, rect.width() / 140)

    _draw_ground(p, look, detail)

    p.save()
    p.translate(CX, FEET_Y)
    if look.lean:
        p.rotate(look.lean * 3.2)
    p.translate(-CX, -FEET_Y)
    p.translate(0, -look.bob - look.jump * 22)

    b = look.breath
    p.translate(CX, FEET_Y)
    p.scale(1 + 0.006 * b * (1 - 0.5 * look.squash),
            1 + 0.014 * b * (1 + look.squash) - 0.05 * look.squash)
    p.translate(-CX, -FEET_Y)

    if look.stage == 0:
        _draw_egg(p, look, palette, detail)
        p.restore()
        p.restore()
        return

    _draw_cat(p, look, palette, detail)
    p.restore()
    p.restore()


def _draw_ground(p: QPainter, look: Look, detail: float) -> None:
    """柔和的地面投影。跳起时缩小变淡。"""
    k = 1.0 - 0.3 * look.jump
    w = 46 * k
    h = 9 * k
    g = QRadialGradient(QPointF(CX, FEET_Y - 1), w)
    g.setColorAt(0.0, QColor(48, 34, 28, int(64 * (1 - 0.45 * look.jump))))
    g.setColorAt(0.55, QColor(48, 34, 28, int(34 * (1 - 0.45 * look.jump))))
    g.setColorAt(1.0, QColor(48, 34, 28, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QRectF(CX - w, FEET_Y - h, w * 2, h * 2))


# ------------------------------------------------------------------ 颜色
def _colors(palette: dict) -> dict:
    fur = QColor(palette.get("fur") or palette.get("body") or "#D79A5B")
    dark = QColor(palette.get("fur_dark") or palette.get("dark") or "#A96C33")
    light = QColor(palette.get("fur_light") or palette.get("belly") or "#FBF1E2")
    return {
        "fur": fur,
        "dark": dark,
        "light": light,
        "ear": QColor(palette.get("ear") or "#E6A9A6"),
        "nose": QColor(palette.get("nose") or "#DB8E8C"),
        "eye": QColor(palette.get("eye") or "#9DBE63"),
        "accent": QColor(palette.get("accent") or "#E08A45"),
        "blush": QColor(palette.get("blush") or "#F09B9B"),
        "pattern": palette.get("pattern") or "tabby",
    }


# ------------------------------------------------------------------ 几何
def _geo(look: Look) -> dict:
    """按姿态与成长阶段算出各部位坐标。

    比例参照真猫：坐姿时肩到地面的高度约为肩宽的两倍，头宽约为肩宽的 0.72。
    """
    st = max(1, min(3, look.stage))
    if st == 1:      # 幼崽：头大、身子短、腿短
        head_w, head_h = 20.0, 20.5
        hip_hw, chest_hw = 25.0, 21.0
        leg_w = 10.6
        shoulder_y, hip_y = 111.0, 166.0
        head_cy = 91.0
    elif st == 2:    # 少年
        head_w, head_h = 21.6, 22.2
        hip_hw, chest_hw = 30.0, 24.8
        leg_w = 12.0
        shoulder_y, hip_y = 103.0, 167.0
        head_cy = 79.0
    else:            # 成年
        head_w, head_h = 22.6, 23.2
        hip_hw, chest_hw = 34.0, 27.6
        leg_w = 13.2
        shoulder_y, hip_y = 100.0, 169.0
        head_cy = 71.0

    pose = look.pose
    leg_len = 1.0
    tuck = 0.0
    if pose == "stand":
        shoulder_y -= 12
        hip_y -= 8
        head_cy -= 13
        leg_len = 1.30
    elif pose == "loaf":
        shoulder_y += 34
        hip_y += 2
        head_cy += 42
        tuck = 1.0
        leg_len = 0.0
    elif pose == "crouch":
        shoulder_y += 20
        hip_y += 2
        head_cy += 26
        leg_len = 0.34
        tuck = 0.5
    elif pose == "dangle":
        # 被拎起：整只猫离地吊起来，四只爪子垂在下面
        shoulder_y -= 14
        hip_y -= 40
        head_cy -= 9
        leg_len = 1.0
        tuck = 0.0
    elif pose == "eat":
        # 低头吃盆里的东西：身子往前塌下去，头接近盆口
        shoulder_y += 10
        hip_y += 3
        head_cy += 50
        leg_len = 0.6
    elif pose == "stretch":
        # 伸懒腰：前身压低、屁股抬高、两爪往前伸
        shoulder_y += 18
        hip_y -= 5
        head_cy += 30
        leg_len = 0.78

    # 低头：整颗头往下走（吃饭、蹭手）
    head_cy += look.head_down * 18
    return {
        "head_w": head_w,
        "head_h": head_h,
        "hip_hw": hip_hw,
        "chest_hw": chest_hw,
        "leg_w": leg_w,
        "shoulder_y": shoulder_y,
        "hip_y": hip_y,
        "head_cx": CX + look.head_dx,
        "head_cy": head_cy + look.head_dy,
        "leg_len": leg_len,
        "tuck": tuck,
        "neck_y": shoulder_y - 11,
    }


def _smooth(points: list[tuple[float, float]], tension: float = 1.0,
            closed: bool = True) -> QPainterPath:
    """Catmull-Rom 样条：给几个关键点就能得到有机的曲线轮廓。"""
    pts = list(points)
    n = len(pts)
    if n < 3:
        path = QPainterPath()
        path.moveTo(*pts[0])
        for pt in pts[1:]:
            path.lineTo(*pt)
        return path

    path = QPainterPath()
    path.moveTo(*pts[0])
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0 = pts[(i - 1) % n] if closed else pts[max(0, i - 1)]
        p1 = pts[i % n]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if closed else pts[min(n - 1, i + 2)]
        c1x = p1[0] + (p2[0] - p0[0]) / 6.0 * tension
        c1y = p1[1] + (p2[1] - p0[1]) / 6.0 * tension
        c2x = p2[0] - (p3[0] - p1[0]) / 6.0 * tension
        c2y = p2[1] - (p3[1] - p1[1]) / 6.0 * tension
        path.cubicTo(c1x, c1y, c2x, c2y, p2[0], p2[1])
    if closed:
        path.closeSubpath()
    return path


def _body_path(g: dict) -> QPainterPath:
    """坐姿躯干：脖子收窄 → 肩 → 胸 → 腰略收 → 髋部最宽 → 屁股压在地面上。"""
    cx = CX
    hy = g["hip_y"]
    cw, hw = g["chest_hw"], g["hip_hw"]
    neck_y = g.get("neck_y", g["shoulder_y"] - 11)
    neck_hw = cw * 0.46
    span = max(1.0, hy - neck_y)

    def flank(sign: int) -> list[tuple[float, float]]:
        return [
            (cx + sign * neck_hw * 0.94, neck_y + 2),
            (cx + sign * cw * 0.74, neck_y + span * 0.07),
            (cx + sign * cw * 0.96, neck_y + span * 0.16),
            (cx + sign * cw, neck_y + span * 0.26),
            (cx + sign * cw * 0.90, neck_y + span * 0.38),
            (cx + sign * hw * 0.97, neck_y + span * 0.54),
            (cx + sign * hw, neck_y + span * 0.70),
            (cx + sign * hw * 0.96, neck_y + span * 0.85),
            (cx + sign * hw * 0.80, hy + 2),
            (cx + sign * hw * 0.46, hy + 9),
        ]

    pts = [(cx, neck_y - 8)]
    pts += flank(1)
    pts += [(cx, hy + 11)]
    pts += flank(-1)[::-1]
    return _smooth(pts, tension=0.9)


def _head_path(cx: float, cy: float, w: float, h: float) -> QPainterPath:
    """猫头：颧骨最宽、下巴收窄。"""
    pts = [
        (cx, cy - h),
        (cx + w * 0.58, cy - h * 0.93),
        (cx + w * 0.92, cy - h * 0.55),
        (cx + w, cy - h * 0.02),
        (cx + w * 0.84, cy + h * 0.44),
        (cx + w * 0.46, cy + h * 0.80),
        (cx, cy + h * 0.96),
        (cx - w * 0.46, cy + h * 0.80),
        (cx - w * 0.84, cy + h * 0.44),
        (cx - w, cy - h * 0.02),
        (cx - w * 0.92, cy - h * 0.55),
        (cx - w * 0.58, cy - h * 0.93),
    ]
    return _smooth(pts, tension=0.9)


# ------------------------------------------------------------------ 猫
def _draw_cat(p: QPainter, look: Look, palette: dict, detail: float) -> None:
    c = _colors(palette)
    g = _geo(look)
    fur = c["fur"]

    # 尾巴：坐/趴时绕到身前，站/被拎起时放在身后
    front_tail = look.pose == "loaf"

    if not front_tail:
        _draw_tail(p, look, c, g, detail, front=False)

    # ---------------- 后臀的体块（贴在身体轮廓内）
    _draw_haunch(p, look, c, g)

    # ---------------- 身体
    body = _body_path(g)
    _fill_path(p, body,
               _vgrad(body, _shade(fur, 0.14), fur, _shade(fur, -0.24),
                      g["shoulder_y"] - 12, g["hip_y"] + 12))
    if detail > 0.6:
        p.save()
        p.setClipPath(body)
        p.setOpacity(0.82)
        p.drawTiledPixmap(body.boundingRect(), _fur_tex(fur))
        p.restore()

    # 侧面暗部（体积感）+ 顶部受光
    p.save()
    p.setClipPath(body)
    side = QLinearGradient(CX - g["hip_hw"], 0, CX + g["hip_hw"], 0)
    side.setColorAt(0.0, QColor(0, 0, 0, 34))
    side.setColorAt(0.28, QColor(0, 0, 0, 0))
    side.setColorAt(0.70, QColor(0, 0, 0, 0))
    side.setColorAt(1.0, QColor(0, 0, 0, 48))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(side))
    p.drawRect(body.boundingRect())
    top = QLinearGradient(0, g["shoulder_y"] - 10, 0, g["shoulder_y"] + 30)
    top.setColorAt(0.0, QColor(255, 255, 255, 46))
    top.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(QBrush(top))
    p.drawRect(body.boundingRect())
    # 贴地的一道接触阴影
    ground_shade = QLinearGradient(0, g["hip_y"] - 4, 0, g["hip_y"] + 10)
    ground_shade.setColorAt(0.0, QColor(0, 0, 0, 0))
    ground_shade.setColorAt(1.0, QColor(0, 0, 0, 46))
    p.setBrush(QBrush(ground_shade))
    p.drawRect(body.boundingRect())
    p.restore()

    # 左上方来的轮廓光，让身体从背景里"立"起来
    p.save()
    p.setClipPath(body)
    p.translate(2.8, 2.8)
    p.setPen(_pen(QColor(255, 250, 238, 66), 3.4))
    p.setBrush(Qt.NoBrush)
    p.drawPath(body)
    p.restore()

    _draw_bib(p, look, c, g, body)
    _draw_pattern(p, look, c, g, body)

    # 边缘柔化 + 短绒毛（不要做成硬毛刺）
    p.setPen(_pen(_rgba(_shade(fur, -0.08), 70), 2.6))
    p.setBrush(Qt.NoBrush)
    p.drawPath(body)
    _fur_edge(p, body, fur, count=int(44 * detail), length=1.6, seed=5,
              only_bottom=True, alpha=80)

    _draw_front_legs(p, look, c, g)

    if front_tail:
        _draw_tail(p, look, c, g, detail, front=True)

    _draw_neck(p, look, c, g)
    _draw_chest_ruff(p, look, c, g)

    # 头部压在胸口的阴影，让头"坐"在身体上
    p.save()
    p.setClipPath(body)
    chin = QRadialGradient(QPointF(g["head_cx"], g["head_cy"] + g["head_h"] * 0.86),
                           g["head_w"] * 1.5)
    chin.setColorAt(0.0, QColor(60, 40, 30, 62))
    chin.setColorAt(0.6, QColor(60, 40, 30, 22))
    chin.setColorAt(1.0, QColor(60, 40, 30, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(chin))
    p.drawEllipse(QRectF(g["head_cx"] - g["head_w"] * 1.5,
                         g["head_cy"] + g["head_h"] * 0.55,
                         g["head_w"] * 3, g["head_h"] * 1.4))
    p.restore()

    _draw_head(p, look, c, g, detail)
    _draw_raised_paw(p, look, c, g)
    _draw_accessory(p, look, c, g)


def _draw_tail(p: QPainter, look: Look, c: dict, g: dict, detail: float,
               front: bool = False) -> None:
    """尾巴：细长、末端收窄；坐姿时绕到身前，从爪子前面经过。"""
    fur, dark = c["fur"], c["dark"]
    base_x = CX + g["hip_hw"] - 9
    base_y = g["hip_y"] - 26
    sway = look.tail * 6
    up = look.tail_up * 26
    curl = look.tail_curl

    if front:
        if look.pose == "loaf":
            # 环抱身体
            pts = _bez((base_x, base_y + 22), (base_x + 18, base_y + 26),
                       (CX + 22, FEET_Y - 2), (CX - 14, FEET_Y - 4))
        else:
            pts = _bez((base_x - 2, base_y + 20), (base_x + 20, base_y + 26),
                       (base_x + 6, FEET_Y + 1), (CX - 16, FEET_Y - 3))
        # 尾尖轻轻上翘
        lift = 3.0 + 7.0 * curl
        n = len(pts)
        pts = [pt if i < n - 5 else (pt[0] + (i - (n - 5)) * 0.6,
                                     pt[1] - lift * ((i - (n - 5)) / 5) ** 2)
               for i, pt in enumerate(pts)]
        w0, w1 = 9.5, 4.0
    elif look.pose == "dangle":
        # 受惊：尾巴夹起来贴着身体
        pts = _bez((base_x, base_y + 8), (base_x + 10, base_y - 10),
                   (base_x - 2, base_y - 32), (base_x - 14, base_y - 28))
        w0, w1 = 9.5, 3.6
    elif look.pose == "stand":
        pts = _bez((base_x, base_y + 12), (base_x + 18, base_y + 14),
                   (base_x + 22, base_y - 20), (base_x + 6 + sway, base_y - 42 - up))
        w0, w1 = 9.0, 3.6
    else:
        pts = _bez((base_x + 2, base_y + 24), (base_x + 26, base_y + 16),
                   (base_x + 30 + sway * 0.6, base_y - 22 - up * 0.4),
                   (base_x + 10 + sway + curl * 14, base_y - 50 - up))
        w0, w1 = 10.5, 4.2

    ribbon = _ribbon(pts, w0, w1 + curl * 1.2, taper_mid=0.9)
    gr = QLinearGradient(pts[0][0], pts[0][1], pts[-1][0], pts[-1][1])
    gr.setColorAt(0.0, _shade(fur, -0.12))
    gr.setColorAt(0.5, fur)
    gr.setColorAt(1.0, _shade(fur, -0.2))
    _fill_path(p, ribbon, QBrush(gr))

    # 下缘暗部，做出圆柱感
    p.save()
    p.setClipPath(ribbon)
    edge = QLinearGradient(0, pts[0][1], 0, pts[0][1] - 50)
    edge.setColorAt(0.0, QColor(0, 0, 0, 0))
    edge.setColorAt(1.0, QColor(0, 0, 0, 30))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(edge))
    p.drawRect(ribbon.boundingRect())
    p.restore()

    # 尾环
    if c["pattern"] in ("tabby", "point") and detail > 0.5:
        p.setBrush(Qt.NoBrush)
        for i in (4, 7, 10, 13):
            if i >= len(pts) - 2:
                break
            x, y = pts[i]
            nx, ny = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
            ln = math.hypot(nx, ny) or 1
            nx, ny = -ny / ln, nx / ln
            w = (w0 + (w1 - w0) * (i / len(pts))) * 0.5
            p.setPen(_pen(_rgba(dark, 130), 2.2))
            p.drawLine(QPointF(x - nx * w * 0.82, y - ny * w * 0.82),
                       QPointF(x + nx * w * 0.82, y + ny * w * 0.82))

    _fur_edge(p, ribbon, fur, count=int(14 * detail), length=2.6, seed=9, alpha=120)


def _draw_haunch(p: QPainter, look: Look, c: dict, g: dict) -> None:
    """后腿：折叠在身侧的大腿。用体块明暗 + 一道折痕表现，不做成独立圆球。"""
    fur = c["fur"]
    body = _body_path(g)
    hw, hy = g["hip_hw"], g["hip_y"]

    p.save()
    p.setClipPath(body)
    for side in (-1, 1):
        tcx = CX + side * hw * 0.60
        tcy = hy - 24
        rx = hw * 0.54
        ry = hy * 0.17 + 14
        # 大腿体块：上亮下暗，边缘完全融进身体
        grad = QRadialGradient(QPointF(tcx - side * rx * 0.22, tcy - ry * 0.42), rx * 1.85)
        grad.setColorAt(0.0, _rgba(_shade(fur, 0.15), 96))
        grad.setColorAt(0.62, _rgba(_shade(fur, 0.01), 38))
        grad.setColorAt(1.0, _rgba(_shade(fur, -0.2), 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QRectF(tcx - rx, tcy - ry, rx * 2, ry * 2))

        # 大腿与腹部的折痕
        p.setPen(_pen(_rgba(_shade(fur, -0.32), 52), 1.7))
        p.setBrush(Qt.NoBrush)
        crease = QPainterPath(QPointF(CX + side * hw * 0.24, hy - 44))
        crease.cubicTo(CX + side * hw * 0.44, hy - 30,
                       CX + side * hw * 0.52, hy - 14,
                       CX + side * hw * 0.44, hy + 2)
        p.drawPath(crease)
        # 折痕下的一道亮边，让大腿有厚度
        p.setPen(_pen(_rgba(_shade(fur, 0.2), 44), 1.4))
        bright = QPainterPath(QPointF(CX + side * hw * 0.27, hy - 42))
        bright.cubicTo(CX + side * hw * 0.46, hy - 28,
                       CX + side * hw * 0.55, hy - 12,
                       CX + side * hw * 0.47, hy + 1)
        p.drawPath(bright)
    p.restore()

    # 后爪从身侧探出一点（在前爪的两侧偏后）
    if look.pose in ("sit", "crouch", "stand", "eat", "stretch"):
        for side in (-1, 1):
            px = CX + side * hw * 0.74
            py = hy + 1
            # 柔和的接触阴影，不要画成一圈黑边
            sh = QRadialGradient(QPointF(px, py + 2.2), 11.0)
            sh.setColorAt(0.0, QColor(56, 38, 28, 52))
            sh.setColorAt(1.0, QColor(56, 38, 28, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(sh))
            p.drawEllipse(QRectF(px - 11, py - 3.0, 22, 12))
            paw_c = _mix(c["light"], c["fur"], 0.40)
            pg = QRadialGradient(QPointF(px - side * 1.6, py - 2.0), 10.5)
            pg.setColorAt(0.0, _shade(paw_c, 0.04))
            pg.setColorAt(0.72, _shade(paw_c, -0.10))
            pg.setColorAt(1.0, _rgba(_shade(paw_c, -0.20), 0))
            p.setBrush(QBrush(pg))
            p.drawEllipse(QRectF(px - 9.8, py - 4.6, 19.6, 9.4))
            p.setPen(_pen(_rgba(c["dark"], 60), 1.0))
            p.setBrush(Qt.NoBrush)
            for k in (-3.0, 0.0, 3.0):
                p.drawLine(QPointF(px + k, py + 0.4), QPointF(px + k, py + 3.6))


def _draw_bib(p: QPainter, look: Look, c: dict, g: dict, body: QPainterPath) -> None:
    """胸口/腹部的浅色毛。真实猫几乎都有，边缘要柔和不要像贴纸。"""
    light = c["light"]
    pat = c["pattern"]
    if pat == "point":
        return
    p.save()
    p.setClipPath(body)
    top = g["shoulder_y"] - 2
    rw = g["chest_hw"] * (0.86 if pat == "tuxedo" else 0.60)
    grad = QLinearGradient(0, top, 0, g["hip_y"] + 6)
    grad.setColorAt(0.0, _rgba(light, 46))
    grad.setColorAt(0.26, _rgba(light, 132 if pat == "tuxedo" else 72))
    grad.setColorAt(0.72, _rgba(light, 70 if pat == "tuxedo" else 32))
    grad.setColorAt(1.0, _rgba(light, 14))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    path = QPainterPath()
    path.moveTo(CX - rw, top - 6)
    path.cubicTo(CX - rw * 0.92, top + 24, CX - rw * 1.08, g["hip_y"] - 20,
                 CX - rw * 0.44, g["hip_y"] + 4)
    path.cubicTo(CX, g["hip_y"] + 10, CX + rw * 0.44, g["hip_y"] + 4,
                 CX + rw * 1.08, g["hip_y"] - 20)
    path.cubicTo(CX + rw * 0.92, top + 24, CX + rw, top - 6, CX, top - 8)
    path.closeSubpath()
    p.drawPath(path)
    p.restore()


def _draw_pattern(p: QPainter, look: Look, c: dict, g: dict, body: QPainterPath) -> None:
    pat = c["pattern"]
    if pat not in ("tabby", "tuxedo") or g["leg_len"] == 0 and pat == "tabby":
        pass
    p.save()
    p.setClipPath(body)
    if pat == "tabby":
        # 躯干侧面的横向虎斑：细、柔、顺着身体弧度
        p.setPen(_pen(_rgba(c["dark"], 48), 2.2))
        p.setBrush(Qt.NoBrush)
        for i in range(3):
            y = g["shoulder_y"] + 26 + i * 14
            for side in (-1, 1):
                x0 = CX + side * (g["chest_hw"] - 1)
                x1 = CX + side * (g["hip_hw"] * 0.94)
                path = QPainterPath(QPointF(x0, y))
                path.cubicTo(x0 + side * 9, y - 4, x1 - side * 7, y + 6, x1, y + 2)
                p.drawPath(path)
    elif pat == "tuxedo":
        # 背部的黑色披风
        p.setPen(Qt.NoPen)
        grad = QLinearGradient(0, g["shoulder_y"] - 12, 0, g["hip_y"] - 10)
        grad.setColorAt(0.0, _rgba(c["dark"], 80))
        grad.setColorAt(1.0, _rgba(c["dark"], 0))
        p.setBrush(QBrush(grad))
        p.drawRect(body.boundingRect())
    p.restore()




def _draw_neck(p: QPainter, look: Look, c: dict, g: dict) -> None:
    """脖子：把头和身体连起来。低头吃饭时会被拉长，没有它头就会"浮"在身体上。"""
    cx, cy = g["head_cx"], g["head_cy"]
    hw, hh = g["head_w"], g["head_h"]
    nw = g["chest_hw"] * 0.52
    neck_y = g["neck_y"]
    top_y = cy + hh * 0.60
    if top_y <= neck_y + 2:
        return

    path = QPainterPath()
    path.moveTo(cx - nw, neck_y - 10)
    path.cubicTo(cx - nw * 0.96, (neck_y + top_y) * 0.5, cx - nw * 1.02, top_y - 8,
                 cx - hw * 0.56, top_y + 6)
    path.lineTo(cx + hw * 0.56, top_y + 6)
    path.cubicTo(cx + nw * 1.02, top_y - 8, cx + nw * 0.96, (neck_y + top_y) * 0.5,
                 cx + nw, neck_y - 10)
    path.closeSubpath()

    gr = QLinearGradient(0, neck_y, 0, top_y + 6)
    gr.setColorAt(0.0, _shade(c["fur"], -0.20))
    gr.setColorAt(0.55, _shade(c["fur"], -0.12))
    gr.setColorAt(1.0, _shade(c["fur"], -0.24))
    _fill_path(p, path, QBrush(gr))
    # 下巴投在脖子上的阴影
    p.save()
    p.setClipPath(path)
    sh = QLinearGradient(0, top_y - 10, 0, top_y + 12)
    sh.setColorAt(0.0, QColor(56, 36, 26, 96))
    sh.setColorAt(1.0, QColor(56, 36, 26, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(sh))
    p.drawRect(path.boundingRect())
    p.restore()


def _draw_chest_ruff(p: QPainter, look: Look, c: dict, g: dict) -> None:
    """胸口的绒毛层：用几段圆弧做出毛尖，盖住前腿根部。"""
    if look.pose in ("loaf", "dangle"):
        return
    fur, light = c["fur"], c["light"]
    top = g["shoulder_y"] + 2
    h = 32
    rw = g["chest_hw"] * 0.84

    path = QPainterPath()
    n = 5
    depths = (0.62, 1.0, 0.82, 1.06, 0.7)
    path.moveTo(CX - rw, top - 8)
    for i in range(n):
        xa = CX - rw + 2 * rw * i / n
        xb = CX - rw + 2 * rw * (i + 1) / n
        path.quadTo((xa + xb) / 2, top + h * depths[i] + 8, xb,
                    top + h * (0.82 if i % 2 else 0.92))
    path.lineTo(CX + rw, top - 8)
    path.quadTo(CX, top - 20, CX - rw, top - 8)
    path.closeSubpath()

    p.save()
    p.setClipPath(_body_path(g))
    gr = QLinearGradient(0, top - 10, 0, top + h + 8)
    gr.setColorAt(0.0, _shade(fur, 0.10))
    gr.setColorAt(0.55, _shade(fur, 0.02))
    gr.setColorAt(1.0, _shade(fur, -0.07))
    _fill_path(p, path, QBrush(gr))
    p.restore()

    # 毛尖上一点点浅色，模拟受光
    p.setPen(_pen(_rgba(light, 70), 1.3))
    p.setBrush(Qt.NoBrush)
    for i in range(n):
        xa = CX - rw + 2 * rw * i / n
        xb = CX - rw + 2 * rw * (i + 1) / n
        mid = (xa + xb) / 2
        yy = top + h * depths[i] + 2
        p.drawLine(QPointF(mid - 1.2, yy), QPointF(mid + 1.2, yy + 3))


def _draw_front_legs(p: QPainter, look: Look, c: dict, g: dict) -> None:
    """前腿：贴着胸口的圆柱形，上粗下细，脚掌比腿略宽、带趾缝。"""
    fur = c["fur"]
    light = _mix(c["light"], c["fur"], 0.42)
    lw = g["leg_w"]
    sy = g["shoulder_y"] + 24
    ground = FEET_Y - 4
    gap = g["chest_hw"] * 0.50
    hanging = look.pose == "dangle"

    if look.pose == "loaf" or g["leg_len"] <= 0.01:
        # 揣手手：只露出两只前爪尖
        for side in (-1, 1):
            px = CX + side * gap * 0.9
            py = g["hip_y"] - 1
            p.setPen(Qt.NoPen)
            p.setBrush(_shade(light, -0.04))
            p.drawEllipse(QRectF(px - lw * 0.55, py - lw * 0.34, lw * 1.1, lw * 0.72))
            p.setPen(_pen(_rgba(c["dark"], 90), 1.1))
            p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(px - lw * 0.34, py - 1, lw * 0.68, lw * 0.52),
                      200 * 16, 140 * 16)
        return

    walk = look.walk
    for side, lift in ((-1, look.leg_l), (1, look.leg_r)):
        phase = look.walk_phase + (0 if side < 0 else math.pi)
        step = math.sin(phase) * walk
        lift = max(lift, max(0.0, step) * 0.6)
        x = CX + side * gap
        foot_y = ground - lift * 19

        if hanging:
            # 悬空：整条腿垂直挂在身体下面，跟着身体一起离地
            sway = math.sin(look.t * 4.5 + (0 if side < 0 else 1.4)) * 3.2
            foot_y = g["hip_y"] + 34
            pts = _bez((x, sy - 4), (x + sway * 0.5, sy + 14),
                       (x + sway, sy + 26), (x + sway * 1.5, foot_y))
        elif lift > 0.55:
            # 举爪舔毛：前爪抬到嘴边
            target_x = CX + side * 8.0
            target_y = g["head_cy"] + g["head_h"] * 0.66
            pts = _bez((x, sy), (x + side * 7, sy - 10),
                       (target_x + side * 4, target_y + 22), (target_x, target_y))
        elif look.pose == "stretch":
            # 伸懒腰：前爪向前伸、贴地，肩部压低
            pts = _bez((x, sy), (x + side * 3, sy + 14),
                       (x + side * 8, 164), (x + side * 11, ground))
            foot_y = ground
        elif look.pose == "crouch":
            pts = _bez((x, sy), (x + side * 2, sy + 10), (x + side * 5, foot_y - 9),
                       (x + side * 6, foot_y))
        elif look.paw_fwd > 0.02:
            reach = look.paw_fwd * 30
            pts = _bez((x, sy), (x - side * 1, sy + 14),
                       (x - side * 2, foot_y - 16 + reach * 0.15),
                       (x - side * 3, foot_y - reach * 0.45))
        else:
            swing = step * 3.4 * (1 if side < 0 else -1)
            mid = sy + (foot_y - sy) * 0.5
            pts = _bez((x, sy), (x + swing * 0.5, mid - 6),
                       (x + swing * 0.85, foot_y - (foot_y - mid) * 0.5),
                       (x + swing, foot_y))

        # 腿投在胸口的阴影（腿长在身体前面的关键线索）
        shadow = QRadialGradient(QPointF(x + side * 1.5, sy + 12), lw * 1.9)
        shadow.setColorAt(0.0, QColor(0, 0, 0, 34))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(shadow))
        p.drawEllipse(QRectF(x - lw * 1.9 + side * 1.5, sy - 6, lw * 3.8, 44))

        # 上端粗、下端略细，肩部自然融进胸口
        leg = _ribbon(pts, lw * 1.55, lw * 1.06, taper_mid=1.02)
        gr = QLinearGradient(x - lw, 0, x + lw, 0)
        gr.setColorAt(0.0, _shade(fur, -0.26))
        gr.setColorAt(0.30, _shade(fur, 0.08))
        gr.setColorAt(0.62, _shade(fur, -0.02))
        gr.setColorAt(0.88, _shade(fur, -0.24))
        gr.setColorAt(1.0, _shade(fur, -0.34))
        _fill_path(p, leg, QBrush(gr))
        p.setPen(_pen(_rgba(_shade(fur, -0.42), 30), 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawPath(leg)

        # 脚掌：比腿粗一圈，底下有一道接触阴影
        paw_x = pts[-1][0]
        paw_y = pts[-1][1] + 1.2
        pw = lw * 0.84
        ph = lw * 0.56
        p.setPen(Qt.NoPen)
        g2 = QLinearGradient(0, paw_y - ph, 0, paw_y + ph)
        g2.setColorAt(0.0, _shade(light, 0.06))
        g2.setColorAt(0.66, _shade(light, -0.02))
        g2.setColorAt(1.0, _shade(light, -0.24))
        p.setBrush(QBrush(g2))
        p.drawEllipse(QRectF(paw_x - pw, paw_y - ph, pw * 2, ph * 2))
        # 趾缝
        p.setPen(_pen(_rgba(c["dark"], 120), 1.1))
        p.setBrush(Qt.NoBrush)
        for k in (-0.46, 0.0, 0.46):
            p.drawLine(QPointF(paw_x + k * pw, paw_y + ph * 0.05),
                       QPointF(paw_x + k * pw, paw_y + ph * 0.68))
        if not hanging:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 26))
            p.drawEllipse(QRectF(paw_x - pw * 1.06, paw_y + ph * 0.55, pw * 2.12, 4.2))


def _draw_raised_paw(p: QPainter, look: Look, c: dict, g: dict) -> None:
    """舔毛时抬起来的那只前爪：前臂从胸前弯上来，爪子按在腮边。"""
    lift = max(look.leg_l, look.leg_r)
    if lift <= 0.55 or look.pose in ("dangle", "loaf"):
        return
    side = 1 if look.leg_r >= look.leg_l else -1
    lw = g["leg_w"]
    hw, hh = g["head_w"], g["head_h"]
    paw_x = g["head_cx"] + side * hw * 0.52
    paw_y = g["head_cy"] + hh * 0.30
    x = CX + side * g["chest_hw"] * 0.54
    sy = g["shoulder_y"] + 46
    pts = _bez((x, sy), (x + side * 7.5, sy - 22),
               (paw_x + side * 6.5, paw_y + 26), (paw_x, paw_y))

    leg = _ribbon(pts, lw * 1.22, lw * 0.95, taper_mid=1.04)
    gr = QLinearGradient(x - lw, 0, x + lw, 0)
    gr.setColorAt(0.0, _shade(c["fur"], -0.28))
    gr.setColorAt(0.32, _shade(c["fur"], 0.10))
    gr.setColorAt(0.72, _shade(c["fur"], -0.04))
    gr.setColorAt(1.0, _shade(c["fur"], -0.32))
    _fill_path(p, leg, QBrush(gr))
    p.setPen(_pen(_rgba(_shade(c["fur"], -0.42), 46), 1.0))
    p.setBrush(Qt.NoBrush)
    p.drawPath(leg)

    # 爪垫
    p.setPen(Qt.NoPen)
    paw_c = _mix(c["light"], c["fur"], 0.40)
    pg = QRadialGradient(QPointF(paw_x, paw_y - 1), lw * 0.95)
    pg.setColorAt(0.0, _shade(paw_c, 0.06))
    pg.setColorAt(1.0, _shade(paw_c, -0.18))
    p.setBrush(QBrush(pg))
    p.drawEllipse(QRectF(paw_x - lw * 0.72, paw_y - lw * 0.34,
                         lw * 1.44, lw * 0.94))
    p.setPen(_pen(_rgba(c["dark"], 96), 1.0))
    p.setBrush(Qt.NoBrush)
    for k in (-0.40, 0.06, 0.50):
        p.drawLine(QPointF(paw_x + k * lw, paw_y + 0.4),
                   QPointF(paw_x + k * lw, paw_y + lw * 0.34))


def _draw_head(p: QPainter, look: Look, c: dict, g: dict, detail: float) -> None:
    hw, hh = g["head_w"], g["head_h"]
    cx, cy = g["head_cx"], g["head_cy"]
    fur, dark, light = c["fur"], c["dark"], c["light"]

    p.save()
    p.translate(cx, cy)
    p.rotate(look.head_tilt * 7.0 + look.lean * 2.0)
    p.translate(-cx, -cy)

    # ---------------- 耳朵（在头骨之后，先画）
    for side in (-1, 1):
        _draw_ear(p, side, look, c, cx, cy, hw, hh)

    # ---------------- 头骨
    head = _head_path(cx, cy, hw, hh)
    _fill_path(p, head,
               _vgrad(head, _shade(fur, 0.14), fur, _shade(fur, -0.2),
                      cy - hh, cy + hh))
    if detail > 0.6:
        p.save()
        p.setClipPath(head)
        p.setOpacity(0.8)
        p.drawTiledPixmap(head.boundingRect(), _fur_tex(fur))
        p.restore()

    # 面部暗部（下巴、两颊内侧）
    p.save()
    p.setClipPath(head)
    chin = QRadialGradient(QPointF(cx, cy + hh * 0.95), hw * 1.1)
    chin.setColorAt(0.0, _rgba(_shade(dark, -0.1), 60))
    chin.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(chin))
    p.drawRect(head.boundingRect())
    p.restore()

    # 头顶受光
    p.save()
    p.setClipPath(head)
    top = QLinearGradient(0, cy - hh, 0, cy - hh * 0.1)
    top.setColorAt(0.0, QColor(255, 255, 255, 52))
    top.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(QBrush(top))
    p.setPen(Qt.NoPen)
    p.drawRect(head.boundingRect())
    p.restore()

    # 轮廓光
    p.save()
    p.setClipPath(head)
    p.translate(2.2, 2.2)
    p.setPen(_pen(QColor(255, 250, 238, 54), 2.6))
    p.setBrush(Qt.NoBrush)
    p.drawPath(head)
    p.restore()

    # 额头花纹
    _draw_forehead(p, look, c, cx, cy, hw, hh)

    # 口鼻：两瓣胡须垫（柔边，不要贴纸感的椭圆）+ 下巴
    pad_w, pad_h = hw * 0.25, hh * 0.20
    for side in (-1, 1):
        mx = cx + side * hw * 0.21
        my = cy + hh * 0.46
        mg = QRadialGradient(QPointF(mx, my - pad_h * 0.2), pad_w * 1.6)
        mg.setColorAt(0.0, _rgba(light, 240))
        mg.setColorAt(0.62, _rgba(light, 196))
        mg.setColorAt(1.0, _rgba(light, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(mg))
        p.drawEllipse(QRectF(mx - pad_w * 1.6, my - pad_h * 1.7,
                             pad_w * 3.2, pad_h * 3.2))
    # 下巴
    cg = QRadialGradient(QPointF(cx, cy + hh * 0.68), hw * 0.30)
    cg.setColorAt(0.0, _rgba(light, 220))
    cg.setColorAt(1.0, _rgba(light, 0))
    p.setBrush(QBrush(cg))
    p.drawEllipse(QRectF(cx - hw * 0.30, cy + hh * 0.52, hw * 0.60, hh * 0.32))
    # 鼻梁两侧的阴影，把口鼻从脸颊上"分"出来
    for side in (-1, 1):
        sg = QRadialGradient(QPointF(cx + side * hw * 0.42, cy + hh * 0.30),
                             hw * 0.34)
        sg.setColorAt(0.0, _rgba(_shade(fur, -0.22), 62))
        sg.setColorAt(1.0, _rgba(_shade(fur, -0.22), 0))
        p.setBrush(QBrush(sg))
        p.drawEllipse(QRectF(cx + side * hw * 0.42 - hw * 0.34,
                             cy + hh * 0.30 - hh * 0.30,
                             hw * 0.68, hh * 0.60))

    # 耳根下方一小撮毛，打破轮廓的圆滑
    p.setPen(Qt.NoPen)
    for side in (-1, 1):
        spike = QPainterPath()
        bx = cx + side * hw * 0.86
        by = cy - hh * 0.28
        spike.moveTo(bx, by - 3.0)
        spike.quadTo(bx + side * 5.0, by + 1.0, bx + side * 3.0, by + 6.0)
        spike.quadTo(bx - side * 1.0, by + 2.0, bx, by - 3.0)
        spike.closeSubpath()
        p.setBrush(_rgba(_shade(fur, -0.06), 210))
        p.drawPath(spike)

    # 脸颊两侧的短毛（沿着下缘，不会在额头上留下痕迹）
    _fur_edge(p, head, fur, count=int(16 * detail), length=1.8, seed=7,
              alpha=110, only_bottom=True)

    # ---------------- 五官
    _draw_eyes(p, look, c, cx, cy, hw, hh)
    _draw_nose_mouth(p, look, c, cx, cy, hw, hh)
    _draw_whiskers(p, look, c, cx, cy, hw, hh)

    # 腮红（只在很亲密时出现）
    if look.emotion in ("love", "happy") and look.purr > 0.3:
        p.setPen(Qt.NoPen)
        p.setBrush(_rgba(c["blush"], 70))
        p.drawEllipse(QRectF(cx - hw * 0.95, cy + hh * 0.28, hw * 0.42, hh * 0.26))
        p.drawEllipse(QRectF(cx + hw * 0.53, cy + hh * 0.28, hw * 0.42, hh * 0.26))

    p.restore()


def _draw_ear(p: QPainter, side: int, look: Look, c: dict,
              cx: float, cy: float, hw: float, hh: float) -> None:
    """耳朵：宽底的三角形，尖端圆润；飞机耳时整体外翻下塌。"""
    back = look.ear_back
    fur, dark = c["fur"], c["dark"]

    ax, ay = cx + side * hw * 0.14, cy - hh * 0.62          # 内侧耳根
    bx, by = cx + side * hw * 0.99, cy - hh * 0.24          # 外侧耳根
    tx = cx + side * hw * (0.74 + 0.10 * back)
    ty = cy - hh * (1.46 - 0.68 * back)

    path = QPainterPath()
    path.moveTo(ax, ay)
    # 前缘（内侧）
    path.cubicTo(cx + side * hw * 0.32, cy - hh * (1.14 - 0.28 * back),
                 tx - side * hw * 0.12, ty + hh * 0.16, tx, ty)
    # 后缘（外侧）
    path.cubicTo(tx + side * hw * 0.16, ty + hh * 0.22,
                 bx - side * hw * 0.04, by - hh * 0.14, bx, by)
    # 耳根（被头骨盖住）
    path.cubicTo(cx + side * hw * 0.62, cy - hh * (0.30 + 0.12 * back),
                 cx + side * hw * 0.36, cy - hh * 0.48, ax, ay)
    path.closeSubpath()

    gr = QLinearGradient(ax, ay, bx, ty)
    gr.setColorAt(0.0, _shade(fur, 0.02))
    gr.setColorAt(0.55, fur)
    gr.setColorAt(1.0, _shade(dark, 0.04))
    _fill_path(p, path, QBrush(gr))
    p.setPen(_pen(_rgba(dark, 96), 1.3))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)

    # 耳内：粉色，靠近尖端更浅
    inner = QPainterPath()
    ia = (cx + side * hw * 0.30, cy - hh * 0.58)
    itx = cx + side * hw * (0.72 + 0.08 * back)
    ity = cy - hh * (1.28 - 0.60 * back)
    ib = (cx + side * hw * 0.86, cy - hh * 0.34)
    inner.moveTo(*ia)
    inner.cubicTo(cx + side * hw * 0.38, cy - hh * (1.04 - 0.26 * back),
                  itx - side * hw * 0.14, ity + hh * 0.12, itx, ity)
    inner.cubicTo(itx + side * hw * 0.16, ity + hh * 0.22,
                  ib[0] - side * hw * 0.02, ib[1] - hh * 0.12, *ib)
    inner.cubicTo(cx + side * hw * 0.70, cy - hh * 0.52,
                  cx + hw * 0.40 * side, cy - hh * 0.50, *ia)
    inner.closeSubpath()
    p.setPen(Qt.NoPen)
    eg = QLinearGradient(0, cy - hh * 1.25, 0, cy - hh * 0.35)
    eg.setColorAt(0.0, _rgba(_shade(c["ear"], -0.14), 225))
    eg.setColorAt(1.0, _rgba(c["ear"], 150))
    p.setBrush(QBrush(eg))
    p.drawPath(inner)

    # 耳内绒毛
    p.setPen(_pen(_rgba(_shade(c["light"], -0.02), 165), 1.1))
    p.setBrush(Qt.NoBrush)
    for k in (0.0, 0.22, 0.44, 0.66):
        x = cx + side * hw * (0.44 + 0.34 * k)
        y = cy - hh * (0.60 + 0.72 * k)
        p.drawLine(QPointF(x, y), QPointF(x + side * 1.8, y - 3.4))


def _draw_forehead(p: QPainter, look: Look, c: dict,
                   cx: float, cy: float, hw: float, hh: float) -> None:
    pat = c["pattern"]
    if pat == "tabby":
        p.setPen(_pen(_rgba(c["dark"], 74), 1.8))
        p.setBrush(Qt.NoBrush)
        # 经典 "M" 纹（用曲线，别做成折线）
        mid = QPainterPath(QPointF(cx - hw * 0.30, cy - hh * 0.98))
        mid.quadTo(cx - hw * 0.22, cy - hh * 0.74, cx - hw * 0.09, cy - hh * 0.90)
        mid.quadTo(cx, cy - hh * 0.72, cx + hw * 0.09, cy - hh * 0.90)
        mid.quadTo(cx + hw * 0.22, cy - hh * 0.74, cx + hw * 0.30, cy - hh * 0.98)
        p.drawPath(mid)
        # 两侧短纹
        for side in (-1, 1):
            path = QPainterPath(QPointF(cx + side * hw * 0.52, cy - hh * 0.88))
            path.quadTo(cx + side * hw * 0.66, cy - hh * 0.68,
                        cx + side * hw * 0.70, cy - hh * 0.48)
            p.drawPath(path)
    elif pat == "tuxedo":
        # 额头的黑帽
        p.setPen(Qt.NoPen)
        p.setBrush(_rgba(c["dark"], 210))
        cap = QPainterPath()
        cap.moveTo(cx - hw * 0.86, cy - hh * 0.5)
        cap.cubicTo(cx - hw * 0.8, cy - hh * 1.05, cx + hw * 0.8, cy - hh * 1.05,
                    cx + hw * 0.86, cy - hh * 0.5)
        cap.cubicTo(cx + hw * 0.4, cy - hh * 0.72, cx + hw * 0.18, cy - hh * 0.6,
                    cx + hw * 0.12, cy - hh * 0.42)
        cap.cubicTo(cx + hw * 0.02, cy - hh * 0.66, cx - hw * 0.3, cy - hh * 0.74,
                    cx - hw * 0.86, cy - hh * 0.5)
        cap.closeSubpath()
        p.drawPath(cap)


def _eye_params(look: Look) -> dict:
    """把情绪翻译成眼裂开合、瞳孔、眉毛角度。"""
    emo = look.emotion
    if look.sleeping:
        emo = "sleepy"
    p = {"open": 1.0, "pupil": 0.42, "brow": 0.0, "lower": 0.0, "tilt": 0.0}
    if emo == "happy":
        p.update(open=0.38, pupil=0.42, brow=-0.12, lower=0.5)
    elif emo == "love":
        p.update(open=0.46, pupil=0.66, brow=-0.1, lower=0.45)
    elif emo == "sleepy":
        p.update(open=0.14, pupil=0.5, brow=0.05, lower=0.2)
    elif emo == "sad":
        p.update(open=1.05, pupil=0.6, brow=0.5, lower=-0.1)
    elif emo == "angry":
        p.update(open=0.68, pupil=0.12, brow=-0.75, lower=0.0)
    elif emo == "eat":
        p.update(open=0.5, pupil=0.55, brow=0.0, lower=0.35)
    elif emo == "dizzy":
        p.update(open=0.2, pupil=0.5, brow=0.15, lower=0.0)
    elif emo == "scared":
        p.update(open=1.15, pupil=1.0, brow=0.35, lower=-0.2)
    if look.blink > 0.4:
        p["open"] = 0.04
    p["open"] = min(p["open"], look.eye_open if look.eye_open < 0.99 else 1.0)
    return p


def _draw_eyes(p: QPainter, look: Look, c: dict,
               cx: float, cy: float, hw: float, hh: float) -> None:
    ep = _eye_params(look)
    open_k = max(0.05, ep["open"])
    ex_off = hw * 0.43
    ey = cy - hh * 0.04
    ew, eh = hw * 0.238, hh * 0.240
    lx = look.look_x * ew * 0.20
    ly = look.look_y * eh * 0.14

    for side in (-1, 1):
        ex = cx + side * ex_off
        top = ey - eh * open_k * 0.95
        bot = ey + eh * open_k * 0.62

        # 杏仁形：内眼角低、外眼角略高
        pts = [
            (ex - side * ew, ey + eh * 0.06 * open_k),
            (ex - side * ew * 0.42, top + eh * 0.14 * open_k),
            (ex + side * ew * 0.30, top),
            (ex + side * ew * 0.80, top + eh * 0.28 * open_k),
            (ex + side * ew, ey - eh * 0.12 * open_k),
            (ex + side * ew * 0.66, bot - eh * 0.04 * open_k),
            (ex + side * ew * 0.10, bot),
            (ex - side * ew * 0.50, bot - eh * 0.08 * open_k),
            (ex - side * ew * 0.86, ey + eh * 0.30 * open_k),
        ]
        shape = _smooth(pts, tension=0.95)

        # 眼窝：先铺一层浅阴影，眼球才不会像贴上去的
        p.setPen(Qt.NoPen)
        p.setBrush(_rgba(_shade(c["fur"], -0.25), 46))
        p.drawEllipse(QRectF(ex - ew * 1.30, ey - eh * 1.10,
                             ew * 2.60, eh * 2.30))

        # 虹膜铺满整个眼裂（猫几乎不露眼白）
        p.save()
        p.setClipPath(shape)
        base = c["eye"]
        iris = QRadialGradient(QPointF(ex - side * ew * 0.12 + lx, ey - eh * 0.10 + ly),
                               eh * 1.15)
        iris.setColorAt(0.0, _shade(base, 0.38))
        iris.setColorAt(0.42, base)
        iris.setColorAt(0.86, _shade(base, -0.34))
        iris.setColorAt(1.0, _shade(base, -0.58))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(iris))
        p.drawRect(shape.boundingRect().adjusted(-2, -2, 2, 2))

        if open_k > 0.18:
            pw = ew * (0.15 + 0.22 * ep["pupil"])
            ph = eh * (0.72 + 0.26 * min(1.0, open_k))
            # 虹膜放射纹
            p.setPen(_pen(_rgba(_shade(base, -0.38), 40), 0.8))
            p.setBrush(Qt.NoBrush)
            for k in range(14):
                ang = k / 14 * math.tau
                p.drawLine(QPointF(ex + lx + math.cos(ang) * pw * 0.95,
                                   ey - eh * 0.10 + ly + math.sin(ang) * ph * 0.34),
                           QPointF(ex + lx + math.cos(ang) * ew * 1.24,
                                   ey - eh * 0.10 + ly + math.sin(ang) * eh * 1.10))
            # 竖瞳
            pupil = QPainterPath()
            pupil.moveTo(ex + lx, ey - eh * 0.10 - ph * 0.52 + ly)
            pupil.quadTo(ex + lx + pw * 0.62, ey - eh * 0.10 + ly,
                         ex + lx, ey - eh * 0.10 + ph * 0.52 + ly)
            pupil.quadTo(ex + lx - pw * 0.62, ey - eh * 0.10 + ly,
                         ex + lx, ey - eh * 0.10 - ph * 0.52 + ly)
            p.setPen(Qt.NoPen)
            p.setBrush(_rgba(QColor("#191214"), 244))
            p.drawPath(pupil)
            # 高光
            p.setBrush(QColor(255, 255, 255, 238))
            p.drawEllipse(QRectF(ex - ew * 0.66 + lx, top + eh * 0.10,
                                 ew * 0.30, eh * 0.26))
            p.setBrush(QColor(255, 255, 255, 110))
            p.drawEllipse(QRectF(ex + ew * 0.22, bot - eh * 0.30, ew * 0.18, eh * 0.15))
            if look.emotion == "love":
                p.setBrush(QColor(255, 116, 148, 220))
                p.drawPath(_heart(ex + lx, ey + eh * 0.06, eh * 0.14))
        p.restore()

        # 上眼睑压下来的投影
        p.save()
        p.setClipPath(shape)
        lid_sh = QLinearGradient(0, top - 2, 0, top + eh * 0.80 * open_k)
        lid_sh.setColorAt(0.0, QColor(24, 14, 12, 116))
        lid_sh.setColorAt(1.0, QColor(24, 14, 12, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(lid_sh))
        p.drawRect(shape.boundingRect())
        p.restore()

        # 眼线：整圈一圈很细的深色，上缘更重
        p.setPen(_pen(_rgba(QColor("#2A211F"), 96), 0.9))
        p.setBrush(Qt.NoBrush)
        p.drawPath(shape)
        p.setPen(_pen(_rgba(QColor("#2A211F"), 225), max(1.1, eh * 0.11)))
        lid = QPainterPath()
        lid.moveTo(ex - side * ew * 0.92, ey + eh * 0.16 * open_k)
        lid.cubicTo(ex - side * ew * 0.40, top - eh * 0.10,
                    ex + side * ew * 0.62, top - eh * 0.06,
                    ex + side * ew * 0.98, ey - eh * 0.14 * open_k)
        p.drawPath(lid)

        # 眉毛
        brow = ep["brow"]
        if abs(brow) > 0.05:
            p.setPen(_pen(_rgba(c["dark"], 140), 1.8))
            bx0 = ex - side * ew * 0.10
            by0 = top - eh * 0.62
            p.drawLine(QPointF(bx0, by0 + (0.0 if brow < 0 else 2.0)),
                       QPointF(ex + side * ew * 0.80, by0 + brow * 3.6))


def _draw_nose_mouth(p: QPainter, look: Look, c: dict,
                     cx: float, cy: float, hw: float, hh: float) -> None:
    nose_y = cy + hh * 0.32
    nw, nh = hw * 0.15, hh * 0.105

    # 鼻子：上宽下尖的圆三角，带鼻孔和高光
    nose = QPainterPath()
    nose.moveTo(cx - nw, nose_y - nh * 0.55)
    nose.cubicTo(cx - nw * 0.98, nose_y + nh * 0.28, cx - nw * 0.36,
                 nose_y + nh * 0.92, cx, nose_y + nh * 0.98)
    nose.cubicTo(cx + nw * 0.36, nose_y + nh * 0.92, cx + nw * 0.98,
                 nose_y + nh * 0.28, cx + nw, nose_y - nh * 0.55)
    nose.cubicTo(cx + nw * 0.52, nose_y - nh * 1.02, cx - nw * 0.52,
                 nose_y - nh * 1.02, cx - nw, nose_y - nh * 0.55)
    nose.closeSubpath()
    ng = QLinearGradient(0, nose_y - nh, 0, nose_y + nh)
    ng.setColorAt(0.0, _shade(c["nose"], 0.20))
    ng.setColorAt(0.6, c["nose"])
    ng.setColorAt(1.0, _shade(c["nose"], -0.18))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(ng))
    p.drawPath(nose)
    p.setPen(_pen(_rgba(_shade(c["nose"], -0.42), 140), 0.9))
    p.setBrush(Qt.NoBrush)
    p.drawPath(nose)
    p.setPen(Qt.NoPen)
    p.setBrush(_rgba(QColor("#7A4A48"), 165))
    for side in (-1, 1):
        p.drawEllipse(QRectF(cx + side * nw * 0.40 - nw * 0.17,
                             nose_y + nh * 0.18, nw * 0.34, nh * 0.46))
    p.setBrush(QColor(255, 255, 255, 96))
    p.drawEllipse(QRectF(cx - nw * 0.52, nose_y - nh * 0.66, nw * 0.52, nh * 0.32))

    # 人中 + 嘴
    cleft_y = nose_y + nh * 1.02
    my = cleft_y + hh * 0.14
    p.setPen(_pen(_rgba(QColor("#6B4B45"), 170), 1.2))
    p.drawLine(QPointF(cx, cleft_y), QPointF(cx, my))

    mouth = look.mouth
    if mouth > 0.08:
        # 张嘴：上唇平、下唇圆，里面是深色口腔和舌头
        mw = hw * (0.15 + 0.11 * mouth)
        mh = hh * (0.07 + 0.28 * mouth)
        shape = QPainterPath()
        shape.moveTo(cx - mw, my - 0.4)
        shape.quadTo(cx, my - mh * 0.16, cx + mw, my - 0.4)
        shape.cubicTo(cx + mw * 0.96, my + mh * 0.86, cx + mw * 0.52, my + mh * 1.22,
                      cx, my + mh * 1.22)
        shape.cubicTo(cx - mw * 0.52, my + mh * 1.22, cx - mw * 0.96, my + mh * 0.86,
                      cx - mw, my - 0.4)
        shape.closeSubpath()
        p.setPen(_pen(_rgba(QColor("#4A2426"), 200), 1.0))
        p.setBrush(QColor("#6E3538"))
        p.drawPath(shape)
        p.setPen(Qt.NoPen)
        # 上排小门牙
        p.setBrush(QColor(252, 246, 236, 235))
        tw0 = mw * 0.34
        p.drawRoundedRect(QRectF(cx - tw0, my - 0.2, tw0 * 2, mh * 0.26), 1.4, 1.4)
        # 舌头
        p.setBrush(QColor("#D9757E"))
        tw = mw * (0.58 + 0.12 * look.tongue)
        p.drawEllipse(QRectF(cx - tw, my + mh * (0.62 + 0.22 * look.tongue),
                             tw * 2, mh * 0.56))
        p.setBrush(QColor("#E88E96"))
        p.drawEllipse(QRectF(cx - tw * 0.72, my + mh * 0.54, tw * 1.44, mh * 0.26))
    else:
        # 闭嘴：经典的 ω 形嘴
        p.setPen(_pen(_rgba(QColor("#6B4B45"), 195), 1.6))
        p.setBrush(Qt.NoBrush)
        for side in (-1, 1):
            path = QPainterPath(QPointF(cx, my))
            path.cubicTo(cx + side * hw * 0.03, my + hh * 0.10,
                         cx + side * hw * 0.13, my + hh * 0.11,
                         cx + side * hw * 0.19, my + hh * 0.005)
            p.drawPath(path)


def _draw_whiskers(p: QPainter, look: Look, c: dict,
                   cx: float, cy: float, hw: float, hh: float) -> None:
    # 浅色毛上用深色胡须，深色毛上用浅色，保证看得见
    lum = c["fur"].lightness()
    col = _rgba(QColor("#6B5648") if lum > 140 else QColor("#FFF7EA"),
                108 if lum > 140 else 138)
    p.setPen(_pen(col, 0.75))
    p.setBrush(Qt.NoBrush)
    base_y = cy + hh * 0.44
    for side in (-1, 1):
        for i, (dy, ln, curve) in enumerate(((-0.16, 1.02, -4.6),
                                             (0.0, 1.10, 0.6),
                                             (0.16, 1.00, 5.8))):
            x0 = cx + side * hw * 0.30
            y0 = base_y + hh * dy * 0.46
            x1 = cx + side * hw * ln
            y1 = y0 + hh * 0.08 * (i - 1) + curve * 0.40
            path = QPainterPath(QPointF(x0, y0))
            path.quadTo((x0 + x1) / 2, y0 + curve, x1, y1)
            p.drawPath(path)

    # 胡须垫上的小孔
    p.setPen(Qt.NoPen)
    p.setBrush(_rgba(c["dark"], 55))
    for side in (-1, 1):
        for k in range(3):
            p.drawEllipse(QRectF(cx + side * (hw * 0.22 + k * hw * 0.08) - 0.6,
                                 base_y - hh * 0.10 + k * hh * 0.085, 1.3, 1.1))


# ------------------------------------------------------------------ 装饰
def _draw_accessory(p: QPainter, look: Look, c: dict, g: dict) -> None:
    stage = look.stage
    cx = g["head_cx"]
    neck_y = g["head_cy"] + g["head_h"] * 1.14
    half = g["chest_hw"] * 0.62
    if stage == 2:
        # 少年：铃铛项圈
        _draw_collar(p, cx, neck_y, half, c, bell=True)
    elif stage >= 3:
        # 成年：皮质项圈 + 金色名牌
        _draw_collar(p, cx, neck_y + 1, half * 1.03, c, bell=False, tag=True)


def _draw_collar(p: QPainter, cx: float, y: float, half: float,
                 c: dict, bell: bool = False, tag: bool = False) -> None:
    band = QPainterPath()
    band.moveTo(cx - half, y)
    band.cubicTo(cx - half * 0.4, y + 8, cx + half * 0.4, y + 8, cx + half, y)
    band.lineTo(cx + half, y + 7.5)
    band.cubicTo(cx + half * 0.4, y + 15.5, cx - half * 0.4, y + 15.5, cx - half, y + 7.5)
    band.closeSubpath()
    gr = QLinearGradient(0, y, 0, y + 16)
    gr.setColorAt(0.0, QColor("#C6524B"))
    gr.setColorAt(0.45, QColor("#A83C38"))
    gr.setColorAt(1.0, QColor("#7E2C2A"))
    _fill_path(p, band, QBrush(gr))
    p.setPen(_pen(QColor(60, 24, 22, 130), 1.0))
    p.setBrush(Qt.NoBrush)
    p.drawPath(band)
    # 缝线
    p.setPen(_pen(QColor(255, 220, 200, 90), 0.9))
    stitch = QPainterPath(QPointF(cx - half * 0.9, y + 4))
    stitch.cubicTo(cx - half * 0.4, y + 11, cx + half * 0.4, y + 11, cx + half * 0.9, y + 4)
    p.drawPath(stitch)

    if bell:
        by = y + 16
        p.setPen(_pen(QColor("#B8862F"), 1.2))
        p.setBrush(QColor("#F2C14E"))
        p.drawEllipse(QRectF(cx - 6, by - 2, 12, 12))
        p.setPen(_pen(QColor("#B8862F"), 1.0))
        p.drawLine(QPointF(cx - 3, by + 4), QPointF(cx + 3, by + 4))
        p.setBrush(QColor(255, 246, 200, 190))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(cx - 3.6, by + 0.4, 3.4, 3.0))
    if tag:
        ty = y + 17
        p.setPen(_pen(QColor("#B8963F"), 1.1))
        p.setBrush(QColor("#EFD07A"))
        p.drawEllipse(QRectF(cx - 5.5, ty - 3, 11, 11))
        p.setPen(_pen(QColor("#9A7A2E"), 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(cx - 3.2, ty - 1.0, 6.4, 6.4))


# ------------------------------------------------------------------ 蛋
def _draw_egg(p: QPainter, look: Look, palette: dict, detail: float) -> None:
    c = _colors(palette)
    p.save()
    p.translate(CX, FEET_Y)
    wob = math.sin(look.t * 7.0) * (3.4 if look.egg_crack else 1.2)
    p.rotate(wob)
    p.translate(-CX, -FEET_Y)

    shell = QColor("#FBF3E4")
    edge = QColor("#D9BE96")
    path = QPainterPath()
    path.moveTo(CX, 62)
    path.cubicTo(CX + 30, 62, CX + 47, 96, CX + 47, 126)
    path.cubicTo(CX + 47, 160, CX + 26, 180, CX, 180)
    path.cubicTo(CX - 26, 180, CX - 47, 160, CX - 47, 126)
    path.cubicTo(CX - 47, 96, CX - 30, 62, CX, 62)
    path.closeSubpath()

    gr = QRadialGradient(QPointF(CX - 14, 96), 76)
    gr.setColorAt(0.0, QColor("#FFFDF7"))
    gr.setColorAt(0.62, shell)
    gr.setColorAt(1.0, QColor("#DCC6A4"))
    _fill_path(p, path, QBrush(gr))

    # 斑点
    p.save()
    p.setClipPath(path)
    p.setPen(Qt.NoPen)
    for (x, y, r, a) in ((80, 104, 7, 40), (120, 118, 9, 34), (96, 150, 8, 26),
                         (122, 152, 5, 30), (74, 140, 4, 24)):
        p.setBrush(QColor(196, 168, 130, a))
        p.drawEllipse(QRectF(x - r, y - r * 0.8, r * 2, r * 1.6))
    # 底部接触阴影
    p.setBrush(QColor(120, 95, 70, 34))
    p.drawEllipse(QRectF(CX - 40, 162, 80, 30))
    p.restore()

    # 裂纹
    p.setPen(_pen(edge, 2.4))
    p.setBrush(Qt.NoBrush)
    if look.egg_crack >= 1:
        cpath = QPainterPath(QPointF(74, 92))
        for pt in ((86, 100), (76, 112), (92, 118)):
            cpath.lineTo(*pt)
        p.drawPath(cpath)
    if look.egg_crack >= 2:
        cpath2 = QPainterPath(QPointF(126, 88))
        for pt in ((114, 100), (126, 108), (112, 122), (124, 130)):
            cpath2.lineTo(*pt)
        p.drawPath(cpath2)
    if look.egg_crack >= 3:
        cpath3 = QPainterPath(QPointF(70, 126))
        for pt in ((86, 132), (74, 144), (90, 150)):
            cpath3.lineTo(*pt)
        p.drawPath(cpath3)

    # 高光
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 120))
    p.drawEllipse(QRectF(CX - 30, 82, 15, 30))
    p.setBrush(QColor(255, 255, 255, 60))
    p.drawEllipse(QRectF(CX + 18, 120, 8, 16))
    p.restore()


def _heart(cx: float, cy: float, s: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(cx, cy + s * 0.75)
    path.cubicTo(cx - s * 1.5, cy - s * 0.25, cx - s * 0.55, cy - s * 1.15, cx, cy - s * 0.35)
    path.cubicTo(cx + s * 0.55, cy - s * 1.15, cx + s * 1.5, cy - s * 0.25, cx, cy + s * 0.75)
    path.closeSubpath()
    return path


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
