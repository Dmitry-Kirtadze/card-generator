"""Етап 5: таблиця — операції з рядками/стовпцями, відмальовування, редагування."""
import json

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QPushButton, QSpinBox, QTableWidget

from cardgen.model import Paint, Stroke, TableElement, Template
from cardgen.model import serialization as ser
from cardgen.model import table_ops
from cardgen.model.table_ops import TableError
from cardgen.render import RenderContext, render_template
from cardgen.render.painter import cell_overflow_id
from cardgen.ui.color_button import ColorButton
from cardgen.ui.editor.page import EditorPage
from imaging import assert_matches_golden


def texts(table):
    return [[c.text for c in row] for row in table.cells]


@pytest.fixture
def table():
    t = TableElement.create(3, 2, width=600, height=300)
    for r in range(3):
        for c in range(2):
            t.cells[r][c].text = f"{r}{c}"
    t.cells[1][0].style.bold = True
    t.cells[1][0].binding.enabled = True
    return t


# --- Рядки й стовпці --------------------------------------------------------------

def test_insert_row_keeps_data_and_copies_style(table):
    table_ops.insert_row(table, 1)
    table_ops.check(table)
    assert texts(table) == [["00", "01"], ["", ""], ["10", "11"], ["20", "21"]]
    assert table.cells[1][0].style.bold  # стиль узято з рядка, що був на цьому місці
    assert not table.cells[1][0].binding.enabled  # але не прив'язку до даних
    table_ops.insert_row(table, 99)
    assert texts(table)[-1] == ["", ""] and table.rows == 5


def test_delete_row_and_col(table):
    table_ops.delete_row(table, 0)
    table_ops.delete_col(table, 1)
    table_ops.check(table)
    assert texts(table) == [["10"], ["20"]]
    table_ops.delete_col(table, 0) if False else None
    with pytest.raises(TableError):
        table_ops.delete_col(table, 0)
    table_ops.delete_row(table, 0)
    with pytest.raises(TableError):
        table_ops.delete_row(table, 0)


def test_insert_col(table):
    table_ops.insert_col(table, 0)
    table_ops.check(table)
    assert texts(table) == [["", "00", "01"], ["", "10", "11"], ["", "20", "21"]]
    assert table.col_widths == [1.0, 1.0, 1.0]


def test_resize_preserves_data(table):
    table_ops.resize(table, 5, 4)
    table_ops.check(table)
    assert texts(table)[:3] == [["00", "01", "", ""], ["10", "11", "", ""], ["20", "21", "", ""]]
    table_ops.resize(table, 2, 1)
    assert texts(table) == [["00"], ["10"]]
    with pytest.raises(TableError):
        table_ops.resize(table, 0, 1)


def test_positions_and_move_divider():
    assert table_ops.positions([1, 1, 2], 400) == [0, 100, 200, 400]
    weights = table_ops.move_divider([1, 1, 2], 0, 150, 400)
    assert table_ops.positions(weights, 400) == pytest.approx([0, 150, 200, 400])
    assert sum(weights) == pytest.approx(4)
    # межу не можна протягнути за сусідню
    weights = table_ops.move_divider([1, 1], 0, 1000, 200)
    assert table_ops.positions(weights, 200)[1] == pytest.approx(196)


def test_table_json_roundtrip(table):
    template = Template(elements=[table])
    restored = ser.template_from_dict(json.loads(json.dumps(ser.template_to_dict(template))))
    assert restored == template


def test_old_table_without_new_fields_loads():
    data = {"elements": [{"type": "table", "rows": 1, "cols": 1, "col_widths": [1], "row_heights": [1],
                          "cells": [[{"text": "x"}]]}]}
    t = ser.template_from_dict(data).elements[0]
    assert t.border_outer and t.cells[0][0].wrap and t.stripe.kind == "none"


# --- Відмальовування ---------------------------------------------------------------

