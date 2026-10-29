"""Прибирання білого фону з фото товару."""
import pytest
from PIL import Image, ImageDraw
from PySide6.QtGui import QColor

from cardgen.model import Background, PhotoElement, Template
from cardgen.model import serialization as ser
from cardgen.render import RenderContext, render_template
from cardgen.render.background import background_mask, pil_to_qimage, qimage_to_pil, remove_white_background

pytestmark = pytest.mark.usefixtures("qapp")


def product_photo(size=900) -> Image.Image:
    """Білий фон, червоне кільце з білою серединою (біле всередині товару має лишитись)."""
    img = Image.new("RGB", (size, size), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.ellipse((150, 150, size - 150, size - 150), outline=(210, 30, 30), width=40)
    d.rectangle((420, 420, 480, 480), fill=(250, 250, 250))  # «бирка» всередині кільця
    d.rectangle((0, size - 60, size, size), fill=(240, 240, 240))  # світло-сіра «тінь» біля краю
    return img


def alpha_at(qimage, x, y) -> int:
    return QColor(qimage.pixelColor(x, y)).alpha()


def test_border_white_removed_inside_kept():
    result = remove_white_background(pil_to_qimage(product_photo()), tolerance=10)
    assert alpha_at(result, 10, 10) == 0  # фон
    assert alpha_at(result, 450, 450) == 255  # біле всередині кільця
    assert alpha_at(result, 450, 300) == 255  # біле між кільцем і биркою теж усередині
    assert alpha_at(result, 450, 150 + 20) == 255  # сам товар
    assert alpha_at(result, 450, 880) == 255  # сіра смуга не біла при чутливості 10


def test_tolerance_takes_light_grey():
    result = remove_white_background(pil_to_qimage(product_photo()), tolerance=20)
    assert alpha_at(result, 450, 880) == 0  # 240 ≥ 255-20 — теж фон


def test_thin_outline_is_not_leaked_through():
    img = Image.new("RGB", (1200, 1200), (255, 255, 255))
    ImageDraw.Draw(img).rectangle((300, 300, 900, 900), outline=(0, 0, 0), width=2)  # тонкий контур
    mask = background_mask(img, 10)
    assert mask.getpixel((10, 10)) == 255
    assert mask.getpixel((600, 600)) == 0  # середина за контуром — не фон


def test_existing_transparency_kept():
    img = product_photo(300).convert("RGBA")
    img.putpixel((150, 150), (0, 0, 0, 0))
    result = qimage_to_pil(remove_white_background(pil_to_qimage(img), 10))
    assert result.getpixel((150, 150))[3] == 0


def test_render_photo_without_white(workspace, tmp_path):
    c = workspace.create_category("Кабель")
    path = tmp_path / "кабель.png"
    product_photo(400).save(path)
    ref = workspace.add_category_asset(c.id, path)
    photo = PhotoElement(x=0, y=0, width=400, height=400, placeholder=ref, remove_white=True,
                         white_tolerance=20)
    template = Template(width=400, height=400, background=Background(color="#1E5BFF"), elements=[photo])
    image = render_template(template, RenderContext(workspace, c.id))
    assert image.pixelColor(5, 5) == QColor("#1E5BFF")  # крізь фото видно фон картки
    photo.remove_white = False
    image = render_template(template, RenderContext(workspace, c.id))
    assert image.pixelColor(5, 5) == QColor("#FFFFFF")


def test_defaults_for_old_templates():
    t = ser.template_from_dict({"elements": [{"type": "photo"}]})
    assert t.elements[0].remove_white is False and t.elements[0].white_tolerance == 20
