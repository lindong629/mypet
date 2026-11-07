"""对话气泡：贴在宠物头顶的小气泡，自动消失，且不挡住鼠标点击。"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QWidget

from .config import app_font_family

TAIL = 10
MARGIN = 6
PAD_X = 14
PAD_Y = 11
TEXT_W = 176


class Bubble(QWidget):
    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.WindowTransparentForInput
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._font = QFont()
        self._font.setFamilies(app_font_family())
        self._font.setPixelSize(13)

        self.label = QLabel(self)
        self.label.setWordWrap(True)
        self.label.setFont(self._font)
        self.label.setStyleSheet("color:#4A3B34; background:transparent;")
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide_animated)

        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self._below = False
        self._tail_x = 0
        self._hide_hooked = False

    # ---------------------------------------------------------------- 显示
    def say(self, text: str, anchor: QRect, duration_ms: int | None = None) -> None:
        text = (text or "").strip()
        if not text:
            return
        self.label.setText(text)
        self.label.setFont(self._font)

        fm = QFontMetrics(self._font)
        rect = fm.boundingRect(QRect(0, 0, TEXT_W, 2000), Qt.TextWordWrap, text)
        text_h = max(fm.height() + 2, rect.height())
        self.label.setFixedWidth(TEXT_W)
        self.label.setFixedHeight(text_h + 2)

        w = TEXT_W + PAD_X * 2 + MARGIN * 2
        h = text_h + PAD_Y * 2 + TAIL + MARGIN * 2
        self.resize(w, h)
        self.label.move(MARGIN + PAD_X, MARGIN + PAD_Y)

        self._place(anchor, w, h)

        if duration_ms is None:
            duration_ms = int(2200 + len(text) * 95)
            duration_ms = max(2600, min(9000, duration_ms))

        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._anim.stop()
        self._unhook()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(duration_ms)

    def _place(self, anchor: QRect, w: int, h: int) -> None:
        screen = QGuiApplication.screenAt(anchor.center()) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()

        x = anchor.center().x() - w // 2
        above_y = anchor.top() - h + MARGIN + 2
        below_y = anchor.bottom() - MARGIN
        self._below = above_y < avail.top() + 4
        y = below_y if self._below else above_y

        x = max(avail.left() + 2, min(x, avail.right() - w - 2))
        y = max(avail.top() + 2, min(y, avail.bottom() - h - 2))
        self.move(QPoint(x, y))

        # 气泡尾巴对准宠物中心
        self._tail_x = anchor.center().x() - x
        self._tail_x = max(24, min(w - 24, self._tail_x))
        self.update()

    def hide_animated(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(0.0)
        if not self._hide_hooked:
            self._anim.finished.connect(self._finish_hide)
            self._hide_hooked = True
        self._anim.start()

    def _unhook(self) -> None:
        if self._hide_hooked:
            try:
                self._anim.finished.disconnect(self._finish_hide)
            except (RuntimeError, TypeError):
                pass
            self._hide_hooked = False

    def _finish_hide(self) -> None:
        self._unhook()
        self.hide()

    def hide_now(self) -> None:
        self._timer.stop()
        self._anim.stop()
        self.hide()

    # ---------------------------------------------------------------- 绘制
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        body = QRect(MARGIN, MARGIN, self.width() - MARGIN * 2, self.height() - MARGIN * 2 - TAIL)
        if self._below:
            body = QRect(MARGIN, MARGIN + TAIL, self.width() - MARGIN * 2,
                         self.height() - MARGIN * 2 - TAIL)

        path = QPainterPath()
        path.addRoundedRect(body, 13, 13)

        tx = self._tail_x
        if self._below:
            tri = QPainterPath()
            tri.moveTo(tx - 8, body.top() + 1)
            tri.lineTo(tx, body.top() - TAIL)
            tri.lineTo(tx + 8, body.top() + 1)
        else:
            tri = QPainterPath()
            tri.moveTo(tx - 8, body.bottom() - 1)
            tri.lineTo(tx, body.bottom() + TAIL)
            tri.lineTo(tx + 8, body.bottom() - 1)
        tri.closeSubpath()
        shape = path.united(tri)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(120, 90, 60, 26))
        shadow = QPainterPath(shape)
        shadow.translate(0, 2)
        p.drawPath(shadow)

        p.setBrush(QColor(255, 253, 246, 248))
        p.setPen(QPen(QColor("#F0CFA4"), 2))
        p.drawPath(shape)