@pytest.fixture
def spec_table(qapp):
    t = TableElement.create(4, 2, x=40, y=40, width=520, height=240, corner_radius=16,
                            border=Stroke(color="#C9D1DE", width=2),
                            background=Paint(color="#FFFFFF"), stripe=Paint(color="#F1F5FF"))
    t.col_widths = [1.0, 1.3]
    rows = [("Переріз", "18 AWG"), ("Довжина", "1 м"), ("Ізоляція", "силікон"),
            ("Робоча температура", "від −60 до +200 °C, дуже довгий текст значення")]
    for r, (label, value) in enumerate(rows):
        t.cells[r][0].text, t.cells[r][1].text = label, value
        for cell in t.cells[r]:
            cell.style.font_family = "Arial"
            cell.style.font_size = 26
            cell.padding = 12
        t.cells[r][1].style.bold = True
        t.cells[r][1].style.color = "#1E5BFF"
    t.cells[0][0].background = Paint(color="#FFD54A")
    t.cells[0][1].binding.enabled = True
    t.cells[0][1].binding.suffix = " ★"
    return t


def test_table_matches_golden(workspace, spec_table):
    c = workspace.create_category("Кабель")
    template = Template(width=600, height=320, elements=[spec_table])
    ctx = RenderContext(workspace, c.id)
    image = render_template(template, ctx)
    assert_matches_golden(image, "table_spec")
    assert cell_overflow_id(spec_table.id, 3, 1) not in ctx.overflow  # зменшився й вмістився


def test_table_cell_overflow_reported(workspace, spec_table):
    c = workspace.create_category("Кабель")
    spec_table.cells[2][1].text = "дуже " * 60
    spec_table.cells[2][1].min_font_size = 20
    ctx = RenderContext(workspace, c.id)
    render_template(Template(elements=[spec_table]), ctx)
    assert cell_overflow_id(spec_table.id, 2, 1) in ctx.overflow
    assert spec_table.id in ctx.overflow  # і сама таблиця підсвічується в редакторі


# --- Редактор -----------------------------------------------------------------------

@pytest.fixture
def editor(qtbot, workspace):
    c = workspace.create_category("Кабель")
    t = workspace.create_template(c.id, "Характеристики")
    page = EditorPage(workspace)
    qtbot.addWidget(page)
    page.resize(1400, 900)
    page.show()
    page.open_template(c.id, t.id)
    page.snap_box.setChecked(False)
    page.ws, page.cat, page.tpl = workspace, c, t
    return page


def find(panel, cls, name):
    """Видимий віджет (старі копії панелі ще можуть чекати видалення)."""
    visible = [w for w in panel.findChildren(cls, name) if w.isVisibleTo(panel)]
    assert len(visible) == 1, (name, len(visible))
    return visible[0]


def test_add_table_block(editor):
    table = editor.add_block("table")
    assert isinstance(table, TableElement) and (table.rows, table.cols) == (5, 2)
    assert editor.properties.target is table
    mirror = find(editor.properties, QTableWidget, "tableMirror")
    assert mirror.rowCount() == 5 and mirror.item(0, 0).text() == "Параметр 1"


def test_rows_cols_spin_and_buttons(editor):
    table = editor.add_block("table")
    find(editor.properties, QSpinBox, "table_rows").setValue(7)
    assert table.rows == 7
    find(editor.properties, QSpinBox, "table_cols").setValue(3)
    assert table.cols == 3
    editor.properties.select_cells({(2, 1)})
    find(editor.properties, QPushButton, "btn_row_above").click()
    assert table.rows == 8 and table.cells[2][0].text == ""
    assert table.cells[3][0].text == "Параметр 3"
    find(editor.properties, QPushButton, "btn_col_delete").click()
    assert table.cols == 2
    table_ops.check(table)
    editor.undo()
    current = editor.template.elements[0]
    assert current.cols == 3


