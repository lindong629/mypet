"""聊天面板：输入、对话记录、快捷互动。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .config import app_font_family


def _chip(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("chip")
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(26)
    return b


class ChatPanel(QWidget):
    send_text = Signal(str)
    do_action = Signal(str)
    closed = Signal()

    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(352)
        self.setFixedHeight(462)

        self._drag_from: QPoint | None = None
        self._typing_label: QLabel | None = None
        self._accent = "#FF8A65"

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)

        self.card = QFrame(self)
        self.card.setObjectName("card")
        root.addWidget(self.card)

        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        # 顶部
        head = QHBoxLayout()
        head.setSpacing(6)
        self.title = QLabel("团子")
        self.title.setObjectName("title")
        head.addWidget(self.title)
        self.badge = QLabel("本地对话")
        self.badge.setObjectName("badge")
        head.addWidget(self.badge)
        head.addStretch(1)
        close_btn = QPushButton("×")
        close_btn.setObjectName("closebtn")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.hide_panel)
        head.addWidget(close_btn)
        lay.addLayout(head)

        # 消息区
        self.scroll = QScrollArea(self.card)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;}")

        self.msg_host = QWidget()
        self.msg_host.setStyleSheet("background:transparent;")
        self.msg_lay = QVBoxLayout(self.msg_host)
        self.msg_lay.setContentsMargins(0, 4, 0, 4)
        self.msg_lay.setSpacing(7)
        self.msg_lay.addStretch(1)
        self.scroll.setWidget(self.msg_host)
        lay.addWidget(self.scroll, 1)

        # 快捷操作
        chips = QHBoxLayout()
        chips.setSpacing(6)
        for key, label in (("pat", "摸摸"), ("feed", "喂食"), ("play", "玩耍"),
                           ("wash", "洗澡"), ("sleep", "睡觉")):
            b = _chip(label)
            b.clicked.connect(lambda _=False, k=key: self.do_action.emit(k))
            chips.addWidget(b)
        chips.addStretch(1)
        lay.addLayout(chips)

        # 输入
        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = QLineEdit()
        self.input.setPlaceholderText("和我说点什么吧……")
        self.input.setFixedHeight(36)
        self.input.returnPressed.connect(self._on_send)
        row.addWidget(self.input, 1)
        self.btn_send = QPushButton("发送")
        self.btn_send.setObjectName("send")
        self.btn_send.setFixedSize(62, 36)
        self.btn_send.setCursor(Qt.PointingHandCursor)
        self.btn_send.clicked.connect(self._on_send)
        row.addWidget(self.btn_send)
        lay.addLayout(row)

        self.apply_theme(self._accent, "#FFF6E5")
        self._apply_style()

    # ---------------------------------------------------------------- 外观
    def apply_theme(self, accent: str, soft: str) -> None:
        self._accent = accent
        self._soft = soft
        self._apply_style()

    def _apply_style(self) -> None:
        fam = app_font_family()[0]
        self.setStyleSheet(f"""
            QWidget {{ font-family: "{fam}"; }}
            #card {{
                background: #FFFBF4;
                border: 2px solid #F3D9B4;
                border-radius: 18px;
            }}
            #title {{ font-size: 15px; font-weight: 700; color: #4A3B34; }}
            #badge {{
                font-size: 10px; color: {self._accent};
                background: {self._soft}; border-radius: 8px; padding: 2px 7px;
            }}
            #closebtn {{
                border: none; border-radius: 12px; background: transparent;
                color: #B6A08A; font-size: 16px;
            }}
            #closebtn:hover {{ background: #F6E7D5; color: #7A6455; }}
            QPushButton#chip {{
                border: 1px solid #EFD8BC; border-radius: 13px;
                background: #FFFDF8; color: #7A6455; font-size: 11px;
                padding: 0 10px;
            }}
            QPushButton#chip:hover {{ background: {self._soft}; border-color: {self._accent}; }}
            QPushButton#send {{
                border: none; border-radius: 12px;
                background: {self._accent}; color: white; font-size: 12px; font-weight: 600;
            }}
            QPushButton#send:hover {{ background: {self._accent}; }}
            QPushButton#send:disabled {{ background: #E8D9C7; color: #FFFDF8; }}
            QLineEdit {{
                border: 1px solid #EFD8BC; border-radius: 12px;
                padding: 0 12px; background: #FFFFFF; color: #4A3B34; font-size: 12px;
            }}
            QLineEdit:focus {{ border: 1px solid {self._accent}; }}
            QScrollBar:vertical {{
                background: transparent; width: 6px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: #E6D2B8; border-radius: 3px; min-height: 24px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

    def set_pet_name(self, name: str) -> None:
        self.title.setText(name)

    def set_badge(self, text: str) -> None:
        self.badge.setText(text)

    # ---------------------------------------------------------------- 消息
    def add_message(self, text: str, who: str = "pet") -> QLabel:
        row = QWidget()
        row.setStyleSheet("background:transparent;")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(228)
        label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        if who == "user":
            label.setStyleSheet(
                f"background:{self._accent}; color:white; border-radius:12px;"
                "padding:8px 11px; font-size:12px;"
            )
            h.addStretch(1)
            h.addWidget(label)
        else:
            label.setStyleSheet(
                "background:#FFFFFF; color:#4A3B34; border:1px solid #F2E3CE;"
                "border-radius:12px; padding:8px 11px; font-size:12px;"
            )
            h.addWidget(label)
            h.addStretch(1)

        self.msg_lay.insertWidget(self.msg_lay.count() - 1, row)
        self._scroll_bottom()
        return label

    def show_typing(self) -> None:
        self.clear_typing()
        self._typing_label = self.add_message("……", "pet")

    def clear_typing(self) -> None:
        if self._typing_label is not None:
            label = self._typing_label
            self._typing_label = None
            label.parentWidget().deleteLater()

    def _scroll_bottom(self) -> None:
        QTimer.singleShot(40, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    # ---------------------------------------------------------------- 交互
    def _on_send(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.add_message(text, "user")
        self.send_text.emit(text)

    def hide_panel(self) -> None:
        self.hide()
        self.closed.emit()

    def show_near(self, anchor) -> None:
        screen = QGuiApplication.screenAt(anchor.center()) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        w, h = self.width(), self.height()

        x = anchor.center().x() - w // 2
        y = anchor.top() - h - 8
        if y < avail.top() + 8:
            y = min(avail.bottom() - h - 8, anchor.bottom() + 8)
        x = max(avail.left() + 8, min(x, avail.right() - w - 8))
        y = max(avail.top() + 8, min(y, avail.bottom() - h - 8))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.hide_panel()
            return
        super().keyPressEvent(event)

    # 拖动标题栏
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and event.position().y() < 52:
            self._drag_from = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_from is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_from)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_from = None
        super().mouseReleaseEvent(event)
