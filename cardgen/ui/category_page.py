"""Екран категорії: шаблони-картки та завантажені до них таблиці даних."""
from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..data.dataset import images_dir, load_dataset
from ..data.fields import build_schema
from ..data.validate import validate
from ..market import MARKET_ID, copy_template, ensure_market
from ..storage import TABLE_EXTENSIONS, StorageError, Workspace
from . import dialogs, export_dialog
from .common import THUMB_SIZE, ActionSet, make_grid_list
from .template_dialog import TemplateValues, ask_template
from .thumbnails import ThumbnailLoader

TABLE_FILTER = "Таблиці (" + " ".join(f"*{ext}" for ext in TABLE_EXTENSIONS) + ")"


class CategoryPage(QWidget):
    back = Signal()
    edit_template = Signal(str, str)  # id категорії, id шаблону
    open_data = Signal(str, str, str)  # id категорії, id шаблону, файл для імпорту ("" — без імпорту)
    open_preview = Signal(str, str)  # id категорії, id шаблону

    def __init__(self, workspace: Workspace, parent: QWidget | None = None):
        super().__init__(parent)
        self.workspace = workspace
        self.category_id: str | None = None
        self.is_market = False

        back_button = QPushButton("← Категорії")
        back_button.setObjectName("btn_back")
        back_button.clicked.connect(self.back.emit)
        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        header = QHBoxLayout()
        header.addWidget(back_button)
        header.addWidget(self.title, 1)

        # --- шаблони
        self.grid = make_grid_list(self)
        self.thumbs = ThumbnailLoader(self.grid, workspace, THUMB_SIZE)
        self.grid.setObjectName("templatesGrid")
        self.grid.itemActivated.connect(lambda _item: self.edit_selected())
        self.grid.itemSelectionChanged.connect(self._selection_changed)
        self.grid.customContextMenuRequested.connect(self._show_menu)
        self.empty_hint = QLabel("У категорії ще немає шаблонів. Натисніть «Новий шаблон».")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        a = self.actions = ActionSet(self)
        toolbar = QHBoxLayout()
        toolbar.addWidget(a.add("new", "Новий шаблон", self.create_template, shortcut=QKeySequence.StandardKey.New))
        toolbar.addWidget(a.add("edit", "Змінити", self.edit_selected, needs_selection=True))
        toolbar.addWidget(a.add("settings", "Налаштування…", self.settings_selected, shortcut="F2", needs_selection=True))
        toolbar.addWidget(a.add("duplicate", "Дублювати", self.duplicate_selected, shortcut="Ctrl+D", needs_selection=True))
        toolbar.addWidget(a.add("delete", "Видалити", self.delete_selected, shortcut=QKeySequence.StandardKey.Delete, needs_selection=True))
        toolbar.addSpacing(16)
        toolbar.addWidget(a.add("copy_to", "Скопіювати в категорію…", self.copy_to_category, needs_selection=True))
        toolbar.addWidget(a.add("to_market", "Додати в Маркет", self.add_to_market, needs_selection=True))
        toolbar.addStretch()
        toolbar.addWidget(a.add("export_jpeg", "Експорт JPEG…", self.export_jpeg))
        self.market_hint = QLabel("🛒 Готові шаблони. Виберіть шаблон і натисніть «Скопіювати в категорію…» — "
                                  "копія з'явиться у вашій категорії разом із прикладом товару.")
        self.market_hint.setObjectName("marketHint")
        self.market_hint.setWordWrap(True)
        self.market_hint.setStyleSheet("color: #12B76A;")

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.market_hint)
        left_layout.addLayout(toolbar)
        left_layout.addWidget(self.empty_hint)
        left_layout.addWidget(self.grid, 1)

        # --- таблиці вибраного шаблону
        self.tables_box = QGroupBox("Таблиці даних")
        self.tables_list = QListWidget()
        self.tables_list.setObjectName("tablesList")
        self.tables_list.itemSelectionChanged.connect(self._update_table_buttons)
        self.tables_hint = QLabel("Виберіть шаблон, щоб побачити його таблиці.")
        self.tables_hint.setWordWrap(True)
        self.data_summary = QLabel()
        self.data_summary.setObjectName("dataSummary")
        self.data_summary.setWordWrap(True)
        self.data_button = QPushButton("Дані товарів…")
        self.data_button.setObjectName("btn_data")
        self.data_button.clicked.connect(lambda: self._emit_open_data(""))
        self.add_table_button = QPushButton("Імпорт таблиці…")
        self.add_table_button.setObjectName("btn_add_table")
        self.add_table_button.clicked.connect(self.add_tables)
        self.reimport_button = QPushButton("Завантажити знову")
        self.reimport_button.setObjectName("btn_reimport")
        self.reimport_button.setToolTip("Імпортувати вибрану раніше завантажену таблицю ще раз")
        self.reimport_button.clicked.connect(self.reimport_selected)
        self.delete_table_button = QPushButton("Видалити")
        self.delete_table_button.setObjectName("btn_delete_table")
        self.delete_table_button.clicked.connect(self.delete_selected_table)
        self.open_folder_button = QPushButton("Відкрити папку")
        self.open_folder_button.clicked.connect(self.open_tables_folder)
        self.preview_button = QPushButton("Перегляд карток…")
        self.preview_button.setObjectName("btn_preview")
        self.preview_button.clicked.connect(self._emit_preview)
        top_buttons = QHBoxLayout()
        top_buttons.addWidget(self.data_button)
        top_buttons.addWidget(self.add_table_button)
        top_buttons.addWidget(self.preview_button)
        table_buttons = QHBoxLayout()
        table_buttons.addWidget(self.reimport_button)
        table_buttons.addWidget(self.delete_table_button)
        table_buttons.addWidget(self.open_folder_button)
        history = QLabel("Завантажені таблиці:")
        history.setStyleSheet("color: #6B7280;")
        tables_layout = QVBoxLayout(self.tables_box)
        tables_layout.addWidget(self.tables_hint)
        tables_layout.addWidget(self.data_summary)
        tables_layout.addLayout(top_buttons)
        tables_layout.addWidget(history)
        tables_layout.addWidget(self.tables_list, 1)
        tables_layout.addLayout(table_buttons)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self.tables_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(splitter, 1)

    # --- Дані -------------------------------------------------------------

    def show_category(self, category_id: str) -> None:
        self.category_id = category_id
        self.refresh()

    def refresh(self, select_id: str | None = None) -> None:
        if self.category_id is None:
            return
        select_id = select_id or self.selected_id()
        category = self.workspace.get_category(self.category_id)
        self.is_market = category.protected
        self.title.setText(("🛒 " if self.is_market else "") + category.name)
        self.market_hint.setVisible(self.is_market)
        self.actions.buttons["to_market"].setVisible(not self.is_market)
        self.grid.blockSignals(True)  # під час перебудови виділення вказує на старі елементи
        self.thumbs.reset()
        self.grid.clear()
        for template in self.workspace.list_templates(self.category_id):
            icon = self.thumbs.icon_for(template.id, template, self.category_id)
            item = QListWidgetItem(icon, f"{template.name}\n{template.width} × {template.height}")
            item.setData(Qt.ItemDataRole.UserRole, template.id)
            self.grid.addItem(item)
            if template.id == select_id:
                item.setSelected(True)
                self.grid.setCurrentItem(item)
        self.grid.blockSignals(False)
        self.empty_hint.setVisible(self.grid.count() == 0)
        self._selection_changed()

    def selected_id(self) -> str | None:
        items = self.grid.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def _selection_changed(self) -> None:
        self.actions.set_has_selection(self.selected_id() is not None)
        self.refresh_tables()

    def _show_menu(self, pos) -> None:
        if self.grid.itemAt(pos) is None:
            menu = self.actions.context_menu(["new"])
        else:
            share = ["copy_to"] if self.is_market else ["copy_to", "to_market"]
            menu = self.actions.context_menu(["edit", "settings", "duplicate", "-", *share, "-", "delete"])
        menu.exec(self.grid.viewport().mapToGlobal(pos))

    # --- Дії з шаблонами ---------------------------------------------------

    def create_template(self) -> None:
        values = ask_template(self, title="Новий шаблон")
        if values is None:
            return
        try:
            template = self.workspace.create_template(self.category_id, values.name, values.width,
                                                      values.height)
        except StorageError as e:
            dialogs.error(self, str(e))
            return
        self.refresh(template.id)

    def edit_selected(self) -> None:
        if (tid := self.selected_id()) is not None:
            self.edit_template.emit(self.category_id, tid)

    def settings_selected(self) -> None:
        tid = self.selected_id()
        if tid is None:
            return
        template = self.workspace.load_template(self.category_id, tid)
        export = template.export
        current = TemplateValues(template.name, template.width, template.height, export.number,
                                 export.filename_mask, export.jpeg_quality)
        values = ask_template(self, title="Налаштування шаблону", values=current, show_export=True)
        if values is None:
            return
        try:
            if values.name.strip() != template.name:
                template = self.workspace.rename_template(self.category_id, tid, values.name)
            template.width, template.height = values.width, values.height
            template.export.number = values.number
            template.export.filename_mask = values.filename_mask
            template.export.jpeg_quality = values.jpeg_quality
            self.workspace.save_template(self.category_id, template)
        except StorageError as e:
            dialogs.error(self, str(e))
        self.refresh(tid)

    def copy_to_category(self) -> None:
        """Копія вибраного шаблону в іншу (або нову) категорію."""
        tid = self.selected_id()
        if tid is None:
            return
        targets = [c for c in self.workspace.list_categories()
                   if not c.protected and c.id != self.category_id]
        new_label = "➕ Нова категорія…"
        choice = dialogs.ask_choice(self, "Скопіювати шаблон", "У яку категорію скопіювати шаблон?",
                                    [c.name for c in targets] + [new_label])
        if choice is None:
            return
        try:
            if choice == new_label:
                name = dialogs.ask_text(self, "Нова категорія", "Назва категорії:")
                if name is None:
                    return
                target = self.workspace.create_category(name)
            else:
                target = next(c for c in targets if c.name == choice)
            copy = copy_template(self.workspace, self.category_id, tid, target.id)
        except (StorageError, OSError) as e:
            dialogs.error(self, f"Не вдалося скопіювати: {e}")
            return
        dialogs.info(self, "Скопійовано", f"Шаблон «{copy.name}» скопійовано в категорію «{target.name}».")

    def add_to_market(self) -> None:
        tid = self.selected_id()
        if tid is None:
            return
        try:
            ensure_market(self.workspace)
            copy = copy_template(self.workspace, self.category_id, tid, MARKET_ID)
        except (StorageError, OSError) as e:
            dialogs.error(self, f"Не вдалося додати в Маркет: {e}")
            return
        dialogs.info(self, "Маркет", f"Шаблон «{copy.name}» додано в Маркет — тепер його можна "
                                     "скопіювати в будь-яку категорію.")

    def duplicate_selected(self) -> None:
        tid = self.selected_id()
        if tid is None:
            return
        copy = self.workspace.duplicate_template(self.category_id, tid)
        self.refresh(copy.id)

    def delete_selected(self) -> None:
        tid = self.selected_id()
        if tid is None:
            return
        name = self.workspace.load_template(self.category_id, tid).name
        if not dialogs.confirm(self, "Видалити шаблон",
                               f"Видалити шаблон «{name}» разом з його таблицями?\n\n"
                               "Його буде переміщено в папку trash робочої папки."):
            return
        self.workspace.delete_template(self.category_id, tid)
        self.refresh()

    # --- Таблиці даних ----------------------------------------------------

    def refresh_tables(self) -> None:
        self.tables_list.clear()
        tid = self.selected_id()
        has_template = tid is not None
        self.tables_hint.setVisible(not has_template)
        for button in (self.data_button, self.add_table_button, self.open_folder_button, self.preview_button):
            button.setEnabled(has_template)
        self.data_summary.setText("")
        if has_template:
            for path in self.workspace.list_tables(self.category_id, tid):
                stamp = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
                item = QListWidgetItem(f"{path.name}   ({stamp})")
                item.setData(Qt.ItemDataRole.UserRole, path.name)
                self.tables_list.addItem(item)
            self.data_summary.setText(self._data_summary(tid))
        self._update_table_buttons()

    def _data_summary(self, template_id: str) -> str:
        try:
            template = self.workspace.load_template(self.category_id, template_id)
            tables = self.workspace.tables_dir(self.category_id, template_id)
            dataset = load_dataset(tables)
        except StorageError as e:
            return str(e)
        if not dataset.rows:
            return "Даних ще немає. Натисніть «Дані товарів…» або «Імпорт таблиці…»."
        issues = validate(dataset, build_schema(template), images_dir(tables))
        errors = sum(1 for i in issues if i.level == "error")
        text = f"Товарів: {len(dataset.rows)}"
        return text + (f" · помилок: {errors}" if errors else " · без помилок")

    def _update_table_buttons(self) -> None:
        selected = bool(self.tables_list.selectedItems())
        self.delete_table_button.setEnabled(selected)
        self.reimport_button.setEnabled(selected)

    def export_jpeg(self) -> None:
        if self.category_id is not None:
            selected = [self.selected_id()] if self.selected_id() else None
            export_dialog.ask_export(self, self.workspace, self.category_id, selected)

    def _emit_preview(self) -> None:
        tid = self.selected_id()
        if tid is not None:
            self.open_preview.emit(self.category_id, tid)

    def _emit_open_data(self, path: str) -> None:
        tid = self.selected_id()
        if tid is not None:
            self.open_data.emit(self.category_id, tid, path)

    def add_tables(self) -> None:
        if self.selected_id() is None:
            return
        path = dialogs.open_file(self, "Імпорт таблиці", TABLE_FILTER)
        if path is not None:
            self._emit_open_data(str(path))

    def reimport_selected(self) -> None:
        tid = self.selected_id()
        items = self.tables_list.selectedItems()
        if tid is not None and items:
            filename = items[0].data(Qt.ItemDataRole.UserRole)
            self._emit_open_data(str(self.workspace.tables_dir(self.category_id, tid) / filename))

    def delete_selected_table(self) -> None:
        tid = self.selected_id()
        items = self.tables_list.selectedItems()
        if tid is None or not items:
            return
        filename = items[0].data(Qt.ItemDataRole.UserRole)
        if dialogs.confirm(self, "Видалити таблицю", f"Видалити таблицю «{filename}»?"):
            self.workspace.delete_table(self.category_id, tid, filename)
            self.refresh_tables()

    def open_tables_folder(self) -> None:
        tid = self.selected_id()
        if tid is not None:
            os.startfile(self.workspace.tables_dir(self.category_id, tid))
