"""Розмита тінь під фігурою."""
from __future__ import annotations

from collections import OrderedDict

from PIL import Image, ImageFilter
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath

from ..model import Shadow
from .colors import qcolor

_CACHE: OrderedDict[tuple, QImage] = OrderedDict()
_CACHE_LIMIT = 64


def shadow_margin(shadow: Shadow) -> float:
    if not shadow.enabled:
        return 0.0
    return shadow.blur * 2 + max(abs(shadow.offset_x), abs(shadow.offset_y))


def _mask(path: QPainterPath, pad: int, w: int, h: int) -> QImage:
    mask = QImage(w, h, QImage.Format.Format_Grayscale8)
    mask.fill(0)
    p = QPainter(mask)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(pad, pad)
    p.fillPath(path, QColor(255, 255, 255))
    p.end()
    return mask


def _blur(mask: QImage, radius: float) -> QImage:
    if radius <= 0:
        return mask
    w, h, bpl = mask.width(), mask.height(), mask.bytesPerLine()
    pil = Image.frombuffer("L", (w, h), bytes(mask.constBits()), "raw", "L", bpl, 1)
    pil = pil.filter(ImageFilter.GaussianBlur(radius))
    data = pil.tobytes()
    return QImage(data, w, h, w, QImage.Format.Format_Grayscale8).copy()


def shadow_image(path: QPainterPath, shadow: Shadow) -> tuple[QImage, QPointF]:
    """Зображення тіні в пікселях полотна і зміщення його лівого верхнього кута."""
    bounds = path.boundingRect()
    pad = int(shadow.blur * 2) + 2
    w = int(bounds.right()) + pad * 2 + 1
    h = int(bounds.bottom()) + pad * 2 + 1
    shape = tuple((e.x, e.y, e.type.value) for e in (path.elementAt(i) for i in range(path.elementCount())))
    key = (shape, w, h, shadow.blur, shadow.color)
    image = _CACHE.get(key)
    if image is None:
        alpha = _blur(_mask(path, pad, w, h), shadow.blur / 2)
        image = QImage(w, h, QImage.Format.Format_ARGB32)
        color = qcolor(shadow.color, "#00000055")
        image.fill(QColor(color.red(), color.green(), color.blue()))
        image.setAlphaChannel(alpha)
        _CACHE[key] = image
        if len(_CACHE) > _CACHE_LIMIT:
            _CACHE.popitem(last=False)
    else:
        _CACHE.move_to_end(key)
    return image, QPointF(shadow.offset_x - pad, shadow.offset_y - pad)


def draw_shadow(painter: QPainter, path: QPainterPath, shadow: Shadow) -> None:
    if not shadow.enabled:
        return
    image, offset = shadow_image(path, shadow)
    painter.save()
    painter.setOpacity(painter.opacity() * qcolor(shadow.color, "#00000055").alphaF())
    painter.drawImage(QRectF(offset.x(), offset.y(), image.width(), image.height()), image)
    painter.restore()
