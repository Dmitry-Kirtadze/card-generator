"""Прибирання білого фону з фото товару.

Прозорим стає лише білий фон, з'єднаний із краєм картинки: білі деталі
всередині товару (бирка, наклейка, білий провід усередині бухти) лишаються.

Пошук з'єднаної області — морфологічна реконструкція (розширення маски
в межах «білих» пікселів, поки вона росте). Щоб це було швидко, основна
робота йде на зменшеній копії (а там — від ще меншої до більшої, _connected),
а край уточнюється на повному розмірі.
"""
from __future__ import annotations

from PIL import Image, ImageChops, ImageFilter
from PySide6.QtGui import QImage

WORK_SIDE = 320  # розмір зменшеної копії для пошуку фону
EDGE_PASSES = 4  # уточнення краю на повному розмірі
COARSE_SIDE = 80  # найменший рівень пошуку в _connected


def qimage_to_pil(image: QImage) -> Image.Image:
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombuffer("RGBA", (image.width(), image.height()), bytes(image.constBits()),
                            "raw", "RGBA", image.bytesPerLine(), 1).copy()


def pil_to_qimage(image: Image.Image) -> QImage:
    data = image.convert("RGBA").tobytes()
    return QImage(data, image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888).copy()


def white_mask(rgb: Image.Image, tolerance: int) -> Image.Image:
    """255 там, де всі три канали не темніші за 255 - tolerance."""
    threshold = 255 - max(1, min(80, tolerance))
    channels = [c.point(lambda v: 255 if v >= threshold else 0) for c in rgb.split()]
    return ImageChops.multiply(ImageChops.multiply(channels[0], channels[1]), channels[2])


def _grow(seed: Image.Image, allowed: Image.Image, limit: int | None = None) -> Image.Image:
    """Розширювати seed у межах allowed, доки росте (або limit кроків)."""
    steps = 0
    while limit is None or steps < limit:
        grown = ImageChops.multiply(seed.filter(ImageFilter.MaxFilter(3)), allowed)
        steps += 1
        if ImageChops.difference(grown, seed).getbbox() is None:
            return grown
        seed = grown
    return seed


def _border_seed(mask: Image.Image) -> Image.Image:
    """Білі пікселі на краю картинки — звідти починається фон."""
    w, h = mask.size
    border = Image.new("L", (w, h), 0)
    frame = Image.new("L", (w, h), 255)
    frame.paste(0, (1, 1, w - 1, h - 1))
    border.paste(mask, mask=frame)
    return border


def _shrink(mask: Image.Image, scale: float) -> Image.Image:
    """Зменшена маска: клітинка «біла», лише якщо біла повністю — тонкі контури товару не губляться."""
    w, h = mask.size
    size = (max(1, round(w / scale)), max(1, round(h / scale)))
    return mask.resize(size, Image.BOX).point(lambda v: 255 if v >= 254 else 0)


def _connected(mask: Image.Image) -> Image.Image:
    """Біла область, з'єднана з краєм (точно).

    Спершу шукаємо на копії до COARSE_SIDE px: знайдене там гарантовано належить фону,
    тож на поточному рівні лишається дорости від нього кілька кроків, а не через усю картинку.
    """
    w, h = mask.size
    seed = _border_seed(mask)
    if max(w, h) > COARSE_SIDE:
        coarse = _connected(_shrink(mask, max(w, h) / COARSE_SIDE))
        seed = ImageChops.lighter(seed, ImageChops.multiply(coarse.resize((w, h), Image.NEAREST), mask))
    return _grow(seed, mask)


def background_mask(image: Image.Image, tolerance: int) -> Image.Image:
    """Маска фону (255 — фон) повного розміру."""
    rgb = image.convert("RGB")
    full = white_mask(rgb, tolerance)
    w, h = full.size
    scale = max(w, h) / WORK_SIDE
    if scale > 1:
        found = _connected(_shrink(full, scale))
        seed = ImageChops.multiply(found.resize((w, h), Image.NEAREST), full)
        seed = ImageChops.lighter(seed, _border_seed(full))
        return _grow(seed, full, limit=round(scale) + EDGE_PASSES)
    return _connected(full)


def remove_white_background(image: QImage, tolerance: int = 20) -> QImage:
    pil = qimage_to_pil(image)
    background = background_mask(pil, tolerance).filter(ImageFilter.GaussianBlur(0.8))
    alpha = ImageChops.multiply(pil.getchannel("A"), ImageChops.invert(background))
    pil.putalpha(alpha)
    return pil_to_qimage(pil)
