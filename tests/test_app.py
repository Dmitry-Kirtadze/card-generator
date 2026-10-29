"""Тести інтерфейсу. Діалоги підмінено: відповіді задаються заздалегідь."""
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase

from cardgen import APP_NAME
from cardgen.ui import category_page as category_page_module
from cardgen.ui import dialogs
from cardgen.ui.library_dialog import LibraryDialog
from cardgen.ui.main_window import MainWindow
from cardgen.ui.template_dialog import TemplateValues
from cardgen.ui.thumbnails import render_thumbnail

SYSTEM_FONT = Path(r"C:\Windows\Fonts\arial.ttf")


class FakeDialogs:
    """Записує, які діалоги показано, і повертає підготовлені відповіді."""

    def __init__(self, monkeypatch):
        self.texts: list[str | None] = []
        self.confirm_answer = True
        self.files: list[Path] = []
        self.save_path: Path | None = None
        self.open_path: Path | None = None
        self.dir_path: Path | None = None
        self.errors: list[str] = []
        self.infos: list[str] = []
        self.confirms: list[str] = []
        monkeypatch.setattr(dialogs, "ask_text", lambda *a, **k: self.texts.pop(0))
        self.choices: list[str | None] = []
        self.offered: list[list[str]] = []
        monkeypatch.setattr(dialogs, "ask_choice", self._choice)
        monkeypatch.setattr(dialogs, "confirm", self._confirm)
        monkeypatch.setattr(dialogs, "open_dir", lambda *a, **k: self.dir_path)
        monkeypatch.setattr(dialogs, "open_files", lambda *a, **k: self.files)
        monkeypatch.setattr(dialogs, "open_file", lambda *a, **k: self.open_path)
        monkeypatch.setattr(dialogs, "save_file", lambda *a, **k: self.save_path)
        monkeypatch.setattr(dialogs, "error", lambda _p, text: self.errors.append(text))
        monkeypatch.setattr(dialogs, "info", lambda _p, _t, text: self.infos.append(text))

    def _choice(self, _parent, _title, _label, options):
        self.offered.append(list(options))
        return self.choices.pop(0)

    def _confirm(self, _parent, _title, text) -> bool:
        self.confirms.append(text)
        return self.confirm_answer


@pytest.fixture
def fake(monkeypatch):
    return FakeDialogs(monkeypatch)


@pytest.fixture
def window(qtbot, workspace):
    w = MainWindow(workspace)
    qtbot.addWidget(w)
    w.show()
    return w


def names(grid) -> list[str]:
    return [grid.item(i).text().split("\n")[0] for i in range(grid.count())]


def select(grid, index: int) -> None:
    grid.setCurrentRow(index)


def test_main_window_opens(window):
    assert APP_NAME in window.windowTitle()
    assert window.stack.currentWidget() is window.categories_page
    assert window.categories_page.empty_hint.isVisibleTo(window)


def test_category_crud(window, fake, workspace):
    page = window.categories_page
    assert not page.actions.buttons["delete"].isEnabled()

    fake.texts = ["Кабель AWG"]
    page.create_category()
    assert names(page.grid) == ["Кабель AWG"]
    assert page.actions.buttons["delete"].isEnabled()  # нова категорія виділена

    fake.texts = ["Кабель AWG"]  # така вже є
    page.create_category()
    assert fake.errors and "вже існує" in fake.errors[-1]

    fake.texts = ["Кабель силіконовий AWG"]
    page.rename_selected()
    assert names(page.grid) == ["Кабель силіконовий AWG"]

    page.duplicate_selected()
    assert names(page.grid) == ["Кабель силіконовий AWG", "Кабель силіконовий AWG (копія)"]

    fake.confirm_answer = False
    page.delete_selected()
    assert page.grid.count() == 2
    fake.confirm_answer = True
    page.delete_selected()
    assert names(page.grid) == ["Кабель силіконовий AWG"]
    assert len(workspace.list_categories()) == 1


def test_cancel_create_does_nothing(window, fake):
    fake.texts = [None]
    window.categories_page.create_category()
    assert window.categories_page.grid.count() == 0


