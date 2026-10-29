"""Редактор шаблону: блоки, властивості, мишка, автозбереження, відповідність експорту."""
import math

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QDoubleSpinBox

from cardgen.model import IconElement, PhotoElement, ShapeElement, TextElement
from cardgen.render import RenderContext, render_template
from cardgen.render.painter import setup_painter
from cardgen.ui.color_button import ColorButton, ColorPopup
from cardgen.ui.editor import page as page_module
from cardgen.ui.editor.page import EditorPage
from imaging import difference

ICON_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<circle cx="5" cy="5" r="4" fill="#000"/></svg>')


@pytest.fixture
def setup(qtbot, workspace, tmp_path, monkeypatch):
    c = workspace.create_category("Кабель")
    t = workspace.create_template(c.id, "Обкладинка")
    icon = tmp_path / "dot.svg"
    icon.write_text(ICON_SVG, encoding="utf-8")
    ref = workspace.add_to_library("icons", icon)
    monkeypatch.setattr(page_module, "pick_asset", lambda *a, **k: ref)
    editor = EditorPage(workspace)
    qtbot.addWidget(editor)
    editor.resize(1200, 800)
    editor.show()
    editor.open_template(c.id, t.id)
    return editor, workspace, c, t


def reload(workspace, c, t):
    return workspace.load_template(c.id, t.id)


def spin(editor, name) -> QDoubleSpinBox:
    widget = editor.properties.findChild(QDoubleSpinBox, name)
    assert widget is not None, name
    return widget


def test_add_every_block_and_save(setup):
    editor, workspace, c, t = setup
    for key in ["text", "rect", "ellipse", "line", "icon", "photo"]:
        editor.add_block(key)
    assert editor.save_now()
    saved = reload(workspace, c, t)
    kinds = [type(e).__name__ for e in saved.elements]
    assert kinds == ["TextElement", "ShapeElement", "ShapeElement", "ShapeElement",
                     "IconElement", "PhotoElement"]
    assert [e.shape for e in saved.elements if isinstance(e, ShapeElement)] == ["rect", "ellipse", "line"]
    assert saved.elements[4].asset.startswith("library:icons/")
    assert [e.name for e in saved.elements][:2] == ["Текст 1", "Прямокутник 1"]
    # новий блок по центру полотна і виділений
    photo = saved.elements[-1]
    assert photo.x + photo.width / 2 == pytest.approx(saved.width / 2)
    assert editor.selected_element().id == photo.id


def test_property_change_updates_model_and_saves(setup, qtbot):
    editor, workspace, c, t = setup
    text = editor.add_block("text")
    spin(editor, "font_size").setValue(77)
    spin(editor, "x").setValue(123)
    assert text.style.font_size == 77
    assert editor.scene.items_by_id[text.id].pos().x() == 123
    assert editor.dirty
    qtbot.waitUntil(lambda: not editor.dirty, timeout=3000)  # автозбереження
    saved = reload(workspace, c, t).elements[0]
    assert (saved.style.font_size, saved.x) == (77, 123)


def test_canvas_properties_when_nothing_selected(setup):
    editor, workspace, c, t = setup
    editor.select_canvas()
    assert editor.properties.target is editor.template
    spin(editor, "width").setValue(1200)
    assert editor.template.width == 1200
    assert editor.scene.canvas_rect().width() == 1200


def test_drag_moves_element(setup):
    editor, *_ = setup
    rect = editor.add_block("rect")
    item = editor.scene.items_by_id[rect.id]
    item.setPos(10, 20)  # те саме, що робить Qt під час перетягування
    assert (rect.x, rect.y) == (10, 20)
    assert spin(editor, "x").value() == 10  # панель оновилась


def test_resize_with_handle(setup):
    editor, *_ = setup
    rect = editor.add_block("rect")
    rect.x, rect.y, rect.width, rect.height = 100, 100, 200, 100
    item = editor.scene.items_by_id[rect.id]
    item.sync_from_model()
    item.begin_resize("se")
    item.resize_to(QPointF(400, 300))
    assert (rect.x, rect.y, rect.width, rect.height) == pytest.approx((100, 100, 300, 200))
    item.begin_resize("nw")
    item.resize_to(QPointF(150, 50))
    assert (rect.x, rect.y, rect.width, rect.height) == pytest.approx((150, 50, 250, 250))


def test_resize_rotated_keeps_opposite_corner(setup):
    editor, *_ = setup
    rect = editor.add_block("rect")
    rect.x, rect.y, rect.width, rect.height, rect.rotation = 200, 200, 200, 100, 30
    item = editor.scene.items_by_id[rect.id]
    item.sync_from_model()
    anchor_before = item.mapToScene(QPointF(0, 0))  # протилежний кут для "se"
    target = item.mapToScene(QPointF(260, 150))
    item.begin_resize("se")
    item.resize_to(target)
    assert (rect.width, rect.height) == pytest.approx((260, 150))
    anchor_after = item.mapToScene(QPointF(0, 0))
    assert anchor_after.x() == pytest.approx(anchor_before.x(), abs=1e-6)
    assert anchor_after.y() == pytest.approx(anchor_before.y(), abs=1e-6)