def test_mirror_editing_and_undo(editor):
    table = editor.add_block("table")
    mirror = find(editor.properties, QTableWidget, "tableMirror")
    mirror.item(0, 1).setText("18 AWG")
    assert table.cells[0][1].text == "18 AWG"
    editor.save_now()
    saved = editor.ws.load_template(editor.cat.id, editor.tpl.id).elements[0]
    assert saved.cells[0][1].text == "18 AWG"
    editor.undo()
    assert editor.template.elements[0].cells[0][1].text == ""


def test_style_applies_to_all_selected_cells(editor):
    table = editor.add_block("table")
    mirror = find(editor.properties, QTableWidget, "tableMirror")
    mirror.clearSelection()
    for r in range(3):
        mirror.item(r, 1).setSelected(True)
    assert editor.properties.table_cells == {(0, 1), (1, 1), (2, 1)}
    from PySide6.QtWidgets import QDoubleSpinBox
    find(editor.properties, QDoubleSpinBox, "cell_font_size").setValue(40)
    find(editor.properties, ColorButton, "cell_background").choose("#FFD54A")
    assert [table.cells[r][1].style.font_size for r in range(5)] == [40, 40, 40, 28, 28]
    assert table.cells[2][1].background.kind == "solid"
    assert table.cells[3][1].background.kind == "none"
    # мініатюра лишилась із тим самим виділенням після змін
    mirror = find(editor.properties, QTableWidget, "tableMirror")
    assert {(i.row(), i.column()) for i in mirror.selectedItems()} == {(0, 1), (1, 1), (2, 1)}


def test_cell_binding_settings(editor):
    table = editor.add_block("table")
    editor.properties.select_cells({(0, 1)})
    from PySide6.QtWidgets import QCheckBox, QComboBox
    find(editor.properties, QCheckBox, "cell_enabled").setChecked(True)
    find(editor.properties, QComboBox, "cell_column").setEditText("Переріз")
    assert table.cells[0][1].binding.enabled and table.cells[0][1].binding.column == "Переріз"


def test_click_cell_on_canvas_and_highlight(editor):
    table = editor.add_block("table")
    item = editor.scene.items_by_id[table.id]
    cell = item.cell_at(QPointF(table.width * 0.9, table.height * 0.5))
    assert cell == (2, 1)
    item.cellClicked.emit(table.id, 2, 1, False)
    item.cellClicked.emit(table.id, 3, 1, True)
    assert editor.properties.table_cells == {(2, 1), (3, 1)}
    assert item.selected_cells == {(2, 1), (3, 1)}
    editor.select_canvas()
    assert item.selected_cells == set()


def test_drag_column_divider(editor):
    table = editor.add_block("table")
    editor.view.set_zoom(1.0)
    item = editor.scene.items_by_id[table.id]
    xs = table_ops.positions(table.col_widths, table.width)
    assert item.divider_at(QPointF(xs[1], 10)) == ("col", 0)
    assert item.divider_at(QPointF(xs[1] + 40, 10)) is None
    item.begin_divider("col", 0)
    item.divider_to(item.mapToScene(QPointF(200, 10)))
    item.committed.emit(table.id, "Ширина стовпця")
    assert table_ops.positions(table.col_widths, table.width)[1] == pytest.approx(200)
    editor.undo()
    current = editor.template.elements[0]
    assert table_ops.positions(current.col_widths, current.width)[1] == pytest.approx(xs[1])


def test_table_editor_matches_export(editor):
    """Таблиця на полотні = таблиця в експорті."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter

    from cardgen.render.painter import setup_painter
    from imaging import difference

    table = editor.add_block("table")
    table.stripe = Paint(color="#F1F5FF")
    table.corner_radius = 20
    editor.scene.items_by_id[table.id].sync_from_model()
    editor.select_canvas()
    w, h = editor.template.width, editor.template.height
    from_editor = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(from_editor)
    setup_painter(painter)
    editor.scene.render(painter, QRectF(0, 0, w, h), QRectF(0, 0, w, h))
    painter.end()
    exported = render_template(editor.template, RenderContext(editor.ws, editor.cat.id))
    mean, strong = difference(from_editor, exported)
    assert mean < 0.5 and strong < 0.002, (mean, strong)
