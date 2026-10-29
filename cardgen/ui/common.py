"""Спільні дрібниці інтерфейсу."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QAbstractItemView, QListView, QListWidget, QMenu, QPushButton, QWidget

THUMB_SIZE = 180


def plural(n: int, one: str, few: str, many: str) -> str:
    """Українська множина: 1 шаблон, 2 шаблони, 5 шаблонів."""
    if n % 10 == 1 and n % 100 != 11:
        word = one
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = few
    else:
        word = many
    return f"{n} {word}"


def make_grid_list(parent: QWidget | None = None) -> QListWidget:
    grid = QListWidget(parent)
    grid.setViewMode(QListView.ViewMode.IconMode)
    grid.setIconSize(QSize(THUMB_SIZE, THUMB_SIZE))
    grid.setGridSize(QSize(THUMB_SIZE + 40, THUMB_SIZE + 60))
    grid.setResizeMode(QListView.ResizeMode.Adjust)
    grid.setMovement(QListView.Movement.Static)
    grid.setWordWrap(True)
    grid.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    grid.setSpacing(8)
    return grid


class ActionSet:
    """Дія = кнопка + пункт контекстного меню + гаряча клавіша."""

    def __init__(self, owner: QWidget):
        self.owner = owner
        self.buttons: dict[str, QPushButton] = {}
        self.actions: dict[str, QAction] = {}
        self.needs_selection: set[str] = set()

    def add(self, key: str, text: str, handler: Callable[[], None], *,
            shortcut: QKeySequence | QKeySequence.StandardKey | str | None = None,
            needs_selection: bool = False) -> QPushButton:
        button = QPushButton(text, self.owner)
        button.setObjectName(f"btn_{key}")
        button.clicked.connect(handler)
        self.buttons[key] = button
        action = QAction(text, self.owner)
        action.triggered.connect(handler)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.owner.addAction(action)
        self.actions[key] = action
        if needs_selection:
            self.needs_selection.add(key)
        return button

    def set_has_selection(self, has: bool) -> None:
        for key in self.needs_selection:
            self.buttons[key].setEnabled(has)
            self.actions[key].setEnabled(has)

    def context_menu(self, keys: list[str]) -> QMenu:
        menu = QMenu(self.owner)
        for key in keys:
            if key == "-":
                menu.addSeparator()
            else:
                menu.addAction(self.actions[key])
        return menu