def test_photo_corner_keeps_ratio_and_shift_frees_it(setup):
    editor, *_ = setup
    photo = editor.add_block("photo")
    photo.x, photo.y, photo.width, photo.height = 0, 0, 200, 100
    item = editor.scene.items_by_id[photo.id]
    item.sync_from_model()
    item.begin_resize("se")
    item.resize_to(QPointF(400, 120), keep_ratio=True)
    assert photo.width / photo.height == pytest.approx(2)
    item.begin_resize("se")
    item.resize_to(QPointF(300, 300), keep_ratio=False)
    assert (photo.width, photo.height) == pytest.approx((300, 300))


def test_minimum_size(setup):
    editor, *_ = setup
    rect = editor.add_block("rect")
    item = editor.scene.items_by_id[rect.id]
    item.begin_resize("se")
    item.resize_to(QPointF(-1000, -1000))
    assert rect.width >= 4 and rect.height >= 4


def test_locked_element_not_movable_no_handles(setup):
    editor, *_ = setup
    rect = editor.add_block("rect")
    rect.locked = True
    item = editor.scene.items_by_id[rect.id]
    item.sync_from_model()
    assert not (item.flags() & item.GraphicsItemFlag.ItemIsMovable)
    assert item._handle_rects() == {}
    editor.nudge(10, 0)
    assert rect.x == pytest.approx((editor.template.width - rect.width) / 2)


def test_nudge_and_delete(setup):
    editor, workspace, c, t = setup
    rect = editor.add_block("rect")
    x0 = rect.x
    editor.nudge(10, -1)
    assert rect.x == x0 + 10
    editor.delete_selected()
    assert editor.template.elements == []
    assert rect.id not in editor.scene.items_by_id
    editor.save_now()
    assert reload(workspace, c, t).elements == []


def test_shape_fill_kind_rebuilds_panel(setup):
    editor, *_ = setup
    rect = editor.add_block("rect")
    from PySide6.QtWidgets import QComboBox
    kind = editor.properties.findChild(QComboBox, "fill_kind")
    kind.setCurrentIndex(kind.findData("linear"))
    assert rect.fill.kind == "linear"
    assert editor.properties.findChild(ColorButton, "fill_color2") is not None


def test_editor_matches_export(setup, tmp_path):
    """Головна гарантія: що на полотні редактора — те й в експорті."""
    editor, workspace, c, t = setup
    for key in ["rect", "ellipse", "text", "line", "icon", "photo"]:
        editor.add_block(key)
    els = editor.template.elements
    els[0].x, els[0].y, els[0].rotation = 50, 60, 20
    els[0].shadow.enabled = True
    els[2].text = "Кабель силіконовий AWG 18 — дуже довгий заголовок"
    els[2].x, els[2].y = 40, 600
    els[4].tint = "#FF5757"
    els[5].x, els[5].opacity = 600, 0.7
    for item in editor.scene.items_by_id.values():
        item.sync_from_model()
    editor.select_canvas()

    w, h = editor.template.width, editor.template.height
    from_editor = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(from_editor)
    setup_painter(painter)
    editor.scene.render(painter, QRectF(0, 0, w, h), QRectF(0, 0, w, h))
    painter.end()
    exported = render_template(editor.template, RenderContext(workspace, c.id))

    mean, strong = difference(from_editor, exported)
    assert mean < 0.5 and strong < 0.002, (mean, strong)


# --- Останні кольори --------------------------------------------------------

def test_recent_colors_storage(workspace):
    assert workspace.recent_colors() == []
    workspace.add_recent_color("#1e5bff")
    workspace.add_recent_color("#FFD54A")
    workspace.add_recent_color("#1E5BFF")
    assert workspace.recent_colors() == ["#1E5BFF", "#FFD54A"]
    for i in range(30):
        workspace.add_recent_color(f"#0000{i:02X}")
    assert len(workspace.recent_colors()) == 16
    assert workspace.recent_colors()[0] == "#00001D"


def test_color_button_remembers_choice(setup, qtbot):
    editor, workspace, *_ = setup
    text = editor.add_block("text")
    button = editor.properties.findChild(ColorButton, "text_color")
    button.choose("#FF66C4")
    assert text.style.color == "#FF66C4"
    assert workspace.recent_colors()[0] == "#FF66C4"
    popup = ColorPopup("#000000", workspace.recent_colors(), allow_none=False)
    qtbot.addWidget(popup)
    picked = []
    popup.picked.connect(picked.append)
    popup.findChild(type(popup.findChild(object, "recent_0")), "recent_0").click()
    assert picked == ["#FF66C4"]


def test_color_popup_hex_and_none(qtbot):
    popup = ColorPopup("", [], allow_none=True)
    qtbot.addWidget(popup)
    picked = []
    popup.picked.connect(picked.append)
    popup.hex_edit.setText("1e5bff")
    popup.hex_edit.returnPressed.emit()
    popup.hex_edit.setText("не колір")
    popup.hex_edit.returnPressed.emit()
    from PySide6.QtWidgets import QPushButton
    popup.findChild(QPushButton, "btn_no_color").click()
    assert picked == ["#1E5BFF", ""]
