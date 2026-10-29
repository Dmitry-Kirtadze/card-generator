"""Етап 7, інтерфейс: стрічка карток, правки товару, «зберегти для шаблону»."""
import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDoubleSpinBox

from cardgen.data.dataset import DataSet, images_dir, save_dataset
from cardgen.data.fields import KEY_COLUMN
from cardgen.generate import load_overrides
from cardgen.model import FieldBinding, PhotoElement, Template, TextElement, TextStyle
from cardgen.model import ops
from cardgen.ui.main_window import MainWindow
from test_app import FakeDialogs


@pytest.fixture
def fake(monkeypatch):
    return FakeDialogs(monkeypatch)


@pytest.fixture
def setup(qtbot, workspace):
    c = workspace.create_category("Кабель AWG")
    t = Template(name="Обкладинка", width=600, height=600, elements=[
        TextElement(id="title", x=20, y=20, width=400, height=80, min_font_size=30,
                    style=TextStyle(font_family="Arial", font_size=48),
                    binding=FieldBinding(enabled=True, column="Назва", required=True)),
        TextElement(id="static", x=20, y=520, width=400, height=50, text="Гарантія"),
        PhotoElement(id="photo", x=300, y=150, width=250, height=250),
    ])
    workspace.save_template(c.id, t)
    tables = workspace.tables_dir(c.id, t.id)
    rows = []
    for i in range(5):
        Image.new("RGB", (40, 40), (40 * i, 0, 0)).save(images_dir(tables) / f"p{i}.png")
        rows.append({KEY_COLUMN: f"AWG-{10 + i}", "Назва": f"Кабель {10 + i} AWG", "Фото": f"p{i}.png"})
    rows[3]["Назва"] = "Надзвичайно довга назва кабелю, яка ніяк не вміститься в заголовок " * 2
    rows[4]["Назва"] = ""  # обов'язкове поле порожнє
    save_dataset(tables, DataSet(columns=list(rows[0]), rows=rows))
    window = MainWindow(workspace)
    qtbot.addWidget(window)
    window.resize(1400, 900)
    window.show()
    window.show_category(c.id)
    window.category_page.grid.setCurrentRow(0)
    window.category_page.preview_button.click()
    return window, window.preview_page, workspace, c, t


def element(page, element_id):
    return ops.find(page.editor.template, element_id)


def spin(page, name):
    found = [w for w in page.editor.properties.findChildren(QDoubleSpinBox, name)
             if w.isVisibleTo(page.editor.properties)]
    assert len(found) == 1, name
    return found[0]


def test_strip_shows_all_products_and_problems(setup):
    window, page, *_ = setup
    assert window.stack.currentWidget() is page
    assert page.strip.count() == 5
    texts = [page.strip.item(i).text() for i in range(5)]
    assert texts[0] == "AWG-10"
    assert texts[3].startswith("⚠") and texts[4].startswith("⚠")
    assert "Текст не вміщується" in page.strip.item(3).toolTip()
    assert "Обов'язкове" in page.strip.item(4).toolTip()
    assert "з проблемами: 2" in page.summary.text()
    # відкрито першу картку з даними товару
    assert element(page, "title").text == "Кабель 10 AWG"
    assert element(page, "photo").placeholder == "data:p0.png"
    assert page.problems.text() == ""


def test_switch_products_from_strip_and_buttons(setup):
    _, page, *_ = setup
    page.strip.setCurrentRow(2)
    assert page.current == 2 and element(page, "title").text == "Кабель 12 AWG"
    page.next_button.click()
    assert page.current == 3 and "не вміщується" in page.problems.text()
    page.prev_button.click()
    assert page.current == 2


def test_save_for_product(setup, fake):
    _, page, workspace, c, t = setup
    page.editor.select_ids(["title"])
    spin(page, "font_size").setValue(36)
    assert page.save_product_button.isEnabled()
    page.save_product_button.click()
    assert load_overrides(workspace.tables_dir(c.id, t.id)) == {"AWG-10": {"title": {"style.font_size": 36}}}
    assert page.strip.item(0).text().startswith("✎")
    assert page.reset_button.isEnabled()
    page.go(1)
    assert element(page, "title").style.font_size == 48  # інші товари без змін
    page.go(0)
    assert element(page, "title").style.font_size == 36
    assert ops.find(workspace.load_template(c.id, t.id), "title").style.font_size == 48


def test_unsaved_changes_asked_when_switching(setup, fake):
    _, page, workspace, c, t = setup
    page.editor.select_ids(["static"])
    spin(page, "y").setValue(500)
    fake.confirm_answer = False  # «не зберігати»
    page.go(1)
    assert fake.confirms and "Зберегти правки" in fake.confirms[-1]
    assert load_overrides(workspace.tables_dir(c.id, t.id)) == {}
    page.go(0)
    assert element(page, "static").y == 520


def test_save_for_template(setup, fake):
    window, page, workspace, c, t = setup
    page.editor.select_ids(["static"])
    spin(page, "y").setValue(480)
    page.editor.select_ids(["title"])
    page.save_template_button.click()
    template = workspace.load_template(c.id, t.id)
    assert ops.find(template, "static").y == 480
    assert ops.find(template, "title").text == "Текст"  # дані «Кабель 10 AWG» в шаблон не потрапили
    page.go(2)
    assert element(page, "static").y == 480  # змінилось для всіх


def test_reset_product(setup, fake):
    _, page, workspace, c, t = setup
    page.editor.select_ids(["title"])
    spin(page, "x").setValue(60)
    page.save_for_product()
    page.reset_button.click()
    assert load_overrides(workspace.tables_dir(c.id, t.id)) == {}
    assert element(page, "title").x == 20
    assert not page.strip.item(0).text().startswith("✎")


def test_preview_blocks_structure_changes(setup):
    _, page, *_ = setup
    count = len(page.editor.template.elements)
    page.editor.select_ids(["static"])
    page.editor.delete_selected()
    page.editor.duplicate_selected()
    page.editor.paste()
    assert len(page.editor.template.elements) == count
    assert not page.editor.add_buttons["text"].isVisible()


def test_back_returns_and_template_reloaded_in_editor(setup, fake):
    window, page, workspace, c, t = setup
    page.leave()
    assert window.stack.currentWidget() is window.category_page
    window.open_editor(c.id, t.id)
    window.editor_page._open_preview()
    assert window.stack.currentWidget() is window.preview_page
    page.editor.select_ids(["static"])
    spin(page, "x").setValue(77)
    page.save_template_button.click()
    page.leave()
    assert window.stack.currentWidget() is window.editor_page
    assert ops.find(window.editor_page.template, "static").x == 77


def test_preview_card_has_no_photo_placeholder_for_missing_photo(setup):
    _, page, workspace, c, t = setup
    products = page.products
    products.dataset.rows[0]["Фото"] = ""
    image = products.render(0).image
    # без фото на картці товару немає сірої заглушки «Фото»
    assert image.pixelColor(425, 275).name() == "#ffffff"
