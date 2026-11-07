"""主窗口：宠物本体、动画循环、鼠标交互、右键菜单、托盘。"""
from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QCursor,
    QGuiApplication,
    QIcon,
    QPainter,
)
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from . import config, dialogue, painter, props
from .bubble import Bubble
from .chat_panel import ChatPanel
from .effects import Effects
from .llm import LLMWorker
from .settings_panel import SettingsPanel
from .state import PetState, clamp
from .status_panel import StatusPanel

CANVAS = 200.0
# 窗口只包住宠物本体，减少透明区域挡住桌面点击
WIN_W = 168.0
WIN_H = 192.0
OFF_X = -(CANVAS - WIN_W) / 2.0   # -20
OFF_Y = -(CANVAS - WIN_H) / 2.0   # -4


class PetWindow(QWidget):
    def __init__(self, state: PetState, settings: dict):
        super().__init__(None, self._flags(settings))

        self.state = state
        self.settings = settings
        self.palette = config.palette_of(settings)

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowTitle(config.APP_NAME)
        self.setToolTip("")

        self.look = painter.Look(stage=state.stage)
        self.effects = Effects()
        self.bubble = Bubble()

        self._t = 0.0
        self._s = float(settings.get("scale", 1.0))
        self._last_frame = time.time()
        self._blink_at = time.time() + random.uniform(2, 5)
        self._blink_start = -1.0
        self._emotion = "normal"
        self._emotion_until = 0.0
        self._action: dict | None = None
        self._spawn_acc = 0.0
        self._hop_start = -1.0
        self._wet = 0.0
        self._idle_next = time.time() + random.uniform(20, 40)
        self._shake_until = 0.0

        self._dragging = False
        self._press_global = QPoint()
        self._press_win = QPoint()
        self._moved = False

        self._wander_target: float | None = None
        self._wander_next = time.time() + random.uniform(12, 28)

        self._chat_panel: ChatPanel | None = None
        self._status_panel: StatusPanel | None = None
        self._settings_panel: SettingsPanel | None = None
        self._llm_worker: LLMWorker | None = None
        self._history: list[dict] = []

        self._apply_geometry()

        # 计时器
        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(33)
        self._frame_timer.timeout.connect(self._on_frame)
        self._frame_timer.start()

        self._stat_timer = QTimer(self)
        self._stat_timer.setInterval(5000)
        self._stat_timer.timeout.connect(self._on_stat_tick)
        self._stat_timer.start()
        self._last_tick = time.time()

        self._save_timer = QTimer(self)
        self._save_timer.setInterval(30000)
        self._save_timer.timeout.connect(self.state.save)
        self._save_timer.start()

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle_chatter)
        self._schedule_idle()

        self._setup_tray()
        QTimer.singleShot(700, self._greet)

    # ---------------------------------------------------------------- 初始化
    @staticmethod
    def _flags(settings: dict):
        f = Qt.FramelessWindowHint | Qt.Tool
        if settings.get("always_on_top", True):
            f |= Qt.WindowStaysOnTopHint
        return f

    def _apply_geometry(self) -> None:
        scale = float(self.settings.get("scale", 1.0))
        self._s = scale
        w, h = int(WIN_W * scale), int(WIN_H * scale)
        self.setFixedSize(w, h)

        screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        x, y = self.state.pos.get("x"), self.state.pos.get("y")
        if x is None or y is None or not self._on_screen(int(x), int(y), avail):
            x = avail.right() - w - 40
            y = avail.bottom() - h - 20
        self.move(int(x), int(y))

    @staticmethod
    def _on_screen(x: int, y: int, avail) -> bool:
        return (avail.left() - 200 < x < avail.right() + 200
                and avail.top() - 200 < y < avail.bottom() + 200)

    def _setup_tray(self) -> None:
        icon = QIcon(painter.tray_icon_pixmap(64, self.palette))
        self.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip(config.APP_NAME)
        menu = QMenu()
        menu.setStyleSheet(self._menu_style())
        act_show = QAction("显示 / 隐藏", menu)
        act_show.triggered.connect(self.toggle_visible)
        act_chat = QAction("聊聊天", menu)
        act_chat.triggered.connect(self.open_chat)
        act_status = QAction("看看状态", menu)
        act_status.triggered.connect(self.open_status)
        act_settings = QAction("设置", menu)
        act_settings.triggered.connect(self.open_settings)
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self.quit_app)
        for a in (act_show, act_chat, act_status, act_settings):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggle_visible()

    def _menu_style(self) -> str:
        fam = config.app_font_family()[0]
        return f"""
            QMenu {{ font-family: "{fam}"; font-size: 12px; background: #FFFDF8;
                     border: 1px solid #F0D9BB; border-radius: 10px; padding: 6px; }}
            QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 6px; color: #4A3B34; }}
            QMenu::item:selected {{ background: #FFF0DC; }}
            QMenu::item:disabled {{ color: #B7A695; }}
            QMenu::separator {{ height: 1px; background: #F2E2CD; margin: 4px 8px; }}
        """

    # ---------------------------------------------------------------- 问候
    def _greet(self) -> None:
        hour = time.localtime().tm_hour
        if not self.state.hatched:
            self._speak("（蛋轻轻晃了一下）……好像有什么在里面动？", "normal", 5000)
            return
        if self.state.sleeping:
            return
        if 5 <= hour < 11:
            kind = "morning"
        elif hour >= 22 or hour < 5:
            kind = "night"
        else:
            return
        text, emo = dialogue.event_line(kind, self.state, self.settings.get("owner_name", "主人"))
        self._speak(text, emo, 5000)

    # ---------------------------------------------------------------- 绘制
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        s = getattr(self, "_s", 1.0)
        rect = QRectF(OFF_X * s, OFF_Y * s, CANVAS * s, CANVAS * s)
        painter.draw_pet(p, rect, self.look, self.palette)

        # 互动道具（饭盆、毛线球等）画在宠物前面
        if self.look.prop:
            p.save()
            p.translate(OFF_X * s, OFF_Y * s)
            p.scale(s, s)
            props.draw_props(p, self.look, self.palette)
            p.restore()

        p.save()
        p.translate(OFF_X * s, OFF_Y * s)
        p.scale(s, s)
        self.effects.draw(p)
        p.restore()

    # ---------------------------------------------------------------- 每帧
    def _on_frame(self) -> None:
        now = time.time()
        dt = min(0.1, now - self._last_frame)
        self._last_frame = now
        self._t += dt
        lk = self.look

        lk.t = self._t
        lk.stage = self.state.stage
        lk.egg_crack = self.state.egg_crack

        # 姿态参数每帧归零，由下面的动作重新设置
        lk.pose = "sit"
        lk.head_down = 0.0
        lk.head_dx = 0.0
        lk.head_dy = 0.0
        lk.head_tilt = 0.0
        lk.ear_back = 0.0
        lk.leg_l = 0.0
        lk.leg_r = 0.0
        lk.paw_fwd = 0.0
        lk.walk = 0.0
        lk.tongue = 0.0
        lk.hand = 0.0
        lk.purr = 0.0
        lk.prop = ""
        lk.extra = {}
        lk.mouth = 0.0
        lk.eating = False
        lk.washing = False
        lk.tail_up = 0.0
        lk.tail_curl = 0.0
        lk.squash = 0.0
        lk.lean = 0.0
        lk.bob = 0.0

        if now < getattr(self, "_squash_until", 0.0):
            lk.squash = 0.16

        # 洗完澡慢慢变干
        if self._wet > 0.01:
            self._wet = max(0.0, self._wet - dt * 0.05)
        lk.wet = self._wet

        # 呼吸
        speed = 0.62 if self.state.sleeping else 1.0
        lk.breath = math.sin(self._t * 1.6 * speed)

        # 眨眼
        if self._blink_start > 0:
            if now - self._blink_start > 0.16:
                self._blink_start = -1.0
                lk.blink = 0.0
            else:
                lk.blink = 1.0
        elif now > self._blink_at and not self.state.sleeping:
            self._blink_start = now
            self._blink_at = now + random.uniform(2.2, 6.5)
            lk.blink = 1.0
        else:
            lk.blink = 0.0

        # 尾巴
        lk.tail = math.sin(self._t * (0.7 if self.state.sleeping else 1.35))

        # 跳跃（动作里置位 _hop_start）
        if self._hop_start > 0:
            k = (now - self._hop_start) / 0.42
            if k >= 1:
                self._hop_start = -1.0
                lk.jump = 0.0
            else:
                lk.jump = math.sin(math.pi * k) * 0.55
        else:
            lk.jump = 0.0

        # 眼睛跟随鼠标
        lk.sleeping = self.state.sleeping
        if self.state.sleeping:
            lk.look_x, lk.look_y = 0.0, 0.0
        else:
            g = QCursor.pos()
            cx = self.x() + self.width() / 2
            cy = self.y() + self.height() * 0.45
            dx, dy = g.x() - cx, g.y() - cy
            dist = math.hypot(dx, dy)
            if dist < 420:
                lk.look_x = clamp(dx / 180.0, -1, 1)
                lk.look_y = clamp(dy / 260.0, -1, 1)
            else:
                lk.look_x *= 0.9
                lk.look_y *= 0.9

        # 情绪
        if now > self._emotion_until:
            self._emotion = self._base_emotion()
        lk.emotion = self._emotion

        # 动作：会覆盖姿态、情绪、道具
        self._update_action(now, dt)

        # 走动（走路会覆盖腿的摆动）
        self._update_wander(dt)

        # 睡觉冒 Z
        if self.state.sleeping and not self._action:
            self._spawn_acc += dt
            if self._spawn_acc > 1.1:
                self._spawn_acc = 0.0
                self.effects.zzz()
                lk.tail = math.sin(self._t * 0.7) * 0.7

        self.effects.update(dt)
        self.update()

    # ---------------------------------------------------------------- 动作
    def _base_emotion(self) -> str:
        """没在演动作时，按属性算出来的情绪基线。"""
        s = self.state.stats
        if not self.state.hatched:
            return "normal"
        if self.state.sleeping:
            return "sleepy"
        if s["mood"] < 26 or s["hunger"] < 18:
            return "sad"
        if s["energy"] < 20:
            return "sleepy"
        if s["clean"] < 20:
            return "dizzy"
        if s["mood"] > 80 and s["hunger"] > 45:
            return "happy"
        return "normal"

    @staticmethod
    def _ramp(a: float, b: float, x: float) -> float:
        """0→1 的平滑过渡。"""
        if x <= a:
            return 0.0
        if x >= b:
            return 1.0
        t = (x - a) / (b - a)
        return t * t * (3 - 2 * t)

    def _start_action(self, kind: str, dur: float, **data) -> None:
        self._action = {"kind": kind, "start": time.time(), "dur": dur, **data}
        self._wander_target = None
        self._spawn_acc = 0.0

    def _update_action(self, now: float, dt: float) -> None:
        lk = self.look

        # 被拎起来：四脚悬空、飞机耳、瞳孔放大
        if self._dragging and self._moved:
            lk.pose = "dangle"
            lk.emotion = "scared"
            lk.ear_back = 0.85
            lk.tail_curl = 0.9
            lk.leg_l = 0.45
            lk.leg_r = 0.55
            return

        # 睡觉：趴卧、收爪、闭眼
        if self.state.sleeping:
            lk.pose = "loaf"
            lk.emotion = "sleepy"
            lk.tail_curl = 0.55
            lk.breath = math.sin(self._t * 0.95)
            return

        act = self._action
        if act is None:
            if now >= self._idle_next and self._can_idle():
                self._random_idle()
                act = self._action
            if act is None:
                return

        p = (now - act["start"]) / max(0.02, act["dur"])
        if p >= 1.0:
            kind = act["kind"]
            self._action = None
            if kind == "wash":
                self._wet = max(self._wet, 0.8)
                self.effects.shake_sparkles(8)
            if kind == "pat":
                self.set_emotion(act.get("emotion", "happy"), 2.0)
            return

        kind = act["kind"]
        if kind == "eat":
            self._act_eat(p, dt, act)
        elif kind == "play":
            self._act_play(p, dt, act)
        elif kind == "wash":
            self._act_wash(p, dt)
        elif kind == "pat":
            self._act_pat(p)
        elif kind == "groom":
            self._act_groom(p)
        elif kind == "yawn":
            self._act_yawn(p)
        elif kind == "stretch":
            self._act_stretch(p)
        elif kind == "look":
            self._act_look(p)

    # ---- 吃东西：低头对着饭盆，一口一口嚼
    def _act_eat(self, p: float, dt: float, act: dict) -> None:
        lk = self.look
        lk.emotion = "eat"
        down = self._ramp(0.0, 0.18, p) * (1.0 - self._ramp(0.88, 1.0, p))
        lk.pose = "eat" if down > 0.2 else "sit"
        lk.head_down = down * 0.35
        lk.head_dy = down * 3.0
        lk.prop = "bowl"
        lk.prop_t = min(1.0, p * 1.05)
        lk.extra = {"food_color": act.get("food_color", "#E8A15C")}
        if 0.14 < p < 0.9:
            lk.mouth = 0.35 + 0.5 * abs(math.sin(self._t * 12))
            self._spawn_acc += dt
            if self._spawn_acc > 0.24:
                self._spawn_acc = 0.0
                self.effects.crumb_at(100 + random.uniform(-6, 6), 166,
                                      QColor(act.get("food_color", "#E8A15C")))
        lk.tail = math.sin(self._t * 2.4) * 0.8

    # ---- 玩耍：三种玩具有三种动作
    def _act_play(self, p: float, dt: float, act: dict) -> None:
        lk = self.look
        game = act.get("game", "yarn")
        lk.emotion = "happy"

        if game == "yarn":
            lk.prop = "yarn"
            # 毛线球被拨来拨去
            bx = math.sin(p * math.pi * 2.4) * 34
            lk.extra = {"yarn_x": bx}
            lk.prop_t = p
            if p < 0.22:
                lk.pose = "crouch"
                lk.head_down = 0.55
                lk.tail_up = 1.0
                lk.tail = math.sin(self._t * 9) * 0.7
            elif p < 0.52:
                k = (p - 0.22) / 0.30
                lk.jump = math.sin(math.pi * k) * 0.75
                lk.paw_fwd = math.sin(math.pi * k)
                lk.head_down = 0.35
                lk.leg_l = 0.7
                lk.leg_r = 0.55
            else:
                lk.paw_fwd = max(0.0, math.sin((p - 0.52) * 18)) * 0.8
                lk.leg_r = max(0.0, math.sin((p - 0.52) * 18)) * 0.8
                lk.head_down = 0.25
            if p > 0.3 and int(p * 10) % 3 == 0:
                self._spawn_acc += dt
                if self._spawn_acc > 0.3:
                    self._spawn_acc = 0.0
                    self.effects.sparkles(3)

        elif game == "wand":
            lk.prop = "wand"
            ang = math.sin(p * math.pi * 3.2) * 26
            lk.extra = {"wand_angle": ang}
            lk.prop_t = p
            lk.head_dx = clamp(ang * 0.16, -6, 6)
            lk.head_down = 0.12 + 0.16 * abs(math.sin(p * math.pi * 3.2))
            bat = math.sin(p * math.pi * 6.4)
            lk.leg_l = max(0.0, bat) * 0.9
            lk.leg_r = max(0.0, -bat) * 0.9
            if p > 0.35 and p < 0.65:
                lk.jump = math.sin((p - 0.35) / 0.3 * math.pi) * 0.5
            lk.tail = math.sin(self._t * 7) * 0.9

        else:  # 捉迷藏：东张西望然后蹦一下
            lk.head_dx = math.sin(p * math.pi * 3.4) * 7
            lk.head_tilt = math.sin(p * math.pi * 2.2) * 0.6
            lk.look_x = math.sin(p * math.pi * 3.4) * 0.9
            lk.ear_back = -0.15
            if 0.62 < p < 0.82:
                lk.jump = math.sin((p - 0.62) / 0.2 * math.pi) * 0.6
                if int(p * 40) % 4 == 0:
                    self.effects.sparkles(2)
            lk.tail_up = 0.6

    # ---- 洗澡：湿身、抖毛、泡沫
    def _act_wash(self, p: float, dt: float) -> None:
        lk = self.look
        lk.prop = "tub"
        lk.prop_t = p
        self._wet = min(1.0, 0.15 + p * 1.2)
        lk.wet = self._wet
        lk.washing = True
        lk.emotion = "dizzy" if p < 0.75 else "happy"
        if p > 0.12:
            lk.lean = math.sin(self._t * 17) * 0.55
            lk.squash = 0.10
            lk.head_down = 0.3
        if p > 0.8:
            # 抖掉水：高频小幅摆动
            lk.lean = math.sin(self._t * 34) * 0.7
            lk.ear_back = 0.5
        self._spawn_acc += dt
        if self._spawn_acc > 0.14:
            self._spawn_acc = 0.0
            self.effects.bubbles(2)
            self.effects.drops(2)

    # ---- 摸头：手落下来，头往手心里顶
    def _act_pat(self, p: float) -> None:
        lk = self.look
        lk.emotion = "happy" if p < 0.75 else "love"
        down = math.sin(min(1.0, p) * math.pi)
        lk.hand = min(1.0, p * 1.6)
        lk.head_dy = down * 3.4
        lk.head_down = down * 0.18
        lk.ear_back = 0.22 * down
        lk.purr = down
        lk.tail = math.sin(self._t * 3.2) * 0.9
        lk.tail_up = 0.25
        lk.leg_l = lk.leg_r = 0.0

    # ---- 舔毛
    def _act_groom(self, p: float) -> None:
        lk = self.look
        lk.emotion = "happy"
        lk.leg_r = self._ramp(0.0, 0.2, p) * (1 - self._ramp(0.85, 1.0, p))
        lk.head_down = 0.22
        lk.head_tilt = 0.5
        if 0.2 < p < 0.85:
            lk.tongue = 0.5 + 0.5 * math.sin(self._t * 9)
            lk.mouth = 0.12
        lk.tail = math.sin(self._t * 1.1) * 0.6

    # ---- 打哈欠
    def _act_yawn(self, p: float) -> None:
        lk = self.look
        lk.emotion = "sleepy"
        lk.mouth = math.sin(min(1.0, p) * math.pi) * 1.0
        lk.head_dy = -1.5 * math.sin(min(1.0, p) * math.pi)
        lk.eye_open = 1.0 - 0.85 * math.sin(min(1.0, p) * math.pi)
        lk.ear_back = 0.3 * math.sin(min(1.0, p) * math.pi)

    # ---- 伸懒腰
    def _act_stretch(self, p: float) -> None:
        lk = self.look
        k = math.sin(min(1.0, p) * math.pi)
        lk.pose = "stretch"
        lk.head_down = 0.35 * k
        lk.tail_up = 0.8 * k
        lk.emotion = "sleepy"
        lk.paw_fwd = 0.5 * k
        lk.squash = -0.06 * k

    # ---- 东张西望
    def _act_look(self, p: float) -> None:
        lk = self.look
        lk.head_tilt = math.sin(p * math.pi * 2) * 0.7
        lk.head_dx = math.sin(p * math.pi * 2) * 3.5
        lk.look_x = math.sin(p * math.pi * 2) * 0.9
        lk.emotion = "normal"

    def _can_idle(self) -> bool:
        return (self.isVisible() and not self.state.sleeping
                and not self._dragging and not self._action
                and not self.bubble.isVisible()
                and not (self._chat_panel and self._chat_panel.isVisible()))

    def _random_idle(self) -> None:
        self._idle_next = time.time() + random.uniform(24, 55)
        kind = random.choices(
            ["groom", "look", "yawn", "stretch", "tail"],
            weights=[34, 30, 12, 10, 14])[0]
        if kind == "groom":
            self._start_action("groom", random.uniform(2.6, 3.8))
        elif kind == "look":
            self._start_action("look", random.uniform(2.0, 3.0))
        elif kind == "yawn":
            self._start_action("yawn", 1.5)
        elif kind == "stretch":
            self._start_action("stretch", 1.8)
        else:
            self.look.tail_up = 0.9
            self.look.tail_curl = 1.0

    # ---------------------------------------------------------------- 走动
    def _update_wander(self, dt: float) -> None:
        now = time.time()
        allowed = (
            self.settings.get("allow_wander", True)
            and not self.state.sleeping
            and not self._dragging
            and not self.bubble.isVisible()
            and not (self._chat_panel and self._chat_panel.isVisible())
        )
        if not allowed:
            self.look.lean *= 0.85
            return

        if self._wander_target is None and now > self._wander_next:
            if random.random() < 0.35:
                screen = QGuiApplication.screenAt(self.geometry().center()) or QGuiApplication.primaryScreen()
                avail = screen.availableGeometry()
                span = max(80, avail.width() - self.width() - 60)
                self._wander_target = float(avail.left() + 30 + random.random() * span)
            self._wander_next = now + random.uniform(16, 40)

        if self._wander_target is not None:
            x = float(self.x())
            diff = self._wander_target - x
            if abs(diff) < 2:
                self._wander_target = None
                return
            speed = 34.0
            step = math.copysign(min(abs(diff), speed * dt), diff)
            nx = int(round(x + step))
            self.move(nx, self.y())
            # 走路：前腿交替、身体起伏、头随步点轻轻点头
            self.look.walk = 1.0
            self.look.walk_phase += dt * 8.5
            self.look.bob = abs(math.sin(self.look.walk_phase)) * 1.8
            self.look.head_dy = math.sin(self.look.walk_phase * 2) * 0.9
            self.look.lean = clamp(step * 0.35, -1, 1)
            self.look.tail = math.sin(self.look.walk_phase) * 0.5

    # ---------------------------------------------------------------- 互动
    def _speak(self, text: str, emotion: str = "normal", duration: int = 0) -> None:
        if not text:
            return
        self.set_emotion(emotion, 3.2)
        self._wander_target = None
        anchor = self._anchor_rect()
        self.bubble.say(text, anchor, duration or None)

    def say(self, text: str, emotion: str = "normal", duration: int = 0) -> None:
        """对外公开的说话接口（气泡 + 表情）。"""
        self._speak(text, emotion, duration)

    def set_emotion(self, emotion: str, seconds: float = 2.5) -> None:
        self._emotion = emotion or "normal"
        self._emotion_until = time.time() + seconds

    def _anchor_rect(self) -> QRect:
        s = getattr(self, "_s", 1.0)
        return QRect(self.x() + int((46 + OFF_X) * s), self.y() + int((24 + OFF_Y) * s),
                     int(108 * s), int(94 * s))

    def _after_action(self, result: dict) -> None:
        if not result.get("ok"):
            self._speak(result.get("text", ""), result.get("emotion", "normal"))
            return

        self._speak(result.get("text", ""), result.get("emotion", "normal"))

        for lv in result.get("levelups") or []:
            self.effects.sparkles(14)
            QTimer.singleShot(700, lambda: self.effects.hearts_big())
            self._speak(f"我升级了！现在是 {lv} 级！", "happy", 3200)

        for aid in result.get("unlocked") or []:
            name = self.state.achieve_name(aid)
            QTimer.singleShot(1400, lambda n=name: self._speak(f"解锁了新成就：{n}", "happy", 3200))

        if result.get("hatched"):
            self.effects.sparkles(20)
            self.set_emotion("happy", 6)

        self.state.save()
        if self._status_panel and self._status_panel.isVisible():
            self._status_panel.refresh(self.state, self.palette)
        self._update_tray_tip()

    def feed(self, food_id: str) -> None:
        food = config.FOOD_BY_ID.get(food_id)
        if not food:
            return
        res = self.state.feed(food)
        if res.get("ok"):
            self._start_action("eat", 2.6, food_color=food.get("color", "#E8A15C"))
        self._after_action(res)

    def play(self, action_id: str | None = None) -> None:
        pool = config.PLAY_ACTIONS
        action = next((a for a in pool if a["id"] == action_id), random.choice(pool))
        res = self.state.play(action)
        if res.get("ok"):
            game = action.get("id", "yarn")
            if game not in ("yarn", "wand", "hide"):
                game = "yarn"
            dur = {"yarn": 2.8, "wand": 3.2, "hide": 2.6}[game]
            self._start_action("play", dur, game=game)
            self.effects.hearts(4)
        self._after_action(res)

    def wash(self) -> None:
        res = self.state.wash()
        if res.get("ok"):
            self._start_action("wash", 3.2)
            self.effects.bubbles(10)
        self._after_action(res)

    def pat(self) -> None:
        res = self.state.pat()
        if res.get("ok"):
            if self.state.hatched:
                self._start_action("pat", 0.95, emotion=res.get("emotion", "happy"))
                self.effects.hearts(3 if res.get("emotion") != "love" else 6, 100, 62)
            else:
                self._hop_start = time.time()
                self.effects.sparkles(6)
        self._after_action(res)

    def toggle_sleep(self) -> None:
        res = self.state.toggle_sleep()
        self._after_action(res)

    # ---------------------------------------------------------------- 菜单
    def contextMenuEvent(self, event) -> None:  # noqa: N802
        self._wander_target = None
        menu = QMenu(self)
        menu.setStyleSheet(self._menu_style())

        head = QAction(f"{self.state.name}　Lv.{self.state.level}　{self.state.stage_name}", menu)
        head.setEnabled(False)
        menu.addAction(head)
        menu.addSeparator()

        feed_menu = menu.addMenu("喂食")
        feed_menu.setStyleSheet(self._menu_style())
        for food in config.FOODS:
            act = QAction(QIcon(painter.food_pixmap(food["icon"], 32)), food["name"], feed_menu)
            act.setToolTip(food["desc"])
            act.triggered.connect(lambda _=False, fid=food["id"]: self.feed(fid))
            feed_menu.addAction(act)

        play_menu = menu.addMenu("玩耍")
        play_menu.setStyleSheet(self._menu_style())
        for action in config.PLAY_ACTIONS:
            act = QAction(action["name"], play_menu)
            act.triggered.connect(lambda _=False, aid=action["id"]: self.play(aid))
            play_menu.addAction(act)

        act_wash = QAction("洗澡", menu)
        act_wash.triggered.connect(self.wash)
        menu.addAction(act_wash)

        act_sleep = QAction("叫醒它" if self.state.sleeping else "哄它睡觉", menu)
        act_sleep.triggered.connect(self.toggle_sleep)
        menu.addAction(act_sleep)

        act_pat = QAction("摸摸头", menu)
        act_pat.triggered.connect(self.pat)
        menu.addAction(act_pat)

        menu.addSeparator()
        act_chat = QAction("聊聊天", menu)
        act_chat.triggered.connect(self.open_chat)
        menu.addAction(act_chat)
        act_status = QAction("状态面板", menu)
        act_status.triggered.connect(self.open_status)
        menu.addAction(act_status)
        act_settings = QAction("设置", menu)
        act_settings.triggered.connect(self.open_settings)
        menu.addAction(act_settings)

        menu.addSeparator()
        act_hide = QAction("藏到托盘", menu)
        act_hide.triggered.connect(self.hide_to_tray)
        menu.addAction(act_hide)
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self.quit_app)
        menu.addAction(act_quit)

        menu.exec(event.globalPos())

    # ---------------------------------------------------------------- 面板
    def open_chat(self) -> None:
        if self._chat_panel is None:
            panel = ChatPanel()
            panel.send_text.connect(self.on_chat_text)
            panel.do_action.connect(self._on_quick_action)
            self._chat_panel = panel
        panel = self._chat_panel
        panel.set_pet_name(self.state.name)
        panel.apply_theme(self.palette["accent"], self._soft_color())
        panel.set_badge("AI 对话" if self._llm_enabled() else "本地对话")
        if panel.msg_lay.count() <= 1:
            panel.add_message(self._opening_line(), "pet")
        panel.show_near(self._anchor_rect())
        self._wander_target = None

    def _soft_color(self) -> str:
        c = self.palette["body"]
        return c

    def _opening_line(self) -> str:
        s = self.state.stats
        if not self.state.hatched:
            return "蛋壳里传来轻轻的晃动……要不要敲敲看？"
        if s["hunger"] < 25:
            return "你来了……我正好有点饿。（可怜巴巴）"
        if s["mood"] > 78:
            return "你终于来啦！我有一肚子话想跟你说。"
        return random.choice([
            "在的！想聊什么都可以。",
            "嗯嗯，我听着呢。",
            "今天过得怎么样呀？",
        ])

    def _on_quick_action(self, key: str) -> None:
        if key == "pat":
            self.pat()
        elif key == "feed":
            self.feed("fish")
        elif key == "play":
            self.play()
        elif key == "wash":
            self.wash()
        elif key == "sleep":
            self.toggle_sleep()
        if self._chat_panel:
            self._chat_panel.add_message(
                {"pat": "（你摸了摸它的头）", "feed": "（你递过去一条小鱼干）",
                 "play": "（你拿出了毛线球）", "wash": "（你放好了洗澡水）",
                 "sleep": "（你轻轻拍了拍它）"}.get(key, ""), "user")

    def _llm_enabled(self) -> bool:
        llm = self.settings.get("llm") or {}
        if not llm.get("enabled"):
            return False
        if (llm.get("api_key") or "").strip():
            return True
        # 免注册 / 本地服务：没有密钥也能用
        preset = config.preset_by_id(llm.get("provider", ""))
        if preset.get("keyless"):
            return True
        base = (llm.get("base_url") or "").lower()
        return base.startswith("http://localhost") or base.startswith("http://127.0.0.1")

    def on_chat_text(self, text: str) -> None:
        panel = self._chat_panel
        if panel is None:
            return
        if self._llm_enabled():
            panel.show_typing()
            self._ask_llm(text)
        else:
            reply, emo = dialogue.reply(text, self.state, self.settings.get("owner_name", "主人"))
            panel.add_message(reply, "pet")
            self._speak(reply, emo)
        self._finish_chat_exp()

    def _finish_chat_exp(self) -> None:
        ups = self.state.chat_done()
        for lv in ups:
            self.effects.sparkles(12)
            if self._chat_panel:
                self._chat_panel.add_message(f"（我升级了！现在是 {lv} 级）", "pet")
        self.state.save()

    def _ask_llm(self, text: str) -> None:
        cfg = self.settings["llm"]
        system = dialogue.build_system_prompt(self.state, self.settings.get("owner_name", "主人"))
        self._history.append({"role": "user", "content": text})
        self._history = self._history[-10:]
        messages = [{"role": "system", "content": system}] + self._history

        worker = LLMWorker(cfg, messages, self)
        self._llm_worker = worker
        worker.ok.connect(self._on_llm_ok)
        worker.fail.connect(self._on_llm_fail)
        worker.start()

    def _on_llm_ok(self, text: str) -> None:
        panel = self._chat_panel
        if panel:
            panel.clear_typing()
            panel.add_message(text, "pet")
        self._history.append({"role": "assistant", "content": text})
        self._speak(text, "happy")

    def _on_llm_fail(self, msg: str) -> None:
        panel = self._chat_panel
        if panel:
            panel.clear_typing()
        reply, emo = dialogue.reply(self._history[-1]["content"] if self._history else "",
                                    self.state, self.settings.get("owner_name", "主人"))
        if panel:
            panel.add_message(reply, "pet")
            panel.add_message(f"（AI 连接失败，先用本地对话：{msg[:60]}）", "pet")
        self._speak(reply, emo)

    def open_status(self) -> None:
        if self._status_panel is None:
            self._status_panel = StatusPanel()
        self._status_panel.refresh(self.state, self.palette)
        self._status_panel.show_near(self._anchor_rect())

    def open_settings(self) -> None:
        if self._settings_panel is None:
            self._settings_panel = SettingsPanel(self.settings)
            self._settings_panel.saved.connect(self.apply_settings)
        else:
            self._settings_panel.load_from(self.settings)
        self._settings_panel.show_center()

    def apply_settings(self, new_settings: dict) -> None:
        old_scale = float(self.settings.get("scale", 1.0))
        self.settings.update(new_settings)
        config.save_settings(self.settings)
        self.state.name = self.settings.get("pet_name", self.state.name)
        self.state.palette = self.settings.get("palette", self.state.palette)
        self.palette = config.palette_of(self.settings)

        # 置顶
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(self.settings.get("always_on_top", True)))
        # 尺寸
        new_scale = float(self.settings.get("scale", 1.0))
        if abs(new_scale - old_scale) > 1e-6:
            self._s = new_scale
            self.setFixedSize(int(WIN_W * new_scale), int(WIN_H * new_scale))
        self.show()

        # 开机自启
        from . import platform_utils
        if platform_utils.supported():
            platform_utils.set_autostart(bool(self.settings.get("autostart")))

        if self._chat_panel:
            self._chat_panel.set_pet_name(self.state.name)
            self._chat_panel.apply_theme(self.palette["accent"], self._soft_color())
        if self._status_panel and self._status_panel.isVisible():
            self._status_panel.refresh(self.state, self.palette)
        icon = QIcon(painter.tray_icon_pixmap(64, self.palette))
        self.tray.setIcon(icon)
        self.setWindowIcon(icon)
        self.state.save()
        self._speak("设置好啦，我是不是更好看了？", "happy", 3000)

    # ---------------------------------------------------------------- 计时
    def _on_stat_tick(self) -> None:
        now = time.time()
        dt = max(1.0, min(120.0, now - self._last_tick))
        self._last_tick = now
        events = self.state.tick(dt, float(self.settings.get("decay_speed", 1.0)))
        self._update_tray_tip()
        for ev in events:
            if ev == "wake":
                self._speak(*dialogue.event_line("wake", self.state, self.settings.get("owner_name", "主人")))
            elif ev == "fall_asleep":
                self._speak(*dialogue.event_line("fall_asleep", self.state, self.settings.get("owner_name", "主人")))
            else:
                text, emo = dialogue.event_line(ev, self.state, self.settings.get("owner_name", "主人"))
                self._speak(text, emo)
            break  # 一次只提醒一件事，别轰炸

        if self._status_panel and self._status_panel.isVisible():
            self._status_panel.refresh(self.state, self.palette)

    def _update_tray_tip(self) -> None:
        s = self.state
        self.tray.setToolTip(
            f"{s.name}　Lv.{s.level}　{s.stage_name}\n"
            f"饱食 {int(s.stats['hunger'])}　精力 {int(s.stats['energy'])}\n"
            f"清洁 {int(s.stats['clean'])}　心情 {int(s.stats['mood'])}"
        )

    def _schedule_idle(self) -> None:
        self._idle_timer.start(random.randint(75000, 150000))

    def _on_idle_chatter(self) -> None:
        try:
            if (self.isVisible() and not self.state.sleeping and not self.bubble.isVisible()
                    and not (self._chat_panel and self._chat_panel.isVisible())):
                text, emo = dialogue.idle_line(self.state, self.settings.get("owner_name", "主人"))
                if text:
                    self._speak(text, emo)
        finally:
            self._schedule_idle()

    # ---------------------------------------------------------------- 鼠标
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._press_win = self.pos()
            self._moved = False
            self._dragging = True
            self._wander_target = None
            self.bubble.hide_now()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging and event.buttons() & Qt.LeftButton:
            g = event.globalPosition().toPoint()
            delta = g - self._press_global
            if delta.manhattanLength() > 4:
                self._moved = True
            if self._moved:
                self.move(self._press_win + delta)
                self.look.lean = clamp(delta.x() * 0.02, -0.8, 0.8)
                self.look.bob = abs(math.sin(self._t * 10)) * 3
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            was_drag = self._dragging and self._moved
            self._dragging = False
            self.look.bob = 0.0
            self.look.lean = 0.0
            if was_drag:
                self._squash_until = time.time() + 0.22
                self.effects.dust(7)
            if self._moved:
                self._clamp_to_screen()
                self.state.pos = {"x": self.x(), "y": self.y()}
                self.state.save()
            else:
                self.pat()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.open_chat()
        super().mouseDoubleClickEvent(event)

    def _clamp_to_screen(self) -> None:
        screen = QGuiApplication.screenAt(self.geometry().center()) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        x = max(avail.left() - self.width() // 3, min(self.x(), avail.right() - self.width() // 2))
        y = max(avail.top() - self.height() // 3, min(self.y(), avail.bottom() - self.height() // 2))
        self.move(int(x), int(y))

    # ---------------------------------------------------------------- 显隐
    def toggle_visible(self) -> None:
        if self.isVisible():
            self.hide_to_tray()
        else:
            self.show()
            self.raise_()
            self.state.save()

    def hide_to_tray(self) -> None:
        self.bubble.hide_now()
        if self._chat_panel:
            self._chat_panel.hide()
        if self._status_panel:
            self._status_panel.hide()
        self.hide()

    def quit_app(self) -> None:
        self.state.pos = {"x": self.x(), "y": self.y()}
        self.state.save()
        self.bubble.hide_now()
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.quit_app()
        event.accept()
