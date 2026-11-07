"""设置面板：名字、外观、作息节奏、大模型接入。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import platform_utils, ui_assets
from .config import (
    DECAY_PRESETS,
    LLM_PRESETS,
    PALETTES,
    app_font_family,
    preset_by_base_url,
    preset_by_id,
)
from .llm import LLMTestWorker, ModelsWorker


class SettingsPanel(QWidget):
    saved = Signal(dict)

    def __init__(self, settings: dict) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(412, 700)
        self._drag_from: QPoint | None = None
        self._settings = dict(settings)
        self._test_worker: LLMTestWorker | None = None
        self._models_worker: ModelsWorker | None = None
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)
        card = QFrame()
        card.setObjectName("card")
        root.addWidget(card)

        outer = QVBoxLayout(card)
        outer.setContentsMargins(20, 14, 16, 14)
        outer.setSpacing(8)

        title = QLabel("设置")
        title.setObjectName("title")
        outer.addWidget(title)

        # 可滚动主体（小屏 / 大字号下也不会被裁掉）
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(8)
        self.scroll.setWidget(body)
        outer.addWidget(self.scroll, 1)

        # ---------- 基本
        lay.addWidget(self._section("基本"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(7)

        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(8)
        self.owner_edit = QLineEdit()
        self.owner_edit.setMaxLength(8)
        grid.addWidget(QLabel("宠物名字"), 0, 0)
        grid.addWidget(self.name_edit, 0, 1)
        grid.addWidget(QLabel("它叫你"), 1, 0)
        grid.addWidget(self.owner_edit, 1, 1)

        self.palette_box = QComboBox()
        self.palette_box.addItems(list(PALETTES.keys()))
        grid.addWidget(QLabel("配色"), 2, 0)
        grid.addWidget(self.palette_box, 2, 1)

        self.decay_box = QComboBox()
        self.decay_box.addItems(list(DECAY_PRESETS.keys()))
        grid.addWidget(QLabel("养成节奏"), 3, 0)
        grid.addWidget(self.decay_box, 3, 1)
        lay.addLayout(grid)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("大小"))
        self.scale_slider = QSlider(Qt.Horizontal)
        self.scale_slider.setRange(75, 160)
        size_row.addWidget(self.scale_slider, 1)
        self.scale_lbl = QLabel("100%")
        self.scale_lbl.setFixedWidth(44)
        size_row.addWidget(self.scale_lbl)
        self.scale_slider.valueChanged.connect(lambda v: self.scale_lbl.setText(f"{v}%"))
        lay.addLayout(size_row)

        self.top_check = QCheckBox("窗口始终置顶")
        self.wander_check = QCheckBox("允许在桌面上自由走动")
        self.autostart_check = QCheckBox("开机自动启动")
        if not platform_utils.supported():
            self.autostart_check.setText("开机自动启动（仅 Windows）")
            self.autostart_check.setEnabled(False)
        for w in (self.top_check, self.wander_check, self.autostart_check):
            lay.addWidget(w)

        # ---------- 对话
        lay.addWidget(self._section("对话（可选）"))
        self.llm_check = QCheckBox("启用大模型对话（不勾就用本地词库，也能聊）")
        lay.addWidget(self.llm_check)

        prov_row = QHBoxLayout()
        prov_row.addWidget(QLabel("服务商"))
        self.provider_box = QComboBox()
        for p in LLM_PRESETS:
            self.provider_box.addItem(p["name"], p["id"])
        prov_row.addWidget(self.provider_box, 1)
        lay.addLayout(prov_row)

        self.note_lbl = QLabel("")
        self.note_lbl.setObjectName("note")
        self.note_lbl.setWordWrap(True)
        lay.addWidget(self.note_lbl)

        g2 = QGridLayout()
        g2.setHorizontalSpacing(10)
        g2.setVerticalSpacing(7)
        self.base_edit = QLineEdit()
        self.base_edit.setPlaceholderText("https://xxx/v1")
        self.model_box = QComboBox()
        self.model_box.setEditable(True)
        self.model_box.setInsertPolicy(QComboBox.NoInsert)
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        g2.addWidget(QLabel("接口地址"), 0, 0)
        g2.addWidget(self.base_edit, 0, 1)
        g2.addWidget(QLabel("模型"), 1, 0)
        g2.addWidget(self.model_box, 1, 1)
        g2.addWidget(QLabel("密钥"), 2, 0)
        g2.addWidget(self.key_edit, 2, 1)
        lay.addLayout(g2)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.key_btn = QPushButton("获取免费 Key")
        self.key_btn.setObjectName("plainbtn")
        self.key_btn.setFixedHeight(28)
        self.key_btn.clicked.connect(self._open_signup)
        self.models_btn = QPushButton("刷新模型")
        self.models_btn.setObjectName("plainbtn")
        self.models_btn.setFixedHeight(28)
        self.models_btn.clicked.connect(self._refresh_models)
        self.test_btn = QPushButton("测试连接")
        self.test_btn.setObjectName("plainbtn")
        self.test_btn.setFixedHeight(28)
        self.test_btn.clicked.connect(self._test)
        for b in (self.key_btn, self.models_btn, self.test_btn):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        self.test_lbl = QLabel("")
        self.test_lbl.setObjectName("note")
        self.test_lbl.setWordWrap(True)
        lay.addWidget(self.test_lbl)

        lay.addStretch(1)

        # ---------- 底部按钮
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setObjectName("plainbtn")
        cancel.setFixedSize(76, 32)
        cancel.clicked.connect(self.hide)
        btns.addWidget(cancel)
        save = QPushButton("保存")
        save.setObjectName("primary")
        save.setFixedSize(88, 32)
        save.clicked.connect(self._save)
        btns.addWidget(save)
        outer.addLayout(btns)

        self.provider_box.currentIndexChanged.connect(self._on_provider_changed)

        fam = app_font_family()[0]
        arrow = ui_assets.arrow_png()
        self.setStyleSheet(f"""
            QWidget {{ font-family: "{fam}"; color: #4A3B34; font-size: 12px; }}
            #card {{ background: #FFFBF4; border: 2px solid #F3D9B4; border-radius: 18px; }}
            #title {{ font-size: 16px; font-weight: 700; }}
            #section {{ font-size: 12px; font-weight: 700; color: #C4713C; margin-top: 2px; }}
            #note {{ font-size: 10px; color: #9C8877; }}
            QLineEdit {{ border: 1px solid #EFD8BC; border-radius: 8px; padding: 4px 8px;
                         background: white; font-size: 12px; }}
            QLineEdit:focus {{ border: 1px solid #FF8A65; }}
            QComboBox {{ border: 1px solid #EFD8BC; border-radius: 8px; padding: 3px 8px;
                         background: white; font-size: 12px; }}
            QComboBox QAbstractItemView {{ selection-background-color: #FFE9CE; color: #4A3B34; }}
            QComboBox::drop-down {{ border: none; width: 20px; background: transparent; }}
            QComboBox::down-arrow {{ image: url("{arrow}"); width: 12px; height: 12px;
                                     margin-right: 4px; }}
            QCheckBox {{ font-size: 12px; color: #6E5A4C; spacing: 6px; }}
            QSlider::groove:horizontal {{ height: 5px; background: #F4E8D8; border-radius: 3px; }}
            QSlider::handle:horizontal {{ width: 14px; margin: -5px 0; border-radius: 7px;
                                          background: #FF9F68; }}
            QPushButton#plainbtn {{ border: 1px solid #EFD8BC; border-radius: 8px;
                                    background: #FFFDF8; font-size: 11px; color: #7A6455;
                                    padding: 0 8px; }}
            QPushButton#plainbtn:hover {{ background: #FFF4E4; }}
            QPushButton#primary {{ border: none; border-radius: 10px; background: #FF9F68;
                                   color: white; font-size: 12px; font-weight: 600; }}
            QPushButton#primary:hover {{ background: #FF8F52; }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0; }}
            QScrollBar::handle:vertical {{ background: #E6D2B8; border-radius: 3px; min-height: 24px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        self.load_from(self._settings)

    @staticmethod
    def _section(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("section")
        return lbl

    # ---------------------------------------------------------------- 载入/收集
    def load_from(self, settings: dict) -> None:
        self._settings = dict(settings)
        self._loading = True
        try:
            self.name_edit.setText(settings.get("pet_name", "团子"))
            self.owner_edit.setText(settings.get("owner_name", "主人"))
            self.palette_box.setCurrentText(settings.get("palette", "奶油橘"))

            decay = float(settings.get("decay_speed", 1.0))
            for name, v in DECAY_PRESETS.items():
                if abs(v - decay) < 0.01:
                    self.decay_box.setCurrentText(name)
            self.scale_slider.setValue(int(float(settings.get("scale", 1.0)) * 100))
            self.scale_lbl.setText(f"{self.scale_slider.value()}%")
            self.top_check.setChecked(bool(settings.get("always_on_top", True)))
            self.wander_check.setChecked(bool(settings.get("allow_wander", True)))
            self.autostart_check.setChecked(bool(settings.get("autostart", False)))

            llm = settings.get("llm") or {}
            self.llm_check.setChecked(bool(llm.get("enabled", False)))
            preset = preset_by_id(llm.get("provider", "")) or preset_by_base_url(llm.get("base_url", ""))
            if not preset:
                preset = preset_by_id("custom")
            idx = self.provider_box.findData(preset["id"])
            self.provider_box.setCurrentIndex(max(0, idx))
            self.base_edit.setText(llm.get("base_url", "") or preset.get("base_url", ""))
            self.model_box.setCurrentText(llm.get("model", "") or preset.get("model", ""))
            self.key_edit.setText(llm.get("api_key", ""))
            self._show_note(preset)
            self._sync_key_field(preset)
            self.test_lbl.setText("")
        finally:
            self._loading = False

    def _collect(self) -> dict:
        s = dict(self._settings)
        s["pet_name"] = self.name_edit.text().strip() or "团子"
        s["owner_name"] = self.owner_edit.text().strip() or "主人"
        s["palette"] = self.palette_box.currentText()
        s["scale"] = round(self.scale_slider.value() / 100.0, 2)
        s["decay_speed"] = DECAY_PRESETS.get(self.decay_box.currentText(), 1.0)
        s["always_on_top"] = self.top_check.isChecked()
        s["allow_wander"] = self.wander_check.isChecked()
        s["autostart"] = self.autostart_check.isChecked()
        s["llm"] = {
            "enabled": self.llm_check.isChecked(),
            "provider": self.provider_box.currentData() or "custom",
            "base_url": self.base_edit.text().strip(),
            "model": self.model_box.currentText().strip(),
            "api_key": self.key_edit.text().strip(),
        }
        return s

    # ---------------------------------------------------------------- 服务商
    def _current_preset(self) -> dict:
        pid = self.provider_box.currentData() or "custom"
        return preset_by_id(pid)

    def _show_note(self, preset: dict) -> None:
        self.note_lbl.setText(preset.get("note", ""))

    def _sync_key_field(self, preset: dict) -> None:
        keyless = bool(preset.get("keyless"))
        self.key_edit.setPlaceholderText("这个服务商不需要密钥" if keyless else "粘贴你的 API Key")
        self.key_edit.setEnabled(not keyless)
        has_signup = bool(preset.get("signup"))
        self.key_btn.setVisible(has_signup)
        self.key_btn.setEnabled(has_signup)

    def _on_provider_changed(self) -> None:
        if self._loading:
            return
        preset = self._current_preset()
        self.base_edit.setText(preset.get("base_url", ""))
        self.model_box.clear()
        self.model_box.setCurrentText(preset.get("model", ""))
        self._show_note(preset)
        self._sync_key_field(preset)
        self.test_lbl.setText("")

    def _open_signup(self) -> None:
        preset = self._current_preset()
        url = preset.get("signup")
        if url:
            QDesktopServices.openUrl(QUrl(url))
            self.test_lbl.setText("已在浏览器打开注册页：注册 → 实名 → 创建 API Key → 粘贴回这里")
        else:
            self.test_lbl.setText("这个服务商不需要注册。")

    # ---------------------------------------------------------------- 网络动作
    def _refresh_models(self) -> None:
        cfg = self._collect()["llm"]
        self.models_btn.setEnabled(False)
        self.test_lbl.setText("正在拉取模型列表……")
        worker = ModelsWorker(cfg, self)
        self._models_worker = worker

        def on_ok(models: list) -> None:
            cur = self.model_box.currentText().strip()
            self.model_box.clear()
            self.model_box.addItems([str(m) for m in models])
            if cur in models:
                self.model_box.setCurrentText(cur)
            self.test_lbl.setText(f"拉到 {len(models)} 个模型，点下拉选一个")

        worker.ok.connect(on_ok)
        worker.fail.connect(lambda m: self.test_lbl.setText(str(m)[:110]))
        worker.finished.connect(lambda: self.models_btn.setEnabled(True))
        worker.start()

    def _test(self) -> None:
        cfg = self._collect()["llm"]
        preset = self._current_preset()
        if not preset.get("keyless") and not cfg["api_key"]:
            self.test_lbl.setText("先填密钥：点「获取免费 Key」去注册，或者换成免注册的那个服务商。")
            return
        self.test_btn.setEnabled(False)
        self.test_lbl.setText("正在连接……")
        worker = LLMTestWorker(cfg, self)
        self._test_worker = worker
        worker.ok.connect(lambda t: self.test_lbl.setText(f"连接成功，它说：{t}"))
        worker.fail.connect(lambda m: self.test_lbl.setText(str(m)[:120]))
        worker.finished.connect(lambda: self.test_btn.setEnabled(True))
        worker.start()

    # ---------------------------------------------------------------- 保存
    def _save(self) -> None:
        s = self._collect()
        llm = s["llm"]
        preset = preset_by_id(llm["provider"])
        if llm["enabled"]:
            if not llm["base_url"] or not llm["model"]:
                self.test_lbl.setText("接口地址和模型都要填。")
                return
            if not preset.get("keyless") and not llm["api_key"]:
                self.test_lbl.setText("这个服务商需要密钥：点「获取免费 Key」，或者换成标了免注册的那个。")
                return
        self._settings = s
        self.saved.emit(s)
        self.hide()

    # ---------------------------------------------------------------- 显示
    def show_center(self) -> None:
        screen = QGuiApplication.primaryScreen()
        g = screen.availableGeometry()
        h = min(self.height(), g.height() - 60)
        if h != self.height():
            self.setFixedHeight(h)
        self.move(g.center().x() - self.width() // 2, g.center().y() - h // 2)
        self.show()
        self.raise_()
        self.activateWindow()

    # 拖动
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and event.position().y() < 50:
            self._drag_from = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_from is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_from)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_from = None
        super().mouseReleaseEvent(event)
