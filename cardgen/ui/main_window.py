from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMainWindow, QStackedWidget

from .. import APP_NAME, __version__
from ..storage import StorageError, Workspace
from . import dialogs
from .categories_page import CategoriesPage
from .category_page import CategoryPage
from .data_page import DataPage
from .preview_page import PreviewPage
from .update_ui import StartupUpdater, UpdateDialog
from ..config import app_dir
from ..updater import Updater
from .editor.page import EditorPage
from .fonts import register_library_fonts
from .library_dialog import LibraryDialog

STYLE = """
QWidget { font-size: 10pt; }
QLabel#pageTitle { font-size: 18pt; font-weight: 600; padding: 4px 0 8px 0; }
QLabel#emptyHint { color: #6B7280; font-size: 11pt; padding: 40px; }
QListWidget { background: palette(base); color: palette(text); border: 1px solid palette(mid);
              border-radius: 6px; }
QPushButton { padding: 6px 12px; }
"""


class MainWindow(QMainWindow):
    def __init__(self, workspace: Workspace):
        super().__init__()
        self.workspace = workspace
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1280, 800)
        self.setStyleSheet(STYLE)
        register_library_fonts(workspace)

        self.categories_page = CategoriesPage(workspace)
        self.category_page = CategoryPage(workspace)
        self.editor_page = EditorPage(workspace)
        self.data_page = DataPage(workspace)
        self.preview_page = PreviewPage(workspace)
        self._data_return = None  # куди повернутися з екрана даних
        self._preview_return = None
        self.stack = QStackedWidget()
        for page in (self.categories_page, self.category_page, self.editor_page, self.data_page,
                     self.preview_page):
            self.stack.addWidget(page)
        self.setCentralWidget(self.stack)

        self.categories_page.open_category.connect(self.show_category)
        self.categories_page.open_library.connect(self.show_library)
        self.categories_page.open_updates.connect(self.show_updates)
        self.updater = Updater(app_dir())
        self.category_page.back.connect(self.show_categories)
        self.category_page.edit_template.connect(self.open_editor)
        self.category_page.open_data.connect(self.open_data)
        self.editor_page.back.connect(self._editor_closed)
        self.editor_page.open_data.connect(lambda c, t: self.open_data(c, t, ""))
        self.data_page.back.connect(self._data_closed)
        self.category_page.open_preview.connect(self.open_preview)
        self.data_page.open_preview.connect(self.open_preview)
        self.editor_page.open_preview.connect(self.open_preview)
        self.preview_page.back.connect(self._preview_closed)

    def show_categories(self) -> None:
        self.categories_page.refresh()
        self.stack.setCurrentWidget(self.categories_page)

    def show_category(self, category_id: str) -> None:
        self.category_page.show_category(category_id)
        self.stack.setCurrentWidget(self.category_page)

    def show_library(self) -> None:
        LibraryDialog(self.workspace, self).exec()
        register_library_fonts(self.workspace)
        self.categories_page.refresh()

    def show_updates(self) -> None:
        ok, reason = self.updater.supported()
        if not ok:
            dialogs.info(self, "Оновлення", f"Автооновлення недоступне: {reason}.\n\n"
                                            "Програма оновлюється з git-репозиторію — див. README.")
            return
        dialog = UpdateDialog(self.updater, self.workspace, self)
        dialog.check()
        dialog.exec()

    def start_update_check(self) -> None:
        """Фонова перевірка оновлень після запуску (викликається з app.run)."""
        self._startup_updater = StartupUpdater(self, self.updater, self.workspace)
        self._startup_updater.start()

    def open_editor(self, category_id: str, template_id: str) -> None:
        register_library_fonts(self.workspace)
        try:
            self.editor_page.open_template(category_id, template_id)
        except StorageError as e:
            dialogs.error(self, str(e))
            return
        self.stack.setCurrentWidget(self.editor_page)

    def open_data(self, category_id: str, template_id: str, import_path: str = "") -> None:
        try:
            self.data_page.open(category_id, template_id)
        except StorageError as e:
            dialogs.error(self, str(e))
            return
        self._data_return = self.stack.currentWidget()
        self.stack.setCurrentWidget(self.data_page)
        if import_path:
            self.data_page.import_file(Path(import_path))

    def open_preview(self, category_id: str, template_id: str) -> None:
        try:
            self.preview_page.open(category_id, template_id)
        except StorageError as e:
            dialogs.error(self, str(e))
            return
        self._preview_return = self.stack.currentWidget()
        self.stack.setCurrentWidget(self.preview_page)

    def _preview_closed(self) -> None:
        """Повернутись туди, звідки відкрили перегляд; шаблон міг змінитися («Зберегти для шаблону»)."""
        target = self._preview_return or self.category_page
        p = self.preview_page.products
        if target is self.editor_page and p is not None:
            self.editor_page.open_template(p.category_id, p.template_id)
        elif target is self.data_page and p is not None:
            self.data_page.open(p.category_id, p.template_id)
        elif target is self.category_page:
            self.category_page.refresh(p.template_id if p else None)
        self.stack.setCurrentWidget(target)

    def _data_closed(self) -> None:
        target = self._data_return or self.category_page
        if target is self.category_page:
            self.category_page.refresh(self.data_page.template_id)
        self.stack.setCurrentWidget(target)

    def _editor_closed(self) -> None:
        template = self.editor_page.template
        self.category_page.refresh(template.id if template else None)
        self.stack.setCurrentWidget(self.category_page)

    def closeEvent(self, event) -> None:
        if self.stack.currentWidget() is self.editor_page and not self.editor_page.save_now():
            event.ignore()
            return
        if self.stack.currentWidget() is self.data_page and not self.data_page.save_now():
            event.ignore()
            return
        if self.stack.currentWidget() is self.preview_page and self.preview_page.editor.dirty:
            if dialogs.confirm(self, "Незбережені правки", "Зберегти правки поточної картки для цього товару?"):
                self.preview_page.save_for_product()
        super().closeEvent(event)
