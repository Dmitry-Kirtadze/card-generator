"""Панель шарів: дерево блоків (верхній шар — першим), видимість, замок, назви."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...model import Element, GroupElement, ShapeElement, Template

COL_NAME, COL_VISIBLE, COL_LOCKED = 0, 1, 2
TYPE_LABELS = {"text": "Текст", "icon": "Іконка", "photo": "Фото", "table": "Таблиця", "group": "Група"}
SHAPE_LABELS = {"rect": "Прямокутник", "ellipse": "Коло", "line": "Лінія"}


def element_label(e: Element) -> str:
    if e.name:
        return e.name
    if isinstance(e, ShapeElement):
        return SHAPE_LABELS.get(e.shape, "Фігура")
    return TYPE_LABELS.get(e.TYPE, e.TYPE)


class LayersPanel(QWidget):
    selectionChangedIds = Signal(list)
    visibilityToggled = Signal(str, bool)
    lockToggled = Signal(str, bool)
    renamed = Signal(str, str)
    reorderRequested = Signal(str)  # up | down | front | back
    groupRequested = Signal()
    ungroupRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self.items: dict[str, QTreeWidgetItem] = {}

        self.tree = QTreeWidget()
        self.tree.setObjectName("layersTree")
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Шар", "Видно", "Замок"])
        header = self.tree.header()
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_VISIBLE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_LOCKED, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                  | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        self.tree.itemChanged.connect(self._item_changed)

        buttons = QGridLayout()
        self.buttons: dict[str, QPushButton] = {}
        for i, (key, text, tip) in enumerate([
            ("up", "Вище", "На шар вище (Ctrl+])"),
            ("down", "Нижче", "На шар нижче (Ctrl+[)"),
            ("front", "Нагору", "На передній план (Ctrl+Shift+])"),
            ("back", "Донизу", "На задній план (Ctrl+Shift+[)"),
        ]):
            button = QPushButton(text)
            button.setToolTip(tip)
            button.setObjectName(f"layer_{key}")
            button.clicked.connect(lambda _=False, k=key: self.reorderRequested.emit(k))
            buttons.addWidget(button, i // 2, i % 2)
            self.buttons[key] = button
        group = QPushButton("Згрупувати")
        group.setToolTip("Ctrl+G")
        group.clicked.connect(self.groupRequested.emit)
        ungroup = QPushButton("Розгрупувати")
        ungroup.setToolTip("Ctrl+Shift+G")
        ungroup.clicked.connect(self.ungroupRequested.emit)
        buttons.addWidget(group, 2, 0)
        buttons.addWidget(ungroup, 2, 1)
        self.buttons["group"], self.buttons["ungroup"] = group, ungroup

        title = QLabel("Шари")
        title.setStyleSheet("font-weight: 600;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(title)
        layout.addWidget(self.tree, 1)
        layout.addLayout(buttons)

    # --- Побудова -----------------------------------------------------------

    def rebuild(self, template: Template, selected: set[str]) -> None:
        self._updating = True
        expanded = {eid for eid, item in self.items.items() if item.isExpanded()}
        self.tree.clear()
        self.items = {}

        def add(parent, elements: list[Element]) -> None:
            for e in reversed(elements):  # верхній шар — першим
                item = QTreeWidgetItem(parent)
                item.setText(COL_NAME, element_label(e))
                item.setData(COL_NAME, Qt.ItemDataRole.UserRole, e.id)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(COL_VISIBLE, Qt.CheckState.Checked if e.visible else Qt.CheckState.Unchecked)
                item.setCheckState(COL_LOCKED, Qt.CheckState.Checked if e.locked else Qt.CheckState.Unchecked)
                if not e.visible:
                    item.setForeground(COL_NAME, Qt.GlobalColor.gray)
                self.items[e.id] = item
                if isinstance(e, GroupElement):
                    add(item, e.children)
                    item.setExpanded(e.id in expanded)

        add(self.tree.invisibleRootItem(), template.elements)
        self._updating = False
        self.select_ids(selected)

    def select_ids(self, ids: set[str]) -> None:
        self._updating = True
        self.tree.clearSelection()
        for element_id in ids:
            item = self.items.get(element_id)
            if item is not None:
                item.setSelected(True)
                parent = item.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()
        self._updating = False

    def selected_ids(self) -> list[str]:
        return [i.data(COL_NAME, Qt.ItemDataRole.UserRole) for i in self.tree.selectedItems()]

    # --- Події --------------------------------------------------------------

    def _selection_changed(self) -> None:
        if not self._updating:
            self.selectionChangedIds.emit(self.selected_ids())

    def _item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating:
            return
        element_id = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
        if column == COL_VISIBLE:
            self.visibilityToggled.emit(element_id, item.checkState(COL_VISIBLE) == Qt.CheckState.Checked)
        elif column == COL_LOCKED:
            self.lockToggled.emit(element_id, item.checkState(COL_LOCKED) == Qt.CheckState.Checked)
        elif column == COL_NAME:
            self.renamed.emit(element_id, item.text(COL_NAME).strip())
