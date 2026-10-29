"""Спільна бібліотека: шрифти, іконки, фони."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..storage import LIBRARY_EXTENSIONS, StorageError, Workspace
from . import dialogs
from .common import make_grid_list
from .fonts import forget_font, register_library_fonts

SECTIONS = [
    ("fonts", "Шрифти"),
    ("icons", "Іконки"),
    ("backgrounds", "Фони"),
]
FONT_SAMPLE = "Кабель AWG 18 — Аа Бб Єє Іі Її 0123"


def _file_filter(section: str) -> str:
    return "Файли (" + " ".join(f"*{ext}" for ext in LIBRARY_EXTENSIONS[section]) + ")"


class LibrarySection(QWidget):
    def __init__(self, workspace: Workspace, section: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.workspace = workspace
        self.section = section

        if section == "fonts":
            self.list = QListWidget()
            hint = "Шрифти .ttf / .otf. Після додавання вони одразу доступні в редакторі."
        else:
            self.list = make_grid_list()
            self.list.setIconSize(QSize(96, 96))
            self.list.setGridSize(QSize(130, 140))
            hint = ("Іконки: .png, .svg (бажано з прозорим фоном)." if section == "icons"
                    else "Фонові зображення: .png, .jpg, .webp.")
        self.list.setObjectName(f"list_{section}")
        self.list.itemSelectionChanged.connect(self._update_buttons)

        add = QPushButton("Додати…")
        add.setObjectName(f"btn_add_{section}")
        add.clicked.connect(self.add_files)
        self.delete_button = QPushButton("Видалити")
        self.delete_button.setObjectName(f"btn_delete_{section}")
        self.delete_button.clicked.connect(self.delete_selected)
        buttons = QHBoxLayout()
        buttons.addWidget(add)
        buttons.addWidget(self.delete_button)
        buttons.addStretch()

        hint_label = QLabel(hint)
        hint_label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(hint_label)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        if self.section == "fonts":
            register_library_fonts(self.workspace)
            for family, paths in sorted(self.workspace.library_fonts().items()):
                for path in paths:
                    item = QListWidgetItem(f"{family}  ·  {path.name}\n{FONT_SAMPLE}")
                    item.setFont(QFont(family, 14))
                    item.setData(Qt.ItemDataRole.UserRole, path.name)
                    self.list.addItem(item)
        else:
            for path in self.workspace.list_library(self.section):
                image = QImage(str(path))
                pixmap = QPixmap.fromImage(image) if not image.isNull() else QPixmap()
                item = QListWidgetItem(QIcon(pixmap), path.name)
                item.setData(Qt.ItemDataRole.UserRole, path.name)
                self.list.addItem(item)
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.delete_button.setEnabled(bool(self.list.selectedItems()))

    def add_files(self) -> None:
        errors = []
        for path in dialogs.open_files(self, "Додати в бібліотеку", _file_filter(self.section)):
            try:
                self.workspace.add_to_library(self.section, path)
            except (StorageError, OSError) as e:
                errors.append(str(e))
        if errors:
            dialogs.error(self, "\n".join(errors))
        self.refresh()

    def delete_selected(self) -> None:
        items = self.list.selectedItems()
        if not items:
            return
        filename = items[0].data(Qt.ItemDataRole.UserRole)
        if not dialogs.confirm(self, "Видалити з бібліотеки",
                               f"Видалити «{filename}» з бібліотеки?\n\n"
                               "Шаблони, які його використовують, показуватимуть порожнє місце."):
            return
        path = self.workspace.library_dir / self.section / filename
        if self.section == "fonts":
            forget_font(path)
        self.workspace.remove_from_library(self.section, filename)
        self.refresh()


class LibraryDialog(QDialog):
    def __init__(self, workspace: Workspace, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Бібліотека")
        self.resize(820, 600)
        self.tabs = QTabWidget()
        self.sections: dict[str, LibrarySection] = {}
        for key, title in SECTIONS:
            section = LibrarySection(workspace, key)
            self.sections[key] = section
            self.tabs.addTab(section, title)
        close = QPushButton("Закрити")
        close.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addStretch()
        bottom.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(bottom)
