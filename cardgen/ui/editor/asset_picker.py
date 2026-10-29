"""Вибір файлу з бібліотеки (іконки, фони) з можливістю одразу додати новий."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QListWidgetItem, QPushButton, QVBoxLayout

from ...storage import LIBRARY_EXTENSIONS, StorageError, Workspace, library_ref
from .. import dialogs
from ..common import make_grid_list

TITLES = {"icons": "Вибір іконки", "backgrounds": "Вибір фону"}


class AssetPicker(QDialog):
    def __init__(self, workspace: Workspace, section: str, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.section = section
        self.selected_ref: str | None = None
        self.setWindowTitle(TITLES.get(section, "Бібліотека"))
        self.resize(640, 480)

        self.list = make_grid_list()
        self.list.setIconSize(QSize(96, 96))
        self.list.setGridSize(QSize(130, 140))
        self.list.itemActivated.connect(lambda _item: self._accept_selected())

        add = QPushButton("Додати з файлу…")
        add.clicked.connect(self._add)
        choose = QPushButton("Вибрати")
        choose.setDefault(True)
        choose.clicked.connect(self._accept_selected)
        cancel = QPushButton("Скасувати")
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(add)
        buttons.addStretch()
        buttons.addWidget(choose)
        buttons.addWidget(cancel)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self, select_name: str | None = None) -> None:
        self.list.clear()
        for path in self.workspace.list_library(self.section):
            image = QImage(str(path))
            item = QListWidgetItem(QIcon(QPixmap.fromImage(image)), path.name)
            item.setData(Qt.ItemDataRole.UserRole, path.name)
            self.list.addItem(item)
            if path.name == select_name:
                self.list.setCurrentItem(item)

    def _add(self) -> None:
        filters = "Зображення (" + " ".join(f"*{e}" for e in LIBRARY_EXTENSIONS[self.section]) + ")"
        last = None
        for path in dialogs.open_files(self, "Додати в бібліотеку", filters):
            try:
                last = self.workspace.add_to_library(self.section, path)
            except (StorageError, OSError) as e:
                dialogs.error(self, str(e))
        self.refresh(last.split("/")[-1] if last else None)

    def _accept_selected(self) -> None:
        items = self.list.selectedItems()
        if items:
            self.selected_ref = library_ref(self.section, items[0].data(Qt.ItemDataRole.UserRole))
            self.accept()


def pick_asset(parent, workspace: Workspace, section: str) -> str | None:
    picker = AssetPicker(workspace, section, parent)
    return picker.selected_ref if picker.exec() == QDialog.DialogCode.Accepted else None
