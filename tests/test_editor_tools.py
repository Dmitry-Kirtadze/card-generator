"""Етап 4: Undo/Redo, шари, групи, копіювання, вирівнювання, прилипання, поворот."""
import pytest
from PySide6.QtCore import QPointF, Qt

from cardgen.model import GroupElement, ShapeElement
from cardgen.model import ops
from cardgen.model.serialization import template_to_dict
from cardgen.ui.editor import page as page_module
from cardgen.ui.editor.layers import COL_LOCKED, COL_VISIBLE
from cardgen.ui.editor.page import EditorPage


@pytest.fixture
def editor(qtbot, workspace):
    c = workspace.create_category("Кабель")
    t = workspace.create_template(c.id, "Обкладинка")
    page = EditorPage(workspace)
    qtbot.addWidget(page)
    page.resize(1400, 900)
    page.show()
    page.open_template(c.id, t.id)
    page.snap_box.setChecked(False)
    page.grid_box.setChecked(False)
    page_module.CLIPBOARD.clear()
    page.ws, page.cat, page.tpl = workspace, c, t
    return page


def add_rect(editor, x, y, w=100, h=100, name=None):
    """Додає прямокутник однією дією в історії."""
    element = editor.make_block("rect")
    element.x, element.y, element.width, element.height = x, y, w, h
    if name:
        element.name = name
    editor.add_elements([element], "Новий блок")
    return element


def current(editor, element):
    """Після Undo/Redo шаблон створюється заново — шукаємо блок за id."""
    return ops.find(editor.template, element.id)


def state(editor):
    return template_to_dict(editor.template)


def drag(editor, element, dx, dy):
    item = editor.scene.items_by_id[element.id]
    start = item.mapToScene(item.local_rect().center())
    item.begin_drag(start)
    item.drag_to(start + QPointF(dx, dy))
    item.committed.emit(element.id, "Переміщення")
    editor.scene.set_guides(None, None)


# --- Undo / Redo ----------------------------------------------------------------

def test_undo_redo_full_sequence_restores_exact_states(editor):
    states = [state(editor)]
    a = add_rect(editor, 100, 100)
    states.append(state(editor))
    b = add_rect(editor, 400, 100)
    states.append(state(editor))
    editor.select_ids([a.id])
    drag(editor, a, 50, 30)
    states.append(state(editor))
    add_rect(editor, 700, 100)
    states.append(state(editor))
    editor.select_ids([a.id, b.id])
    editor.group_selected()
    states.append(state(editor))
    editor.reorder("front")  # група над третім блоком
    states.append(state(editor))
    editor.delete_selected()
    states.append(state(editor))

    for expected in reversed(states[:-1]):
        editor.undo()
        assert state(editor) == expected
    assert not editor.history.can_undo()
    for expected in states[1:]:
        editor.redo()
        assert state(editor) == expected
    assert not editor.history.can_redo()


def test_undo_rebuilds_canvas_and_layers(editor):
    a = add_rect(editor, 10, 10)
    editor.select_ids([a.id])
    editor.delete_selected()
    assert a.id not in editor.scene.items_by_id
    editor.undo()
    assert a.id in editor.scene.items_by_id
    assert a.id in editor.layers.items


def test_typing_in_field_is_one_undo_step(editor):
    text = editor.add_block("text")
    from PySide6.QtWidgets import QPlainTextEdit
    field = editor.properties.findChild(QPlainTextEdit, "text")
    for value in ["К", "Ка", "Каб", "Кабель"]:
        field.setPlainText(value)
    assert editor.template.elements[0].text == "Кабель"
    editor.undo()
    assert editor.template.elements[0].text == "Текст"


def test_undo_is_saved(editor, qtbot):
    add_rect(editor, 10, 10)
    editor.undo()
    editor.save_now()
    assert editor.ws.load_template(editor.cat.id, editor.tpl.id).elements == []


# --- Групи та виділення -------------------------------------------------------

def test_click_on_group_member_selects_whole_group(editor):
    a, b, c = (add_rect(editor, x, 100) for x in (100, 300, 500))
    editor.select_ids([a.id, b.id])
    editor.group_selected()
    group = editor.template.elements[0]
    assert isinstance(group, GroupElement)

    editor.scene.clearSelection()
    editor.scene.items_by_id[a.id].setSelected(True)  # як клік мишею
    assert {i.element.id for i in editor.selected_items()} == {a.id, b.id}
    assert editor.selection_ids() == [group.id]
    assert editor.scene.group_outlines  # пунктир навколо групи

    editor._item_double_clicked(b.id)  # подвійний клік — окремий блок
    assert editor.selection_ids() == [b.id]
    drag(editor, b, 0, 50)
    assert (a.y, b.y) == (100, 150)
    assert group.height == 150  # рамка групи оновилась

    editor.scene.clearSelection()
    editor.scene.items_by_id[c.id].setSelected(True)
    assert editor.entered_group is None


