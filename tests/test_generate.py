"""Етап 7: збирання карток, ручні правки товару, перенесення правок у шаблон."""
import io

import pytest
from PIL import Image

from cardgen.data.dataset import DataSet, images_dir, save_dataset
from cardgen.data.fields import KEY_COLUMN
from cardgen.generate import (
    apply_data,
    apply_overrides,
    compose,
    diff,
    load_overrides,
    split_for_template,
)
from cardgen.model import FieldBinding, PhotoElement, ShapeElement, TableElement, Template, TextElement, TextStyle
from cardgen.model import ops, table_ops
from cardgen.products import Products

pytestmark = pytest.mark.usefixtures("qapp")


def make_template() -> Template:
    table = TableElement.create(2, 2, id="tbl", x=40, y=300, width=520, height=120)
    table.cells[0][0].text = "Переріз"
    table.cells[0][1].binding = FieldBinding(enabled=True, column="Переріз", suffix=" AWG")
    table.cells[1][0].text = "Довжина"
    table.cells[1][1].binding = FieldBinding(enabled=True, column="Довжина", prefix="≈ ", suffix=" м")
    return Template(width=600, height=600, elements=[
        ShapeElement(id="bg", x=0, y=0, width=600, height=80),
        TextElement(id="title", x=20, y=100, width=300, height=60, text="приклад",
                    style=TextStyle(font_family="Arial", font_size=48), min_font_size=24,
                    binding=FieldBinding(enabled=True, column="Назва")),
        TextElement(id="static", x=20, y=200, width=300, height=40, text="Гарантія 12 міс"),
        PhotoElement(id="photo", x=350, y=100, width=200, height=180, placeholder="library:icons/x.png"),
        table,
    ])


ROW = {KEY_COLUMN: "A1", "Назва": "Кабель силіконовий", "Фото": "A1.png", "Переріз": "18", "Довжина": ""}
DATA = DataSet(columns=list(ROW), rows=[ROW])


def by_id(template, element_id):
    return ops.find(template, element_id)


# --- Підстановка даних ----------------------------------------------------------------

def test_apply_data():
    card = apply_data(make_template(), DATA, ROW)
    assert by_id(card, "title").text == "Кабель силіконовий"
    assert by_id(card, "static").text == "Гарантія 12 міс"
    assert by_id(card, "photo").placeholder == "data:A1.png"
    table = by_id(card, "tbl")
    assert table.cells[0][1].text == "18 AWG"
    assert table.cells[1][1].text == ""  # порожнє значення — без «≈  м»
    assert not by_id(card, "title").binding.enabled


def test_apply_data_does_not_touch_template():
    template = make_template()
    apply_data(template, DATA, ROW)
    assert by_id(template, "title").text == "приклад" and by_id(template, "title").binding.enabled


def test_empty_photo_value():
    row = dict(ROW, Фото="")
    assert by_id(apply_data(make_template(), DATA, row), "photo").placeholder == ""


# --- Різниця та правки ------------------------------------------------------------------

def test_diff_and_apply_roundtrip():
    base = apply_data(make_template(), DATA, ROW)
    edited = apply_data(make_template(), DATA, ROW)
    by_id(edited, "title").x = 55
    by_id(edited, "title").style.font_size = 40
    by_id(edited, "tbl").cells[0][1].text = "18 AWG (0,82 мм²)"
    by_id(edited, "tbl").col_widths = [1.0, 2.0]
    changes = diff(base, edited)
    assert changes == {
        "title": {"x": 55, "style.font_size": 40},
        "tbl": {"col_widths": [1.0, 2.0], "cells.0.1.text": "18 AWG (0,82 мм²)"},
    }
    assert apply_overrides(base, changes).elements == edited.elements


def test_overrides_skip_missing_elements_and_stale_lists():
    template = make_template()
    overrides = {"нема": {"x": 1}, "title": {"нема.поля": 5, "y": 7}, "tbl": {"col_widths": [1, 2, 3]}}
    result = apply_overrides(template, overrides)
    assert by_id(result, "title").y == 7
    assert by_id(result, "tbl").col_widths == [1.0, 1.0]  # 3 значення на 2 стовпці — пропущено


def test_override_survives_template_change():
    template = make_template()
    overrides = {"title": {"style.font_size": 40}}
    by_id(template, "title").x = 99  # шаблон змінили після правки товару
    by_id(template, "static").text = "Гарантія 24 міс"
    card = compose(template, DATA, ROW, overrides)
    assert by_id(card, "title").style.font_size == 40  # правка товару
    assert by_id(card, "title").x == 99  # зміна шаблону
    assert by_id(card, "static").text == "Гарантія 24 міс"


