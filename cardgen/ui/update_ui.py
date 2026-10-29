"""Оновлення програми в інтерфейсі: фонова перевірка при запуску, вікно «Оновлення»."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..storage import Workspace
from ..updater import UpdateError, UpdateInfo, Updater
from . import dialogs


class _Worker(QObject):
    done = Signal(object)  # UpdateInfo або UpdateError

    def __init__(self, updater: Updater, install: bool):
        super().__init__()
        self.updater = updater
        self.install = install

    def run(self) -> None:
        try:
            if self.install:
                changes = self.updater.apply()
                self.done.emit(UpdateInfo(available=bool(changes), behind=len(changes), changes=changes))
            else:
                self.done.emit(self.updater.check())
        except UpdateError as e:
            self.done.emit(e)


class BackgroundTask(QObject):
    """Перевірка/встановлення в окремому потоці, щоб вікно не «замерзало»."""

    finished = Signal(object)

    def __init__(self, updater: Updater, install: bool, parent=None):
        super().__init__(parent)
        self.thread = QThread(self)
        self.worker = _Worker(updater, install)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.done.connect(self._done)

    def start(self) -> None:
        self.thread.start()

    def _done(self, result) -> None:
        self.thread.quit()
        self.thread.wait()
        self.finished.emit(result)


def auto_install_enabled(workspace: Workspace) -> bool:
    return bool(workspace.editor_settings().get("auto_update", True))


def restart(app_dir: Path) -> None:
    """Запустити програму заново й закрити поточну (вікно збереже зміни в closeEvent)."""
    window = QApplication.activeWindow()
    if window is not None and not window.close():
        return
    if getattr(sys, "frozen", False):  # CardGen.exe сам вибере оновлений код
        QProcess.startDetached(sys.executable, [], str(Path(sys.executable).parent))
    else:
        QProcess.startDetached(sys.executable, [str(app_dir / "main.py")], str(app_dir))
    QApplication.quit()


def changes_text(changes: list[str], limit: int = 12) -> str:
    lines = [f"• {c}" for c in changes[:limit]]
    if len(changes) > limit:
        lines.append(f"… і ще {len(changes) - limit}")
    return "\n".join(lines)


class UpdateDialog(QDialog):
    """Вікно «Оновлення»: перевірити, встановити, увімкнути автоматичне встановлення."""

    def __init__(self, updater: Updater, workspace: Workspace, parent: QWidget | None = None):
        super().__init__(parent)
        self.updater = updater
        self.workspace = workspace
        self.info: UpdateInfo | None = None
        self.task: BackgroundTask | None = None
        self.installed = False
        self.setWindowTitle("Оновлення програми")
        self.resize(560, 380)

        self.status = QLabel(f"Версія {__version__}")
        self.status.setObjectName("updateStatus")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.auto = QCheckBox("Встановлювати оновлення автоматично під час запуску")
        self.auto.setObjectName("autoUpdate")
        self.auto.setChecked(auto_install_enabled(workspace))
        self.auto.toggled.connect(lambda on: workspace.save_editor_settings(auto_update=on))

        self.check_button = QPushButton("Перевірити")
        self.check_button.setObjectName("btn_check")
        self.check_button.clicked.connect(self.check)
        self.install_button = QPushButton("Встановити")
        self.install_button.setObjectName("btn_install")
        self.install_button.setEnabled(False)
        self.install_button.clicked.connect(self.install)
        self.restart_button = QPushButton("Перезапустити")
        self.restart_button.setObjectName("btn_restart")
        self.restart_button.setVisible(False)
        self.restart_button.clicked.connect(lambda: restart(updater.app_dir))
        close = QPushButton("Закрити")
        close.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        for b in (self.check_button, self.install_button, self.restart_button):
            buttons.addWidget(b)
        buttons.addStretch()
        buttons.addWidget(close)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status, 1)
        layout.addWidget(self.auto)
        layout.addLayout(buttons)

    def _busy(self, text: str) -> None:
        self.status.setText(text)
        self.check_button.setEnabled(False)
        self.install_button.setEnabled(False)

    def check(self) -> None:
        self._busy("Перевірка оновлень…")
        self._start(install=False)

    def install(self) -> None:
        self._busy("Встановлення оновлення… Це може зайняти хвилину.")
        self._start(install=True)

    def _start(self, install: bool) -> None:
        self.task = BackgroundTask(self.updater, install, self)
        self.task.finished.connect(lambda result: self.show_result(result, install))
        self.task.start()

    def show_result(self, result, installed: bool) -> None:
        self.check_button.setEnabled(True)
        if isinstance(result, UpdateError):
            self.status.setText(f"Не вдалося: {result}")
            return
        if installed:
            self.installed = True
            self.status.setText("Оновлення встановлено. Перезапустіть програму, щоб воно запрацювало.\n\n"
                                + changes_text(result.changes))
            self.restart_button.setVisible(True)
            return
        self.info = result
        if result.available:
            self.status.setText(f"Доступне оновлення: {result.behind} змін (версія {result.current} → "
                                f"{result.latest}).\n\n{changes_text(result.changes)}")
            self.install_button.setEnabled(True)
        else:
            self.status.setText(f"У вас остання версія ({__version__}, {result.current}).")


class StartupUpdater(QObject):
    """Фонова перевірка після запуску. З автооновленням — одразу встановлює й пропонує перезапуск."""

    def __init__(self, window: QWidget, updater: Updater, workspace: Workspace):
        super().__init__(window)
        self.window = window
        self.updater = updater
        self.workspace = workspace
        self.task: BackgroundTask | None = None

    def start(self) -> None:
        if not self.updater.supported()[0]:
            return
        install = auto_install_enabled(self.workspace)
        self.task = BackgroundTask(self.updater, install, self)
        self.task.finished.connect(lambda result: self._finished(result, install))
        self.task.start()

    def _finished(self, result, installed: bool) -> None:
        if isinstance(result, UpdateError) or not result.available:
            return  # тихо: без інтернету чи без оновлень не заважаємо роботі
        if installed:
            if dialogs.confirm(self.window, "Програму оновлено",
                               "Встановлено оновлення:\n" + changes_text(result.changes) +
                               "\n\nПерезапустити програму зараз?"):
                restart(self.updater.app_dir)
        elif dialogs.confirm(self.window, "Доступне оновлення",
                             f"Нових змін: {result.behind}\n\n" + changes_text(result.changes) +
                             "\n\nВстановити зараз?"):
            dialog = UpdateDialog(self.updater, self.workspace, self.window)
            dialog.install()
            dialog.exec()
