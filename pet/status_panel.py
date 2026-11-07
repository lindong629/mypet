"""状态面板：等级、属性、成就一览。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QFont, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import painter
from .config import ACHIEVEMENTS, app_font_family
from .state import STAT_COLORS, STAT_KEYS, STAT_NAMES, STAGE_HINT, PetState


class StatusPanel(QWidget):
    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(364, 486)
        self._drag_from: QPoint | None = None
        self._palette: dict = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        self.card = QFrame(self)
        self.card.setObjectName("card")
        root.addWidget(self.card)

        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(18, 14, 18, 16)
        lay.setSpacing(10)

        # 顶部
        head = QHBoxLayout()
        head.setSpacing(12)
        self.portrait = QLabel()
        self.portrait.setFixedSize(86, 86)
        self.portrait.setStyleSheet("background:transparent;")
        head.addWidget(self.portrait)

        info = QVBoxLayout()
        info.setSpacing(3)
        self.name_lbl = QLabel("团子")
        self.name_lbl.setObjectName("pname")
        info.addWidget(self.name_lbl)

        self.stage_lbl = QLabel("幼崽")
        self.stage_lbl.setObjectName("pstage")
        info.addWidget(self.stage_lbl)

        self.lv_lbl = QLabel("Lv.1")
        self.lv_lbl.setObjectName("plv")
        info.addWidget(self.lv_lbl)

        self.exp_bar = QProgressBar()
        self.exp_bar.setTextVisible(False)
        self.exp_bar.setFixedHeight(8)
        self.exp_bar.setRange(0, 100)
        info.addWidget(self.exp_bar)
        self.exp_lbl = QLabel("")
        self.exp_lbl.setObjectName("tiny")
        info.addWidget(self.exp_lbl)
        info.addStretch(1)
        head.addLayout(info, 1)
        lay.addLayout(head)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#F0E1CD;")
        lay.addWidget(line)

        # 属性
        self.bars: dict[str, QProgressBar] = {}
        self.vals: dict[str, QLabel] = {}
        stats_box = QVBoxLayout()
        stats_box.setSpacing(7)
        for key in STAT_KEYS:
            row = QHBoxLayout()
            row.setSpacing(8)
            name = QLabel(STAT_NAMES[key])
            name.setObjectName("sname")
            name.setFixedWidth(52)
            row.addWidget(name)
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setRange(0, 100)
            bar.setFixedHeight(10)
            bar.setStyleSheet(
                "QProgressBar{background:#F4E8D8;border-radius:5px;}"
                f"QProgressBar::chunk{{background:{STAT_COLORS[key]};border-radius:5px;}}"
            )
            row.addWidget(bar, 1)
            val = QLabel("0")
            val.setObjectName("sval")
            val.setFixedWidth(30)
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(val)
            stats_box.addLayout(row)
            self.bars[key] = bar
            self.vals[key] = val
        lay.addLayout(stats_box)

        # 摘要
        self.summary = QLabel("")
        self.summary.setObjectName("summary")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)

        # 成就
        ach_title = QLabel("成就")
        ach_title.setObjectName("section")
        lay.addWidget(ach_title)

        grid_host = QWidget()
        grid_host.setStyleSheet("background:transparent;")
        self.grid = QGridLayout(grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(6)
        self.grid.setVerticalSpacing(5)
        self.ach_labels: dict[str, QLabel] = {}
        for i, a in enumerate(ACHIEVEMENTS):
            lbl = QLabel(a["name"])
            lbl.setObjectName("ach")
            lbl.setToolTip(a["desc"])
            lbl.setAlignment(Qt.AlignCenter)
            self.grid.addWidget(lbl, i // 2, i % 2)
            self.ach_labels[a["id"]] = lbl
        lay.addWidget(grid_host)
        lay.addStretch(1)

        foot = QHBoxLayout()
        hint = QLabel("右键宠物可喂食、洗澡、让它睡觉")
        hint.setObjectName("tiny")
        foot.addWidget(hint)
        foot.addStretch(1)
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("plainbtn")
        close_btn.setFixedSize(54, 26)
        close_btn.clicked.connect(self.hide)
        foot.addWidget(close_btn)
        lay.addLayout(foot)

        fam = app_font_family()[0]
        self.setStyleSheet(f"""
            QWidget {{ font-family: "{fam}"; color:#4A3B34; }}
            #card {{ background:#FFFBF4; border:2px solid #F3D9B4; border-radius:18px; }}
            #pname {{ font-size:17px; font-weight:700; }}
            #pstage {{ font-size:11px; color:#FF8A65; }}
            #plv {{ font-size:11px; color:#8B7768; }}
            #tiny {{ font-size:10px; color:#A5907E; }}
            #sname {{ font-size:11px; color:#7A6455; }}
            #sval {{ font-size:11px; color:#7A6455; }}
            #summary {{ font-size:11px; color:#8B7768; background:#FFF4E6;
                        border-radius:8px; padding:7px 9px; }}
            #section {{ font-size:12px; font-weight:700; color:#7A6455; }}
            #ach {{ font-size:10px; padding:5px 2px; border-radius:8px;
                    background:#F2E2CB; color:#A08D7B; }}
            #ach[on="true"] {{ background:#FFE1BC; color:#B8652E; font-weight:600; }}
            QPushButton#plainbtn {{ border:1px solid #EFD8BC; border-radius:9px;
                    background:#FFFDF8; font-size:11px; color:#7A6455; }}
            QPushButton#plainbtn:hover {{ background:#FFF4E4; }}
        """)

    # ---------------------------------------------------------------- 刷新
    def refresh(self, state: PetState, palette: dict) -> None:
        self._palette = palette
        self.name_lbl.setText(state.name)
        self.stage_lbl.setText(f"{state.stage_name} · {STAGE_HINT[state.stage]}")
        self.lv_lbl.setText(f"Lv.{state.level}　亲密度 {state.bond_hearts}/5")
        need = state.exp_need()
        self.exp_bar.setMaximum(max(1, need))
        self.exp_bar.setValue(min(state.exp, need))
        self.exp_bar.setStyleSheet(
            "QProgressBar{background:#F4E8D8;border-radius:4px;}"
            f"QProgressBar::chunk{{background:{palette['accent']};border-radius:4px;}}"
        )
        self.exp_lbl.setText(f"经验 {state.exp}/{need}　下一级还需 {max(0, need - state.exp)}")

        for key in STAT_KEYS:
            v = int(round(state.stats[key]))
            self.bars[key].setValue(v)
            self.vals[key].setText(str(v))

        total = sum(state.counters.values())
        self.summary.setText(
            f"心情：{state.mood_word()}　　陪伴 {state.days_together()} 天\n"
            f"互动 {total} 次（喂食 {state.counters['feed']} · 玩耍 {state.counters['play']} · "
            f"洗澡 {state.counters['wash']} · 聊天 {state.counters['chat']}）"
        )

        for aid, lbl in self.ach_labels.items():
            on = aid in state.achievements
            lbl.setProperty("on", "true" if on else "false")
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

        look = painter.Look(stage=state.stage, emotion="happy", t=0.6)
        if state.sleeping:
            look.emotion = "sleepy"
            look.sleeping = True
        pm: QPixmap = painter.render_pixmap(86, look, palette)
        self.portrait.setPixmap(pm)

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

    # 拖动
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and event.position().y() < 100:
            self._drag_from = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_from is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_from)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_from = None
        super().mouseReleaseEvent(event)