def test_split_for_template_keeps_data_fields():
    template = make_template()
    changes = {"title": {"text": "інша назва", "x": 10},
               "tbl": {"cells.0.1.text": "20 AWG", "cells.0.0.text": "Перетин", "border.width": 3}}
    to_template, keep = split_for_template(template, changes)
    assert to_template == {"title": {"x": 10}, "tbl": {"cells.0.0.text": "Перетин", "border.width": 3}}
    assert keep == {"title": {"text": "інша назва"}, "tbl": {"cells.0.1.text": "20 AWG"}}


# --- Товари шаблону (з диском) ---------------------------------------------------------------

def png(path, color):
    Image.new("RGB", (40, 30), color).save(path)


@pytest.fixture
def products(workspace):
    c = workspace.create_category("Кабель AWG")
    t = make_template()
    t.name = "Обкладинка"
    workspace.save_template(c.id, t)
    tables = workspace.tables_dir(c.id, t.id)
    rows = []
    for i in range(3):
        png(images_dir(tables) / f"A{i}.png", (50 * i, 0, 0))
        rows.append({KEY_COLUMN: f"A{i}", "Назва": f"Кабель {i}", "Фото": f"A{i}.png", "Переріз": str(18 + i),
                     "Довжина": "1"})
    rows[2]["Назва"] = "Дуже довга назва кабелю, яка точно не влізе в маленький заголовок " * 3
    save_dataset(tables, DataSet(columns=list(rows[0]), rows=rows))
    return Products(workspace, c.id, t.id)


def test_render_card_with_photo_and_shrink(products):
    rendered = products.render(0)
    assert rendered.image.size().toTuple() == (600, 600)
    assert rendered.image.pixelColor(450, 190).red() == 0  # фото товару A0 (чорне) на місці
    assert products.render(1).image.pixelColor(450, 190).red() == 50
    assert "title" in products.render(2).overflow  # дуже довга назва не вміщується навіть зменшеною
    assert "title" not in rendered.overflow


def test_save_for_product_only_affects_that_product(products, workspace):
    edited = products.card(0)
    by_id(edited, "title").style.font_size = 30
    by_id(edited, "title").text = "Кабель 0 (акція)"
    products.save_for_product(0, edited)
    assert load_overrides(products.tables) == {"A0": {"title": {"style.font_size": 30, "text": "Кабель 0 (акція)"}}}
    assert by_id(products.card(0), "title").style.font_size == 30
    assert by_id(products.card(1), "title").style.font_size == 48
    saved_template = workspace.load_template(products.category_id, products.template_id)
    assert by_id(saved_template, "title").style.font_size == 48  # шаблон не змінено


def test_save_for_template(products, workspace):
    # спершу в товару A0 є власна правка розміру шрифту
    edited = products.card(0)
    by_id(edited, "title").style.font_size = 30
    products.save_for_product(0, edited)
    # тепер рухаємо заголовок і змінюємо текст із даних, «зберегти для шаблону»
    edited = products.card(0)
    by_id(edited, "title").y = 140
    by_id(edited, "title").text = "Інший текст"
    by_id(edited, "static").text = "Гарантія 24 міс"
    keep = products.save_for_template(0, edited)

    template = workspace.load_template(products.category_id, products.template_id)
    assert by_id(template, "title").y == 140
    assert by_id(template, "static").text == "Гарантія 24 міс"
    assert by_id(template, "title").text == "приклад"  # дані в шаблон не потрапили
    assert by_id(template, "title").style.font_size == 48  # стара правка товару — не в шаблон
    assert keep == {"title": {"style.font_size": 30, "text": "Інший текст"}}
    assert by_id(products.card(1), "title").y == 140  # інші товари отримали зміну
    assert by_id(products.card(1), "title").text == "Кабель 1"


def test_reset_and_overrides_survive_data_reload(products):
    edited = products.card(1)
    by_id(edited, "tbl").cells[0][0].text = "Перетин"
    products.save_for_product(1, edited)
    # таблицю перезавантажили: рядки в іншому порядку, нові значення
    rows = list(reversed(products.dataset.rows))
    rows[1]["Переріз"] = "99"
    save_dataset(products.tables, DataSet(columns=products.dataset.columns, rows=rows))
    products.reload()
    index = next(i for i in range(len(products)) if products.article(i) == "A1")
    card = products.card(index)
    assert by_id(card, "tbl").cells[0][0].text == "Перетин"
    assert by_id(card, "tbl").cells[0][1].text == "99 AWG"
    assert products.has_override(index)
    products.reset(index)
    assert not products.has_override(index)
    assert load_overrides(products.tables) == {}


def test_table_structure_change_after_override(products, workspace):
    edited = products.card(0)
    by_id(edited, "tbl").col_widths = [1.0, 3.0]
    products.save_for_product(0, edited)
    template = products.template
    table_ops.insert_col(by_id(template, "tbl"), 2)
    workspace.save_template(products.category_id, template)
    products.reload()
    card = products.card(0)
    assert by_id(card, "tbl").cols == 3
    table_ops.check(by_id(card, "tbl"))  # застаріла правка ширин не зламала таблицю