def test_drag_group_moves_all_members(editor):
    a, b = add_rect(editor, 100, 100), add_rect(editor, 300, 100)
    editor.select_ids([a.id, b.id])
    editor.group_selected()
    drag(editor, a, 10, 20)
    assert [(a.x, a.y), (b.x, b.y)] == [(110, 120), (310, 120)]


def test_ungroup(editor):
    a, b = add_rect(editor, 100, 100), add_rect(editor, 300, 100)
    editor.select_ids([a.id, b.id])
    editor.group_selected()
    editor.ungroup_selected()
    assert [e.id for e in editor.template.elements] == [a.id, b.id]
    assert set(editor.selection_ids()) == {a.id, b.id}


def test_group_saved_and_loaded(editor):
    a, b = add_rect(editor, 100, 100), add_rect(editor, 300, 100)
    editor.select_ids([a.id, b.id])
    editor.group_selected()
    editor.save_now()
    loaded = editor.ws.load_template(editor.cat.id, editor.tpl.id)
    assert loaded == editor.template
    assert isinstance(loaded.elements[0], GroupElement)


# --- Шари ------------------------------------------------------------------------

def test_layers_list_top_first_and_reorder(editor):
    a = add_rect(editor, 0, 0, name="A")
    b = add_rect(editor, 0, 0, name="B")
    c = add_rect(editor, 0, 0, name="C")
    tree = editor.layers.tree
    names = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
    assert names == ["C", "B", "A"]
    editor.select_ids([a.id])
    editor.reorder("front")
    assert [e.name for e in editor.template.elements] == ["B", "C", "A"]
    assert editor.scene.items_by_id[a.id].zValue() > editor.scene.items_by_id[c.id].zValue()
    assert tree.topLevelItem(0).text(0) == "A"


def test_layers_visibility_lock_rename(editor):
    a = add_rect(editor, 0, 0, name="A")
    item = editor.layers.items[a.id]
    item.setCheckState(COL_VISIBLE, Qt.CheckState.Unchecked)
    assert not a.visible and not editor.scene.items_by_id[a.id].isVisible()
    item = editor.layers.items[a.id]  # дерево перебудовано
    item.setCheckState(COL_LOCKED, Qt.CheckState.Checked)
    assert a.locked
    editor.layers.items[a.id].setText(0, "Фон-плашка")
    assert a.name == "Фон-плашка"
    editor.undo()
    assert current(editor, a).name == "A"


def test_hidden_group_hides_members_and_locked_group_blocks_nudge(editor):
    a, b = add_rect(editor, 100, 100), add_rect(editor, 300, 100)
    editor.select_ids([a.id, b.id])
    editor.group_selected()
    group = editor.template.elements[0]
    editor._set_flag(group.id, "locked", True)
    editor.select_ids([group.id])
    editor.nudge(10, 0)
    assert a.x == 100
    editor._set_flag(group.id, "visible", False)
    assert not editor.scene.items_by_id[a.id].isVisible()


def test_select_in_layers_enters_group(editor):
    a, b = add_rect(editor, 100, 100), add_rect(editor, 300, 100)
    editor.select_ids([a.id, b.id])
    editor.group_selected()
    editor._layers_selection([b.id])
    assert editor.selection_ids() == [b.id]


# --- Копіювання --------------------------------------------------------------------

def test_copy_paste_cut_duplicate(editor):
    a = add_rect(editor, 100, 100, name="A")
    editor.select_ids([a.id])
    editor.copy_selected()
    editor.paste()
    pasted = editor.template.elements[-1]
    assert pasted.id != a.id and (pasted.x, pasted.y) == (120, 120) and pasted.name == "A"
    editor.paste()
    assert (editor.template.elements[-1].x, editor.template.elements[-1].y) == (140, 140)

    editor.select_ids([a.id])
    editor.duplicate_selected()
    assert editor.template.elements[1].x == 120  # копія одразу над оригіналом
    assert editor.selection_ids() == [editor.template.elements[1].id]

    count = len(editor.template.elements)
    editor.cut_selected()
    assert len(editor.template.elements) == count - 1
    editor.paste()
    assert len(editor.template.elements) == count