def test_open_category_and_manage_templates(window, fake, workspace, monkeypatch):
    category = workspace.create_category("Кабель AWG")
    window.categories_page.refresh()
    select(window.categories_page.grid, 0)
    window.categories_page.actions.buttons["open"].click()
    page = window.category_page
    assert window.stack.currentWidget() is page
    assert page.title.text() == "Кабель AWG"

    answers = [TemplateValues("Обкладинка", 1000, 1000), TemplateValues("Характеристики", 1200, 1200)]
    monkeypatch.setattr(category_page_module, "ask_template", lambda *a, **k: answers.pop(0))
    page.create_template()
    page.create_template()
    assert names(page.grid) == ["Обкладинка", "Характеристики"]
    assert page.grid.item(1).text().endswith("1200 × 1200")
    numbers = {t.name: t.export.number for t in workspace.list_templates(category.id)}
    assert numbers == {"Обкладинка": 1, "Характеристики": 2}  # номер картинки для імені файлу

    select(page.grid, 0)
    answers.append(TemplateValues("Головна", 1500, 1500, number=3, filename_mask="{Назва}-{№}",
                                  jpeg_quality=85))
    page.settings_selected()
    template = workspace.list_templates(category.id)[0]
    assert (template.name, template.width) == ("Головна", 1500)
    assert (template.export.number, template.export.filename_mask, template.export.jpeg_quality) == \
        (3, "{Назва}-{№}", 85)

    select(page.grid, 0)
    page.duplicate_selected()
    assert names(page.grid) == ["Головна", "Головна (копія)", "Характеристики"]

    select(page.grid, 1)
    page.delete_selected()
    assert names(page.grid) == ["Головна", "Характеристики"]

    page.back.emit()
    assert window.stack.currentWidget() is window.categories_page
    assert window.categories_page.grid.item(0).text().endswith("2 шаблони")


def test_tables_panel(window, fake, workspace, tmp_path):
    category = workspace.create_category("Кабель AWG")
    workspace.create_template(category.id, "Обкладинка")
    window.show_category(category.id)
    page = window.category_page
    assert not page.add_table_button.isEnabled()

    select(page.grid, 0)
    assert page.add_table_button.isEnabled()
    assert "Даних ще немає" in page.data_summary.text()
    xlsx = tmp_path / "кабелі.xlsx"
    xlsx.write_bytes(b"PK")
    workspace.add_table(category.id, workspace.list_templates(category.id)[0].id, xlsx)
    page.refresh_tables()
    assert page.tables_list.count() == 1
    assert page.tables_list.item(0).text().startswith("кабелі.xlsx")

    page.tables_list.setCurrentRow(0)
    page.delete_selected_table()
    assert page.tables_list.count() == 0


def test_edit_opens_editor_and_back(window, fake, workspace):
    category = workspace.create_category("Кабель AWG")
    workspace.create_template(category.id, "Обкладинка")
    window.show_category(category.id)
    select(window.category_page.grid, 0)
    window.category_page.edit_selected()
    assert window.stack.currentWidget() is window.editor_page
    assert window.editor_page.title.text() == "Обкладинка"
    window.editor_page.leave()
    assert window.stack.currentWidget() is window.category_page


def test_export_import_through_ui(window, fake, workspace, tmp_path):
    category = workspace.create_category("Кабель AWG")
    workspace.create_template(category.id, "Обкладинка")
    page = window.categories_page
    page.refresh()
    select(page.grid, 0)

    fake.save_path = tmp_path / "перенос"  # без розширення — додасться
    page.export_selected()
    archive = tmp_path / "перенос.cardgen.zip"
    assert archive.is_file(), fake.errors

    fake.open_path = archive
    page.import_archive()
    assert names(page.grid) == ["Кабель AWG", "Кабель AWG (імпорт)"]
    imported = workspace.list_categories()[1]
    assert [t.name for t in workspace.list_templates(imported.id)] == ["Обкладинка"]


def test_library_icons(qtbot, fake, workspace, tmp_path):
    dialog = LibraryDialog(workspace)
    qtbot.addWidget(dialog)
    icons = dialog.sections["icons"]
    bad = tmp_path / "a.exe"
    bad.write_bytes(b"MZ")
    good = tmp_path / "star.svg"
    good.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>')
    fake.files = [good, bad]
    icons.add_files()
    assert icons.list.count() == 1
    assert fake.errors and "a.exe" in fake.errors[-1]

    icons.list.setCurrentRow(0)
    icons.delete_selected()
    assert icons.list.count() == 0


@pytest.mark.skipif(not SYSTEM_FONT.is_file(), reason="немає системного шрифту")
def test_library_font_available_in_qt(qtbot, fake, workspace):
    dialog = LibraryDialog(workspace)
    qtbot.addWidget(dialog)
    fonts = dialog.sections["fonts"]
    fake.files = [SYSTEM_FONT]
    fonts.add_files()
    assert fonts.list.count() == 1
    assert "Arial" in QFontDatabase.families()
    assert fonts.list.item(0).font().family() == "Arial"


def test_thumbnail_renders_all_element_types(qtbot, workspace, full_template):
    category = workspace.create_category("Кабель")
    pixmap = render_thumbnail(full_template, 180, workspace, category.id)
    assert pixmap.width() == 180 and not pixmap.isNull()
    image = pixmap.toImage()
    # центр не фон-заглушка: щось намальовано
    assert image.pixelColor(90, 90) != Qt.GlobalColor.transparent
