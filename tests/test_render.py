from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QFontMetricsF, QImage

from cardgen.model import (
    Background,
    IconElement,
    Paint,
    PhotoElement,
    Shadow,
    ShapeElement,
    Stroke,
    Template,
    TextElement,
    TextStyle,
)
from cardgen.render import RenderContext, render_template
from cardgen.render.colors import normalize, qcolor, to_hex
from cardgen.render.text import layout_text, make_font
from imaging import assert_matches_golden

pytestmark = pytest.mark.usefixtures("qapp")

BOLT_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<path d="M13 2L3 14h7l-1 8 10-12h-7z" fill="#000"/></svg>')


def make_png(path: Path, w: int, h: int, color: str) -> Path:
    image = QImage(w, h, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    for x in range(w // 2):  # діагональ, щоб було видно масштаб і зсув
        for d in range(4):
            if x + d < h:
                image.setPixelColor(x, x + d, QColor("#FFFFFF"))
    image.save(str(path))
    return path


@pytest.fixture
def card(workspace, tmp_path):
    """Картка з усіма видами вмісту етапу 3."""
    c = workspace.create_category("Кабель")
    icon = tmp_path / "bolt.svg"
    icon.write_text(BOLT_SVG, encoding="utf-8")
    icon_ref = workspace.add_to_library("icons", icon)
    bg_ref = workspace.add_to_library("backgrounds", make_png(tmp_path / "bg.png", 64, 64, "#DDE6F7"))
    photo_ref = workspace.add_category_asset(c.id, make_png(tmp_path / "cable.png", 120, 80, "#C0392B"))
    template = Template(
        width=600, height=600,
        background=Background(color="#F4F7FC", asset=bg_ref, fit="cover", scale=0.5),
        elements=[
            TextElement(x=30, y=20, width=360, height=110, text="Кабель силіконовий AWG 18",
                        style=TextStyle(font_family="Arial", font_size=44, bold=True, color="#0B1F44")),
            ShapeElement(x=30, y=150, width=320, height=40, corner_radius=10, fill=Paint(color="#FFD54A")),
            TextElement(x=30, y=150, width=320, height=40, text="1 м • червоний",
                        style=TextStyle(font_family="Arial", font_size=22, align="center", valign="middle")),
            ShapeElement(x=30, y=220, width=150, height=110, corner_radius=14,
                         fill=Paint(kind="linear", color="#2F6BFF", color2="#1747D6", angle=90),
                         shadow=Shadow(enabled=True, blur=12, offset_y=6, color="#1E5BFF66")),
            ShapeElement(x=200, y=220, width=110, height=110, shape="ellipse",
                         fill=Paint(color="#00BF63"), stroke=Stroke(color="#0B1F44", width=4)),
            IconElement(x=225, y=245, width=60, height=60, asset=icon_ref, tint="#FFFFFF"),
            ShapeElement(x=30, y=360, width=540, height=20, shape="line",
                         stroke=Stroke(color="#C9D1DE", width=3)),
            PhotoElement(x=380, y=60, width=180, height=240, rotation=-10, corner_radius=20,
                         placeholder=photo_ref, fit="cover", content_scale=1.2,
                         shadow=Shadow(enabled=True, blur=16, offset_y=8)),
            PhotoElement(x=30, y=410, width=160, height=160),  # без зразка — заглушка
            ShapeElement(x=220, y=410, width=200, height=160, fill=Paint(color="#FF5757"),
                         opacity=0.5, rotation=15),
            ShapeElement(x=450, y=410, width=100, height=100, visible=False, fill=Paint(color="#000000")),
        ],
    )
    return template, RenderContext(workspace, c.id)


def test_card_matches_golden(card):
    template, ctx = card
    assert_matches_golden(render_template(template, ctx), "card_basic")


def test_render_size_and_scale(card):
    template, ctx = card
    assert render_template(template, ctx).size().toTuple() == (600, 600)
    assert render_template(template, ctx, scale=0.25).size().toTuple() == (150, 150)


def test_render_is_deterministic(card):
    template, ctx = card
    assert render_template(template, ctx) == render_template(template, ctx)


def test_hidden_element_not_drawn(card):
    template, ctx = card
    image = render_template(template, ctx)
    assert image.pixelColor(500, 460) != QColor("#000000")


def test_missing_assets_do_not_crash(workspace):
    c = workspace.create_category("Кабель")
    template = Template(background=Background(asset="library:backgrounds/нема.png"), elements=[
        IconElement(asset="library:icons/нема.svg"),
        PhotoElement(placeholder="category:assets/нема.png"),
        IconElement(asset="library:../../evil"),
    ])
    render_template(template, RenderContext(workspace, c.id))


# --- Текст -------------------------------------------------------------------

STYLE = TextStyle(font_family="Arial", font_size=40)


def test_text_fits_without_shrink():
    layout = layout_text("Кабель", STYLE, 400, 100)
    assert layout.font_size == 40 and not layout.overflow and layout.lines == ["Кабель"]


def test_text_wraps_by_words():
    layout = layout_text("Кабель силіконовий AWG", STYLE, 260, 200, auto_shrink=False)
    assert len(layout.lines) > 1
    assert " ".join(layout.lines) == "Кабель силіконовий AWG"
    fm = QFontMetricsF(make_font(STYLE, 40))
    assert all(fm.horizontalAdvance(line) <= 260.5 for line in layout.lines)


def test_text_shrinks_to_fit():
    text = "Дуже довгий текст, що не влізе в маленьку рамку"
    layout = layout_text(text, STYLE, 300, 100, min_font_size=8)
    assert 8 <= layout.font_size < 40
    assert not layout.overflow
    assert layout.height <= 100.5 and layout.width <= 300.5
    # на 1 px більше вже не вміщується — вибрано найбільший можливий розмір
    bigger = layout_text(text, TextStyle(font_family="Arial", font_size=layout.font_size + 1),
                         300, 100, auto_shrink=False)
    assert bigger.overflow


def test_text_overflow_at_min_size():
    layout = layout_text("Дуже " * 50, STYLE, 100, 30, min_font_size=20)
    assert layout.overflow and layout.font_size == 20


def test_no_shrink_marks_overflow():
    layout = layout_text("Дуже довгий текст", STYLE, 100, 30, auto_shrink=False)
    assert layout.overflow and layout.font_size == 40


def test_no_wrap_keeps_single_line():
    layout = layout_text("Кабель силіконовий AWG", STYLE, 300, 200, wrap=False)
    assert len(layout.lines) == 1
    assert not layout.overflow and layout.font_size < 40  # зменшився по ширині


def test_explicit_newlines_kept():
    assert layout_text("Рядок 1\nРядок 2", STYLE, 1000, 1000).lines == ["Рядок 1", "Рядок 2"]


def test_long_word_is_broken():
    layout = layout_text("Надзвичайнодовгесловобезпробілів", STYLE, 150, 1000, auto_shrink=False)
    assert len(layout.lines) > 1 and "".join(layout.lines) == "Надзвичайнодовгесловобезпробілів"


def test_text_overflow_reported_in_context(workspace):
    c = workspace.create_category("Кабель")
    text = TextElement(width=100, height=40, text="Дуже " * 40, min_font_size=18,
                       style=TextStyle(font_family="Arial", font_size=30))
    ctx = RenderContext(workspace, c.id)
    render_template(Template(elements=[text]), ctx)
    assert text.id in ctx.overflow
    text.text = "Ок"
    render_template(Template(elements=[text]), ctx)
    assert text.id not in ctx.overflow


# --- Кольори ------------------------------------------------------------------

def test_colors():
    assert normalize("1e5bff") == "#1E5BFF"
    assert normalize("#1E5BFFFF") == "#1E5BFF"
    assert normalize("#1E5BFF80") == "#1E5BFF80"
    with pytest.raises(ValueError):
        normalize("синій")
    assert to_hex(qcolor("#1E5BFF80")) == "#1E5BFF80"
    assert qcolor("ерунда", "#FF0000") == QColor("#FF0000")