def test_copy_group_gets_new_ids(editor):
    a, b = add_rect(editor, 100, 100), add_rect(editor, 300, 100)
    editor.select_ids([a.id, b.id])
    editor.group_selected()
    editor.copy_selected()
    editor.paste()
    copy = editor.template.elements[-1]
    assert isinstance(copy, GroupElement)
    assert {c.id for c in copy.children}.isdisjoint({a.id, b.id})
    assert all(c.id in editor.scene.items_by_id for c in copy.children)


# --- Вирівнювання ----------------------------------------------------------------

def test_align_single_to_canvas_center(editor):
    a = add_rect(editor, 10, 10, 200, 100)
    editor.select_ids([a.id])
    editor.align("hcenter")
    editor.align("vcenter")
    assert (a.x, a.y) == (400, 450)


def test_align_many_and_distribute(editor):
    a = add_rect(editor, 0, 50, 100, 100)
    b = add_rect(editor, 300, 0, 100, 50)
    c = add_rect(editor, 900, 200, 100, 100)
    editor.select_ids([a.id, b.id, c.id])
    editor.align("top")
    assert {a.y, b.y, c.y} == {0}
    b.x = 150
    editor.scene.items_by_id[b.id].sync_from_model()
    editor.distribute("h")
    assert (a.x, b.x, c.x) == (0, 450, 900)
    editor.undo()
    assert current(editor, b).x == 300  # стан до розподілу (ручна зміна x не була дією)


# --- Прилипання та сітка -------------------------------------------------------------

def test_drag_snaps_to_canvas_center_and_shows_guide(editor):
    editor.snap_box.setChecked(True)
    editor.view.set_zoom(1.0)
    a = add_rect(editor, 0, 0, 100, 100)
    editor.select_ids([a.id])
    item = editor.scene.items_by_id[a.id]
    start = QPointF(50, 50)
    item.begin_drag(start)
    item.drag_to(start + QPointF(447, 200))  # центр -> 497, поріг 6 px
    assert a.x == 450  # центр прилип до 500
    assert editor.scene.guides[0] == 500


def test_drag_snaps_to_other_block_edge(editor):
    editor.snap_box.setChecked(True)
    editor.view.set_zoom(1.0)
    add_rect(editor, 700, 600, 100, 100)
    a = add_rect(editor, 0, 0, 100, 100)
    editor.select_ids([a.id])
    item = editor.scene.items_by_id[a.id]
    item.begin_drag(QPointF(50, 50))
    item.drag_to(QPointF(50 + 597, 50 + 303))
    # правий край 697 прилип до лівого краю сусіда (700); по y прилипати нема до чого
    assert (a.x, a.y) == (600, 303)
    assert editor.scene.guides == (700, None)


def test_no_snap_when_disabled(editor):
    editor.view.set_zoom(1.0)
    a = add_rect(editor, 0, 0, 100, 100)
    editor.select_ids([a.id])
    drag(editor, a, 447, 0)
    assert a.x == 447


def test_grid_snap_and_settings_saved(editor):
    editor.snap_box.setChecked(True)
    editor.grid_box.setChecked(True)
    editor.grid_size.setValue(40)
    editor.view.set_zoom(1.0)
    a = add_rect(editor, 0, 0, 30, 30)
    editor.select_ids([a.id])
    item = editor.scene.items_by_id[a.id]
    item.begin_drag(QPointF(5, 5))
    item.drag_to(QPointF(5 + 78, 5 + 163))
    assert (a.x, a.y) == (80, 160)
    assert editor.ws.editor_settings() == {"snap": True, "grid": True, "grid_size": 40}


def test_resize_snaps_edge(editor):
    editor.snap_box.setChecked(True)
    editor.view.set_zoom(1.0)
    a = add_rect(editor, 100, 100, 100, 100)
    item = editor.scene.items_by_id[a.id]
    item.begin_resize("e")
    item.resize_to(QPointF(497, 150))
    assert a.x + a.width == 500


# --- Поворот -------------------------------------------------------------------------

def test_rotate_handle(editor):
    a = add_rect(editor, 100, 100, 200, 100)
    item = editor.scene.items_by_id[a.id]
    item._rotating = True
    item.rotate_to(QPointF(400, 151))  # праворуч від центру (200,150) -> 90°
    assert a.rotation == 90
    item.rotate_to(QPointF(300, 50), step=15)  # 45° рівно
    assert a.rotation == 45
    item.rotate_to(QPointF(200 + 100, 150 + 30))  # ~106.7°, не прилипає
    assert 100 < a.rotation < 110
