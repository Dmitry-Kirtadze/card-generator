"""Стандартні діалоги. Зібрані в одному місці, щоб у тестах їх легко підмінити."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QInputDialog, QLineEdit, QMessageBox, QWidget


def ask_text(parent: QWidget, title: str, label: str, text: str = "") -> str | None:
    value, ok = QInputDialog.getText(parent, title, label, QLineEdit.EchoMode.Normal, text)
    return value if ok else None


def ask_choice(parent: QWidget, title: str, label: str, options: list[str]) -> str | None:
    value, ok = QInputDialog.getItem(parent, title, label, options, 0, False)
    return value if ok else None


def confirm(parent: QWidget, title: str, text: str) -> bool:
    answer = QMessageBox.question(parent, title, text)
    return answer == QMessageBox.StandardButton.Yes


def info(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


def error(parent: QWidget, text: str) -> None:
    QMessageBox.warning(parent, "Помилка", text)


def open_files(parent: QWidget, title: str, filters: str) -> list[Path]:
    files, _ = QFileDialog.getOpenFileNames(parent, title, "", filters)
    return [Path(f) for f in files]


def open_file(parent: QWidget, title: str, filters: str) -> Path | None:
    file, _ = QFileDialog.getOpenFileName(parent, title, "", filters)
    return Path(file) if file else None


def open_dir(parent: QWidget, title: str, start: str = "") -> Path | None:
    folder = QFileDialog.getExistingDirectory(parent, title, start)
    return Path(folder) if folder else None


def save_file(parent: QWidget, title: str, suggested: str, filters: str) -> Path | None:
    file, _ = QFileDialog.getSaveFileName(parent, title, suggested, filters)
    return Path(file) if file else None
