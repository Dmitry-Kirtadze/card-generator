"""Операції над моделлю, історія Undo/Redo, прилипання — без інтерфейсу."""
import json

import pytest

from cardgen.model import GroupElement, ShapeElement, Template, TextElement
from cardgen.model import ops
from cardgen.model import serialization as ser
from cardgen.model.ops import OpError
from cardgen.ui.editor.history import History
from cardgen.ui.editor.snapping import snap_angle, snap_axis, snap_rect, snap_value


@pytest.fixture
def tpl():
    """a, b, c, d — прямокутники 100×100 у ряд."""
    elements = [ShapeElement(id=n, name=n, x=i * 150, y=0, width=100, height=100)
                for i, n in enumerate("abcd")]
    return Template(elements=elements)


def ids(elements):
    return [e.id for e in elements]


# --- Групування ---------------------------------------------------------------

def test_group_and_bounds(tpl):
    g = ops.group(tpl, ["b", "c"])
    assert ids(tpl.elements) == ["a", g.id, "d"]
    assert ids(g.children) == ["b", "c"]
    assert (g.x, g.y, g.width, g.height) == (150, 0, 250, 100)
    assert ops.parent_group(tpl, "b") is g
    assert ops.top_level(tpl, "c") is g


def test_group_takes_place_of_topmost_member(tpl):
    g = ops.group(tpl, ["a", "c"])
    assert ids(tpl.elements) == ["b", g.id, "d"]


def test_group_requires_same_level(tpl):
    ops.group(tpl, ["a", "b"])
    with pytest.raises(OpError):
        ops.group(tpl, ["a", "c"])
    with pytest.raises(OpError):
        ops.group(tpl, ["d"])


def test_ungroup_restores_order(tpl):
    g = ops.group(tpl, ["b", "c"])
    assert ops.ungroup(tpl, g.id) == ["b", "c"]
    assert ids(tpl.elements) == ["a", "b", "c", "d"]


def test_nested_group_roundtrip_json(tpl):
    inner = ops.group(tpl, ["a", "b"])
    outer = ops.group(tpl, [inner.id, "c"])
    restored = ser.template_from_dict(json.loads(json.dumps(ser.template_to_dict(tpl))))
    assert restored == tpl
    assert isinstance(restored.elements[0], GroupElement)
    assert ids(ops.leaves(restored.elements)) == ["a", "b", "c", "d"]
    assert ops.top_level(restored, "a").id == outer.id


def test_move_group_moves_children(tpl):
    g = ops.group(tpl, ["a", "b"])
    ops.move_by(g, 10, 5)
    assert [(e.x, e.y) for e in g.children] == [(10, 5), (160, 5)]
    assert (g.x, g.y) == (10, 5)


# --- Порядок шарів ------------------------------------------------------------

@pytest.mark.parametrize("mode, moved, expected", [
    ("up", ["b"], "acbd"),
    ("down", ["c"], "acbd"),
    ("front", ["a", "c"], "bdac"),
    ("back", ["b", "d"], "bdac"),
    ("up", ["d"], "abcd"),  # вже нагорі
    ("down", ["a"], "abcd"),
    ("up", ["a", "b"], "cabd"),
])
def test_reorder(tpl, mode, moved, expected):
    ops.reorder(tpl, moved, mode)
    assert "".join(ids(tpl.elements)) == expected


def test_reorder_inside_group(tpl):
    g = ops.group(tpl, ["a", "b", "c"])
    ops.reorder(tpl, ["a"], "front")
    assert ids(g.children) == ["b", "c", "a"]
    assert ids(tpl.elements) == [g.id, "d"]


# --- Видалення й копіювання ---------------------------------------------------

def test_delete_dissolves_single_child_group(tpl):
    g = ops.group(tpl, ["a", "b"])
    ops.delete(tpl, ["a"])
    assert ids(tpl.elements) == ["b", "c", "d"]
    assert ops.find(tpl, g.id) is None


def test_clone_gives_new_ids_everywhere(tpl):
    g = ops.group(tpl, ["a", "b"])
    copy = ops.clone(g)
    all_old = {e.id for e in ops.leaves([g])} | {g.id}
    all_new = {e.id for e in ops.leaves([copy])} | {copy.id}
    assert not all_old & all_new
    assert [c.x for c in copy.children] == [c.x for c in g.children]


def test_topmost_units(tpl):
    g = ops.group(tpl, ["b", "c"])
    assert ids(ops.topmost_units(tpl, ["d", "b", g.id, "a"])) == ["a", g.id, "d"]


# --- Історія -------------------------------------------------------------------

def state(n):
    return {"v": n}


def test_history_undo_redo_sequence():
    h = History()
    h.push(state(0), state(1), "1")
    h.push(state(1), state(2), "2")
    h.push(state(2), state(3), "3")
    assert h.undo() == state(2)
    assert h.undo() == state(1)
    assert h.redo() == state(2)
    assert h.undo() == state(1)
    assert h.undo() == state(0)
    assert h.undo() is None
    assert h.redo() == state(1)


def test_new_action_clears_redo():
    h = History()
    h.push(state(0), state(1), "1")
    h.undo()
    h.push(state(0), state(5), "5")
    assert not h.can_redo()
    assert h.undo() == state(0)


def test_merge_same_key():
    h = History()
    h.push(state(0), state(1), "Текст", "text")
    h.push(state(1), state(2), "Текст", "text")
    h.push(state(2), state(3), "Розмір", "size")
    assert h.undo() == state(2)
    assert h.undo() == state(0)  # дві правки тексту — одна дія


def test_seal_stops_merge():
    h = History()
    h.push(state(0), state(1), "Текст", "text")
    h.seal()
    h.push(state(1), state(2), "Текст", "text")
    assert h.undo() == state(1)


def test_noop_not_recorded_and_limit():
    h = History(limit=3)
    h.push(state(1), state(1), "нічого")
    assert not h.can_undo()
    for i in range(5):
        h.push(state(i), state(i + 1), str(i))
    undone = [h.undo() for _ in range(4)]
    assert undone == [state(4), state(3), state(2), None]


# --- Прилипання ---------------------------------------------------------------

def test_snap_axis_picks_nearest():
    s = snap_axis([100, 150, 200], [0, 153, 205], threshold=6)
    assert (s.delta, s.guide) == (3, 153)
    assert snap_axis([100], [200], threshold=6).guide is None


def test_snap_rect_to_canvas_center():
    sx, sy = snap_rect(447, 10, 100, 50, xs=[0, 500, 1000], ys=[0, 500, 1000], threshold=6)
    assert sx.delta == 3 and sx.guide == 500  # центр 497 -> 500
    assert sy.delta == -10 or sy.guide is None  # верх 10 далеко від 0 при порозі 6
    assert sy.guide is None


def test_snap_to_grid():
    sx, sy = snap_rect(48, 103, 10, 10, xs=[], ys=[], threshold=5, grid=50)
    assert (sx.delta, sx.guide) == (2, 50)
    assert (sy.delta, sy.guide) == (-3, 100)
    assert snap_value(97, [], 5, grid=50).guide == 100


@pytest.mark.parametrize("raw, step, expected", [
    (44, None, 45), (40, None, 40), (-91, None, -90), (190, None, -170), (181, None, 180),
    (37, 15, 30), (38, 15, 45), (359, None, 0), (-180, None, 180),
])
def test_snap_angle(raw, step, expected):
    assert snap_angle(raw, step) == expected
