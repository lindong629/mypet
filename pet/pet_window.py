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

from . import config, dialogue, painter
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
        self._anim_kind = ""
        self._anim_until = 0.0
        self._spawn_acc = 0.0
        self._hop_start = -1.0
        self._hop_dir = 1

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

        # 呼吸
        speed = 0.75 if self.state.sleeping else 1.0
        lk.breath = math.sin(self._t * 1.7 * speed)

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
        lk.tail = math.sin(self._t * (0.9 if self.state.sleeping else 1.5))

        # 跳跃
        if self._hop_start > 0:
            k = (now - self._hop_start) / 0.45
            if k >= 1:
                self._hop_start = -1.0
                lk.jump = 0.0
            else:
                lk.jump = math.sin(math.pi * k) * 0.55
        else:
            lk.jump = 0.0

        # 走动
        self._update_wander(dt)

        # 眼睛跟随鼠标
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
        lk.sleeping = self.state.sleeping

        # 动作动画
        self._update_action_anim(now, dt)
        if not self._anim_kind:
            lk.mouth = 0.0
            lk.eating = False
            lk.washing = False

        # 睡觉冒 Z
        if self.state.sleeping and not self._anim_kind:
            self._spawn_acc += dt
            if self._spawn_acc > 1.1:
                self._spawn_acc = 0.0
                self.effects.zzz()

        self.effects.update(dt)
        self.update()

    def _base_emotion(self) -> str:
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

    def _update_action_anim(self, now: float, dt: float) -> None:
        if not self._anim_kind:
            return
        if now > self._anim_until:
            self._anim_kind = ""
            return
        lk = self.look
        if self._anim_kind == "eat":
            lk.eating = True
            lk.mouth = 0.55 + 0.45 * math.sin(self._t * 16)
            self._spawn_acc += dt
            if self._spawn_acc > 0.22:
                self._spawn_acc = 0.0
                self.effects.crumbs(3)
        elif self._anim_kind == "wash":
            lk.washing = True
            lk.emotion = "dizzy"
            self._spawn_acc += dt
            if self._spawn_acc > 0.18:
                self._spawn_acc = 0.0
                self.effects.bubbles(3)
            lk.lean = math.sin(self._t * 14) * 0.35
        elif self._anim_kind == "play":
            lk.emotion = "happy"
            self._hop_start = self._hop_start if self._hop_start > 0 else now

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
                self.look.lean *= 0.8
                return
            step = math.copysign(min(abs(diff), 42 * dt), diff)
            nx = int(round(x + step))
            self.move(nx, self.y())
            self.look.lean = clamp(step * 0.4, -1, 1)
            self.look.bob = abs(math.sin(self._t * 9)) * 2.2
        else:
            self.look.lean *= 0.85
            self.look.bob *= 0.9

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
            self._anim_kind = "eat"
            self._anim_until = time.time() + 2.0
            self._spawn_acc = 0.0
            self.effects.crumbs(5)
        self._after_action(res)

    def play(self, action_id: str | None = None) -> None:
        pool = config.PLAY_ACTIONS
        action = next((a for a in pool if a["id"] == action_id), random.choice(pool))
        res = self.state.play(action)
        if res.get("ok"):
            self._anim_kind = "play"
            self._anim_until = time.time() + 1.6
            self._hop_start = time.time()
            self.effects.hearts(5)
        self._after_action(res)

    def wash(self) -> None:
        res = self.state.wash()
        if res.get("ok"):
            self._anim_kind = "wash"
            self._anim_until = time.time() + 2.4
            self._spawn_acc = 0.0
            self.effects.bubbles(10)
        self._after_action(res)

    def pat(self) -> None:
        res = self.state.pat()
        if res.get("ok"):
            self._hop_start = time.time()
            if self.state.hatched:
                self.effects.hearts(3 if res.get("emotion") != "love" else 6)
            else:
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
            self._dragging = False
            self.look.bob = 0.0
            self.look.lean = 0.0
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
