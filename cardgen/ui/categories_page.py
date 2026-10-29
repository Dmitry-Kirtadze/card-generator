"""Головний екран: список категорій."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidgetItem, QVBoxLayout, QWidget

from ..storage import StorageError, Workspace
from ..transfer import EXTENSION, export_category, import_category
from . import dialogs
from .common import THUMB_SIZE, ActionSet, make_grid_list, plural
from .thumbnails import ThumbnailLoader

ARCHIVE_FILTER = f"Категорія (*{EXTENSION} *.zip)"


class CategoriesPage(QWidget):
    open_category = Signal(str)
    open_library = Signal()
    open_updates = Signal()

    def __init__(self, workspace: Workspace, parent: QWidget | None = None):
        super().__init__(parent)
        self.workspace = workspace

        title = QLabel("Категорії")
        title.setObjectName("pageTitle")

        self.grid = make_grid_list(self)
        self.thumbs = ThumbnailLoader(self.grid, workspace, THUMB_SIZE)
        self.grid.setObjectName("categoriesGrid")
        self.grid.itemActivated.connect(lambda item: self.open_category.emit(item.data(Qt.ItemDataRole.UserRole)))
        self.grid.itemSelectionChanged.connect(self._update_buttons)
        self.grid.customContextMenuRequested.connect(self._show_menu)

        self.empty_hint = QLabel("Ще немає жодної категорії. Натисніть «Нова категорія».")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setObjectName("emptyHint")

        a = self.actions = ActionSet(self)
        toolbar = QHBoxLayout()
        toolbar.addWidget(a.add("new", "Нова категорія", self.create_category, shortcut=QKeySequence.StandardKey.New))
        toolbar.addWidget(a.add("open", "Відкрити", self._open_selected, needs_selection=True))
        toolbar.addWidget(a.add("rename", "Перейменувати", self.rename_selected, shortcut="F2", needs_selection=True))
        toolbar.addWidget(a.add("duplicate", "Дублювати", self.duplicate_selected, shortcut="Ctrl+D", needs_selection=True))
        toolbar.addWidget(a.add("delete", "Видалити", self.delete_selected, shortcut=QKeySequence.StandardKey.Delete, needs_selection=True))
        toolbar.addSpacing(24)
        toolbar.addWidget(a.add("export", "Експорт…", self.export_selected, needs_selection=True))
        toolbar.addWidget(a.add("import", "Імпорт…", self.import_archive))
        toolbar.addStretch()
        toolbar.addWidget(a.add("library", "Бібліотека", self.open_library.emit))
        toolbar.addWidget(a.add("updates", "Оновлення…", self.open_updates.emit))

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addLayout(toolbar)
        layout.addWidget(self.empty_hint)
        layout.addWidget(self.grid, 1)

        self.refresh()

    # --- Дані -------------------------------------------------------------

    def refresh(self, select_id: str | None = None) -> None:
        select_id = select_id or self.selected_id()
        self.grid.blockSignals(True)  # під час перебудови виділення вказує на старі елементи
        self.thumbs.reset()
        self.grid.clear()
        for category in self.workspace.list_categories():
            try:
                templates = self.workspace.list_templates(category.id)
            except StorageError:
                templates = []
            icon = self.thumbs.icon_for(category.id, templates[0] if templates else None, category.id)
            count = plural(len(templates), 'шаблон', 'шаблони', 'шаблонів')
            if category.protected:
                text = f"{category.name} · готові\n{count}"
            else:
                text = f"{category.name}\n{count}"
            item = QListWidgetItem(icon, text)
            item.setData(Qt.ItemDataRole.UserRole, category.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, category.protected)
            if category.protected:
                item.setToolTip("Готові шаблони. Скопіюйте потрібний у свою категорію. "
                                "Цю категорію не можна видалити чи перейменувати.")
            self.grid.addItem(item)
            if category.id == select_id:
                item.setSelected(True)
                self.grid.setCurrentItem(item)
        self.grid.blockSignals(False)
        self.empty_hint.setVisible(self.grid.count() == 0)
        self._update_buttons()

    def selected_id(self) -> str | None:
        items = self.grid.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def _update_buttons(self) -> None:
        self.actions.set_has_selection(self.selected_id() is not None)
        items = self.grid.selectedItems()
        if items and items[0].data(Qt.ItemDataRole.UserRole + 1):  # Маркет
            for key in ("rename", "delete"):
                self.actions.buttons[key].setEnabled(False)
                self.actions.actions[key].setEnabled(False)

    def _show_menu(self, pos) -> None:
        if self.grid.itemAt(pos) is None:
            menu = self.actions.context_menu(["new", "import"])
        else:
            menu = self.actions.context_menu(["open", "rename", "duplicate", "-", "export", "-", "delete"])
        menu.exec(self.grid.viewport().mapToGlobal(pos))

    # --- Дії --------------------------------------------------------------

    def _open_selected(self) -> None:
        if (cid := self.selected_id()) is not None:
            self.open_category.emit(cid)

    def create_category(self) -> None:
        name = dialogs.ask_text(self, "Нова категорія", "Назва категорії:")
        if name is None:
            return
        try:
            category = self.workspace.create_category(name)
        except StorageError as e:
            dialogs.error(self, str(e))
            return
        self.refresh(category.id)

    def rename_selected(self) -> None:
        cid = self.selected_id()
        if cid is None:
            return
        category = self.workspace.get_category(cid)
        if category.protected:
            dialogs.error(self, f"Категорію «{category.name}» не можна перейменувати")
            return
        current = category.name
        name = dialogs.ask_text(self, "Перейменувати категорію", "Нова назва:", current)
        if name is None:
            return
        try:
            self.workspace.rename_category(cid, name)
        except StorageError as e:
            dialogs.error(self, str(e))
        self.refresh(cid)

    def duplicate_selected(self) -> None:
        cid = self.selected_id()
        if cid is None:
            return
        try:
            copy = self.workspace.duplicate_category(cid)
        except StorageError as e:
            dialogs.error(self, str(e))
            return
        self.refresh(copy.id)

    def delete_selected(self) -> None:
        cid = self.selected_id()
        if cid is None:
            return
        category = self.workspace.get_category(cid)
        if category.protected:
            dialogs.error(self, f"Категорію «{category.name}» не можна видалити — це вбудований Маркет шаблонів")
            return
        name = category.name
        if not dialogs.confirm(self, "Видалити категорію",
                               f"Видалити категорію «{name}» з усіма шаблонами й таблицями?\n\n"
                               "Її буде переміщено в папку trash робочої папки."):
            return
        self.workspace.delete_category(cid)
        self.refresh()

    def export_selected(self) -> None:
        cid = self.selected_id()
        if cid is None:
            return
        name = self.workspace.get_category(cid).name
        target = dialogs.save_file(self, "Експорт категорії", f"{name}{EXTENSION}", ARCHIVE_FILTER)
        if target is None:
            return
        if not target.name.lower().endswith((EXTENSION, ".zip")):
            target = target.with_name(target.name + EXTENSION)
        try:
            export_category(self.workspace, cid, target)
        except (StorageError, OSError) as e:
            dialogs.error(self, f"Не вдалося експортувати: {e}")
            return
        dialogs.info(self, "Експорт", f"Категорію збережено у файл:\n{target}")

    def import_archive(self) -> None:
        source = dialogs.open_file(self, "Імпорт категорії", ARCHIVE_FILTER)
        if source is None:
            return
        try:
            category = import_category(self.workspace, source)
        except (StorageError, OSError) as e:
            dialogs.error(self, f"Не вдалося імпортувати: {e}")
            return
        self.refresh(category.id)
        dialogs.info(self, "Імпорт", f"Категорію «{category.name}» імпортовано.")
