"""开发用：离屏跑一遍完整应用，截图各面板并验证互动逻辑。

    python tools/smoke.py
"""
from __future__ import annotations

import os
import sys
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pet import config, dialogue  # noqa: E402
from pet.pet_window import PetWindow  # noqa: E402
from pet.state import PetState  # noqa: E402

OUT = os.path.join(ROOT, "preview")
os.makedirs(OUT, exist_ok=True)

errors: list[str] = []


def shot(widget, name: str, bg: str = "#DDE7F2") -> None:
    pm = widget.grab()
    canvas = QPixmap(pm.size())
    canvas.fill(QColor(bg))
    p = QPainter(canvas)
    p.drawPixmap(0, 0, pm)
    p.end()
    canvas.save(os.path.join(OUT, f"{name}.png"))
    print("shot:", name, pm.width(), "x", pm.height())


def main() -> int:
    app = QApplication(sys.argv)
    settings = dict(config.DEFAULT_SETTINGS)
    settings["llm"] = dict(config.DEFAULT_SETTINGS["llm"])

    state = PetState(name="团子", hatched=True, level=2)
    state.stats = {"hunger": 62.0, "energy": 74.0, "clean": 58.0, "mood": 71.0}

    win = PetWindow(state, settings)
    win.show()

    def step1() -> None:
        app.processEvents()
        shot(win, "app_pet")
        print("bubble text:", win.bubble.label.text()[:40])
        print("emotion:", win.look.emotion, "stage:", win.look.stage)
        win.bubble.say("小鱼干！咔嚓咔嚓～最喜欢了！要不要再来一条？", win._anchor_rect())
        app.processEvents()
        shot(win.bubble, "app_bubble")

    def step2() -> None:
        win.open_chat()
        app.processEvents()
        panel = win._chat_panel
        panel.add_message("你好呀，今天过得怎么样？", "pet")
        panel.add_message("还行吧，有点累", "user")
        panel.add_message("那要不要摸摸我？摸完就不累了。", "pet")
        app.processEvents()
        shot(panel, "app_chat")

    def step3() -> None:
        win.open_status()
        app.processEvents()
        win._status_panel.refresh(state, win.palette)
        app.processEvents()
        shot(win._status_panel, "app_status")

    def step4() -> None:
        win.open_settings()
        app.processEvents()
        shot(win._settings_panel, "app_settings")
        panel = win._settings_panel
        panel.provider_box.setCurrentIndex(panel.provider_box.findData("modelscope"))
        panel.llm_check.setChecked(True)
        app.processEvents()
        shot(panel, "app_settings_ms")

    def step5() -> None:
        # 互动测试
        before = dict(state.stats)
        win.feed("fish")
        app.processEvents()
        print("feed ->", win.bubble.label.text(), "| hunger",
              round(before["hunger"], 1), "->", round(state.stats["hunger"], 1))
        win.pat()
        app.processEvents()
        print("pat  ->", win.bubble.label.text())
        win.wash()
        app.processEvents()
        print("wash ->", win.bubble.label.text(), "| clean", round(state.stats["clean"], 1))
        win.play("yarn")
        app.processEvents()
        print("play ->", win.bubble.label.text())
        win.toggle_sleep()
        app.processEvents()
        print("sleep->", win.bubble.label.text(), "| sleeping:", state.sleeping)

    def step6() -> None:
        # 对话引擎抽样
        state.sleeping = False
        for q in ["你好", "你叫什么名字", "我好饿", "陪我玩", "我考试考砸了", "讲个笑话", "晚安"]:
            text, emo = dialogue.reply(q, state, "主人")
            print(f"Q {q} -> [{emo}] {text}")

    def step7() -> None:
        # 敲蛋流程
        egg = PetState()
        for i in range(3):
            res = egg.pat()
            print("egg pat", i + 1, "crack", egg.egg_crack, "|", res["text"][:30])
        print("hatched:", egg.hatched, "stage:", egg.stage_name, "achievements:", egg.achievements)

        # 存档往返
        again = PetState.from_dict(egg.to_dict())
        print("reload ok:", again.name, again.hatched, again.stage_name)
        print("days:", again.days)

        # 设置保存 + 缩放
        new_s = dict(settings)
        new_s.update({"pet_name": "布丁", "scale": 1.4, "palette": "薄荷奶绿"})
        win.apply_settings(new_s)
        app.processEvents()
        print("after settings: size", win.width(), "x", win.height(),
              "| name", win.state.name, "| palette", settings["palette"])
        shot(win, "app_pet_scaled")
        shot(win._status_panel, "app_status2")

        # 对话回归
        for q in ["陪我玩", "我考试考砸了", "你好", "晚安"]:
            text, emo = dialogue.reply(q, win.state, "主人")
            print(f"Q {q} -> [{emo}] {text}")

    def finish() -> None:
        app.quit()

    QTimer.singleShot(300, step1)
    QTimer.singleShot(600, step2)
    QTimer.singleShot(900, step3)
    QTimer.singleShot(1200, step4)
    QTimer.singleShot(1500, step5)
    QTimer.singleShot(1800, step6)
    QTimer.singleShot(2100, step7)
    QTimer.singleShot(2400, finish)

    app.exec()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
