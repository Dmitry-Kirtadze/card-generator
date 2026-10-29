"""Екран «Дані товарів»: таблиця для заповнення, імпорт/експорт Excel, фото, перевірка."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..data.dataset import DataSet, images_dir, load_dataset, save_dataset
from ..data.fields import KEY_COLUMN, TYPE_TITLES, Schema, build_schema
from ..data.photos import PhotoError, cleanup_unused, store_image
from ..data.table_io import TableImportError, export_xlsx, import_table
from ..data.validate import Issue, validate
from ..storage import StorageError, Workspace
from . import dialogs

SAVE_DELAY_MS = 400
THUMB = 48
ERROR_BG = QColor("#FDE2E2")
WARNING_BG = QColor("#FFF4D6")
ISSUE_FG = QColor("#111111")
# кольори тексту, читабельні і на світлій, і на темній темі Windows
ERROR_TEXT = "#F04438"
OK_TEXT = "#12B76A"
EXTRA_FG = QColor("#9CA3AF")
IMAGE_FILTER = "Зображення (*.png *.jpg *.jpeg *.webp)"
TABLE_FILTER = "Таблиці (*.xlsx *.csv)"


class ListDelegate(QStyledItemDelegate):
    """Випадний список для стовпців типу «Вибір зі списку»."""

    def __init__(self, page: DataPage):
        super().__init__(page)
        self.page = page

    def createEditor(self, parent, option, index):
        spec = self.page.spec_at(index.column())
        if spec is None or spec.field_type != "list" or not spec.options:
            return super().createEditor(parent, option, index)
        box = QComboBox(parent)
        box.setEditable(True)
        box.addItems([""] + spec.options)
        return box

    def setEditorData(self, editor, index):
        if isinstance(editor, QComboBox):
            editor.setEditText(index.data() or "")
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentText())
        else:
            super().setModelData(editor, model, index)


class DataTable(QTableWidget):
    """Таблиця, у клітинки фото якої можна перетягнути файл."""

    fileDropped = Signal(int, int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        index = self.indexAt(event.position().toPoint())
        if urls and index.isValid():
            self.fileDropped.emit(index.row(), index.column(), urls[0].toLocalFile())
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class DataPage(QWidget):
    back = Signal()
    open_preview = Signal(str, str)  # id категорії, id шаблону

    def __init__(self, workspace: Workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.category_id: str | None = None
        self.template_id: str | None = None
        self.schema = Schema([])
        self.dataset = DataSet()
        self.columns: list[str] = []
        self.issues: list[Issue] = []
        self._filling = False

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DELAY_MS)
        self._save_timer.timeout.connect(self.save_now)

        back = QPushButton("← Назад")
        back.setObjectName("btn_back")
        back.clicked.connect(self.leave)
        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        self.source = QLabel()
        self.source.setStyleSheet("color: #6B7280;")
        top = QHBoxLayout()
        top.addWidget(back)
        top.addWidget(self.title)
        top.addWidget(self.source)
        top.addStretch()

        tools = QHBoxLayout()
        self.buttons: dict[str, QPushButton] = {}
        for key, text, handler in [
            ("import", "Імпорт з Excel / CSV…", self.import_dialog),
            ("export", "Експорт у Excel…", self.export_dialog),
            ("add", "+ Товар", self.add_row),
            ("delete", "Видалити товар", self.delete_rows),
            ("photo", "Фото для клітинки…", self.choose_photo),
            ("folder", "Папка фото", self.open_images_folder),
            ("preview", "Перегляд карток", self._open_preview),
        ]:
            button = QPushButton(text)
            button.setObjectName(f"btn_{key}")
            button.clicked.connect(handler)
            tools.addWidget(button)
            self.buttons[key] = button
        tools.addStretch()
        self.summary = QLabel()
        self.summary.setObjectName("summary")
        tools.addWidget(self.summary)

        self.table = DataTable()
        self.table.setObjectName("dataTable")
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setIconSize(QSize(THUMB, THUMB))
        self.table.verticalHeader().setDefaultSectionSize(THUMB + 8)
        self.table.setItemDelegate(ListDelegate(self))
        self.table.itemChanged.connect(self._item_changed)
        self.table.cellDoubleClicked.connect(self._double_clicked)
        self.table.fileDropped.connect(self._file_dropped)

        self.issue_list = QListWidget()
        self.issue_list.setObjectName("issueList")
        self.issue_list.itemActivated.connect(self._goto_issue)
        self.issue_list.itemClicked.connect(self._goto_issue)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.issue_list)
        splitter.setSizes([600, 160])

        hint = QLabel("Фото: перетягніть файл на клітинку, двічі клацніть по ній або вставте картинку прямо "
                      "в Excel. Зміни зберігаються автоматично.")
        hint.setStyleSheet("color: #6B7280;")
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(tools)
        layout.addWidget(hint)
        layout.addWidget(splitter, 1)

    # --- Відкриття ---------------------------------------------------------------

    def open(self, category_id: str, template_id: str) -> None:
        self.category_id, self.template_id = category_id, template_id
        template = self.workspace.load_template(category_id, template_id)
        self.title.setText(f"Дані: {template.name}")
        self.schema = build_schema(template)
        self.dataset = load_dataset(self.tables_dir())
        self.refresh()

    def tables_dir(self) -> Path:
        return self.workspace.tables_dir(self.category_id, self.template_id)

    def images(self) -> Path:
        return images_dir(self.tables_dir())

    def spec_at(self, col: int):
        return self.schema.get(self.columns[col]) if 0 <= col < len(self.columns) else None

    # --- Відображення -------------------------------------------------------------

    def refresh(self) -> None:
        extra = [c for c in self.dataset.columns if self.schema.get(c) is None]
        self.columns = self.schema.columns + extra
        self._filling = True
        self.table.clear()
        self.table.setColumnCount(len(self.columns))
        self.table.setRowCount(len(self.dataset.rows))
        for c, name in enumerate(self.columns):
            spec = self.schema.get(name)
            header = QTableWidgetItem(name + (" *" if spec and spec.required else ""))
            if spec is None:
                header.setForeground(EXTRA_FG)
                header.setToolTip("Не використовується в шаблоні")
            else:
                header.setToolTip(f"{TYPE_TITLES.get(spec.field_type)} · використано: {', '.join(spec.used_in[:5])}")
            self.table.setHorizontalHeaderItem(c, header)
        for r, row in enumerate(self.dataset.rows):
            for c, name in enumerate(self.columns):
                self.table.setItem(r, c, self._make_item(name, self.dataset.value(row, name)))
        self.table.resizeColumnsToContents()
        for c in range(len(self.columns)):
            self.table.setColumnWidth(c, max(120, min(self.table.columnWidth(c), 320)))
        self._filling = False
        self.source.setText(f"з файлу {self.dataset.source}" if self.dataset.source else "")
        self.revalidate()

    def _make_item(self, column: str, value: str) -> QTableWidgetItem:
        item = QTableWidgetItem(value)
        spec = self.schema.get(column)
        if spec is not None and spec.is_image and value:
            image = QImage(str(self.images() / value))
            if not image.isNull():
                item.setIcon(QIcon(QPixmap.fromImage(image.scaled(
                    THUMB, THUMB, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))))
        if spec is None:
            item.setForeground(EXTRA_FG)
        return item

    def revalidate(self) -> None:
        self.issues = validate(self.dataset, self.schema, self.images())
        self._filling = True
        for r in range(self.table.rowCount()):
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item is not None:
                    item.setBackground(QBrush())
                    extra = self.schema.get(self.columns[c]) is None
                    item.setForeground(EXTRA_FG if extra else QBrush())
                    item.setToolTip("")
        for issue in self.issues:
            if issue.row < 0 or issue.column not in self.columns:
                continue
            item = self.table.item(issue.row, self.columns.index(issue.column))
            if item is not None:
                item.setBackground(ERROR_BG if issue.level == "error" else WARNING_BG)
                item.setForeground(ISSUE_FG)  # світла підсвітка — темний текст і в темній темі
                item.setToolTip(issue.message)
        self._filling = False

        self.issue_list.clear()
        for issue in self.issues:
            where = "Шаблон" if issue.row < 0 else f"Рядок {issue.row + 1}"
            if issue.column:
                where += f" · {issue.column}"
            item = QListWidgetItem(f"{'⛔' if issue.level == 'error' else '⚠'}  {where}: {issue.message}")
            item.setData(Qt.ItemDataRole.UserRole, (issue.row, issue.column))
            self.issue_list.addItem(item)
        errors = sum(1 for i in self.issues if i.level == "error")
        warnings = len(self.issues) - errors
        text = f"Товарів: {len(self.dataset.rows)}"
        text += f" · помилок: {errors}" if errors else " · помилок немає"
        if warnings:
            text += f" · попереджень: {warnings}"
        self.summary.setText(text)
        self.summary.setStyleSheet(f"color: {ERROR_TEXT}; font-weight: 600;" if errors else f"color: {OK_TEXT};")
        self.issue_list.setVisible(bool(self.issues))

    def _goto_issue(self, item: QListWidgetItem) -> None:
        row, column = item.data(Qt.ItemDataRole.UserRole)
        if row >= 0 and column in self.columns:
            self.table.setCurrentCell(row, self.columns.index(column))
            self.table.setFocus()

    # --- Редагування ----------------------------------------------------------------

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if self._filling:
            return
        column = self.columns[item.column()]
        self.dataset.rows[item.row()][column] = item.text().strip()
        self._changed()

    def _changed(self) -> None:
        self.dataset.ensure_columns(self.columns)
        self._save_timer.start()
        self.revalidate()

    def add_row(self) -> None:
        self.dataset.rows.append({c: "" for c in self.columns})
        self.refresh()
        self._save_timer.start()
        self.table.setCurrentCell(len(self.dataset.rows) - 1, 0)
        self.table.editItem(self.table.currentItem())

    def delete_rows(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        if not dialogs.confirm(self, "Видалити товари", f"Видалити вибрані товари ({len(rows)})?"):
            return
        for r in rows:
            del self.dataset.rows[r]
        self.refresh()
        self._save_timer.start()

    def set_photo(self, row: int, col: int, source: Path) -> bool:
        spec = self.spec_at(col)
        if spec is None or not spec.is_image:
            dialogs.error(self, "Фото можна додати лише в стовпець фото")
            return False
        data_row = self.dataset.rows[row]
        article = self.dataset.key_of(data_row) or f"рядок-{row + 1}"
        try:
            name = store_image(Path(source).read_bytes(), self.images(), article, spec.column)
        except (PhotoError, OSError) as e:
            dialogs.error(self, str(e))
            return False
        data_row[spec.column] = name
        self._filling = True
        self.table.setItem(row, col, self._make_item(spec.column, name))
        self._filling = False
        self._changed()
        return True

    def choose_photo(self) -> None:
        r, c = self.table.currentRow(), self.table.currentColumn()
        if r < 0 or c < 0:
            dialogs.info(self, "Фото", "Спершу виберіть клітинку у стовпці фото.")
            return
        self._double_clicked(r, c)

    def _double_clicked(self, row: int, col: int) -> None:
        spec = self.spec_at(col)
        if spec is None or not spec.is_image:
            return  # звичайна клітинка — Qt сам відкриє редагування
        path = dialogs.open_file(self, "Фото товару", IMAGE_FILTER)
        if path is not None:
            self.set_photo(row, col, path)

    def _file_dropped(self, row: int, col: int, path: str) -> None:
        if path:
            self.set_photo(row, col, Path(path))

    def save_now(self) -> bool:
        self._save_timer.stop()
        if self.category_id is None:
            return True
        try:
            save_dataset(self.tables_dir(), self.dataset)
            cleanup_unused(self.images(), self.used_images())
        except (StorageError, OSError) as e:
            dialogs.error(self, f"Не вдалося зберегти дані: {e}")
            return False
        return True

    def used_images(self) -> set[str]:
        """Імена фото, на які посилаються товари (решту з папки можна прибрати)."""
        image_columns = [spec.column for spec in self.schema.fields if spec.is_image]
        return {self.dataset.value(row, column) for row in self.dataset.rows for column in image_columns} - {""}

    def leave(self) -> None:
        if self.save_now():
            self.back.emit()

    def _open_preview(self) -> None:
        if self.save_now():
            self.open_preview.emit(self.category_id, self.template_id)

    def open_images_folder(self) -> None:
        os.startfile(self.images())

    # --- Імпорт / експорт ----------------------------------------------------------

    def export_dialog(self) -> None:
        template = self.workspace.load_template(self.category_id, self.template_id)
        target = dialogs.save_file(self, "Експорт у Excel", f"{template.name}.xlsx", "Excel (*.xlsx)")
        if target is None:
            return
        if target.suffix.lower() != ".xlsx":
            target = target.with_suffix(".xlsx")
        try:
            export_xlsx(self.schema, self.dataset, target)
        except OSError as e:
            dialogs.error(self, f"Не вдалося зберегти: {e}")
            return
        dialogs.info(self, "Експорт", f"Таблицю збережено:\n{target}\n\n"
                                      "Заповніть її та імпортуйте назад кнопкою «Імпорт з Excel / CSV».")

    def import_dialog(self) -> None:
        path = dialogs.open_file(self, "Імпорт таблиці", TABLE_FILTER)
        if path is not None:
            self.import_file(path)

    def import_file(self, path: Path, photos_folder: Path | None = None) -> bool:
        if self.dataset.rows and photos_folder is None and not dialogs.confirm(
                self, "Імпорт", f"Замінити поточні дані ({len(self.dataset.rows)} товарів) "
                                f"даними з файлу «{path.name}»?\n\nФото з таблиці оновляться."):
            return False
        try:
            result = import_table(path, self.schema, self.images(), photos_folder=photos_folder,
                                  previous=self.dataset)
        except (TableImportError, OSError) as e:
            dialogs.error(self, f"Не вдалося імпортувати: {e}")
            return False
        missing = [w for w in result.warnings if "не знайдено" in w]
        if missing and photos_folder is None and dialogs.confirm(
                self, "Фото не знайдено",
                f"Не знайдено фото: {len(missing)}. Вказати папку, де лежать фото?"):
            folder = dialogs.open_dir(self, "Папка з фото", str(path.parent))
            if folder is not None:
                return self.import_file(path, folder)
        self.dataset = result.dataset
        if Path(path).resolve().parent != self.tables_dir().resolve():  # не повторне завантаження
            try:
                self.workspace.add_table(self.category_id, self.template_id, path)  # історія
            except (StorageError, OSError):
                pass
        self.save_now()
        self.refresh()
        report = f"Імпортовано товарів: {len(self.dataset.rows)}, фото: {result.photos}."
        if result.warnings:
            report += "\n\nЗауваження:\n• " + "\n• ".join(result.warnings[:15])
            if len(result.warnings) > 15:
                report += f"\n… і ще {len(result.warnings) - 15}"
        dialogs.info(self, "Імпорт", report)
        return True
