"""桌面宠物 · 启动入口。

    python main.py
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from pet import config, dialogue
from pet.pet_window import PetWindow
from pet.state import PetState

SERVER_NAME = "DesktopPet-SingleInstance"


def _already_running() -> bool:
    """单实例：若已有进程在跑，通知它显示出来。"""
    try:
        from PySide6.QtNetwork import QLocalSocket
    except ImportError:
        return False

    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(250):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(250)
        sock.disconnectFromServer()
        return True
    return False


def _listen_for_second_launch(window: PetWindow):
    try:
        from PySide6.QtNetwork import QLocalServer
    except ImportError:
        return None

    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer(window)
    if not server.listen(SERVER_NAME):
        return None

    def on_new() -> None:
        conn = server.nextPendingConnection()
        if conn is None:
            return
        conn.readyRead.connect(conn.readAll)
        conn.disconnected.connect(conn.deleteLater)
        window.show()
        window.raise_()
        window.activateWindow()

    server.newConnection.connect(on_new)
    return server


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationDisplayName(config.APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    font = QFont()
    font.setFamilies(config.app_font_family())
    font.setPixelSize(13)
    app.setFont(font)

    if _already_running():
        return 0

    settings = config.load_settings()
    state = PetState.load()
    state.name = settings.get("pet_name", state.name)

    overdue = state.apply_overdue(float(settings.get("decay_speed", 1.0)))
    state.mark_today()

    window = PetWindow(state, settings)
    app.setWindowIcon(QIcon(window.windowIcon()))
    window.show()

    server = _listen_for_second_launch(window)  # noqa: F841 保持引用

    if overdue:
        text, emo = dialogue.event_line("overdue", state, settings.get("owner_name", "主人"))
        QTimer.singleShot(1200, lambda: window.say(text, emo, 4200))

    autosave = QTimer(window)
    autosave.setInterval(600000)
    autosave.timeout.connect(state.save)
    autosave.start()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
