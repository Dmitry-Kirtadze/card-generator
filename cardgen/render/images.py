"""Завантаження растрових і SVG-зображень з кешем."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, QSizeF, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter
from PySide6.QtSvg import QSvgRenderer

from .background import remove_white_background


# Декодовані растри й фото без білого фону — спільні для всіх ImageCache (кожна картка
# товару має свій RenderContext), з обмеженням пам'яті. Ключ містить час зміни файлу.
_RASTER: OrderedDict[tuple, QImage | None] = OrderedDict()
_NO_WHITE: OrderedDict[tuple, QImage | None] = OrderedDict()
_SIZES: dict[tuple, QSize | None] = {}
CACHE_BYTES = 256 * 1024 * 1024  # на кожен із двох кешів
MIN_BUCKET = 256


def processing_side(natural_side: int, drawn_side: float | None) -> int:
    """Розмір, у якому декодувати/обробляти зображення: з запасом під розмір на екрані,
    не більше оригіналу. Розміри «сходинками» (256, 512, 1024…), щоб невелика зміна
    масштабу не вимагала нової обробки.
    """
    if not drawn_side:
        return natural_side
    side = MIN_BUCKET
    while side < drawn_side * 1.5 and side < natural_side:
        side *= 2
    return min(side, natural_side)


def load_scaled(path: Path, side: int | None = None) -> QImage | None:
    """Декодує файл, одразу зменшуючи до side (JPEG при цьому декодується в рази швидше)."""
    reader = QImageReader(str(path))
    size = reader.size()
    if side and size.isValid() and max(size.width(), size.height()) > side:
        reader.setScaledSize(size.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    return None if image.isNull() else image


def _remember(cache: OrderedDict, key: tuple, image: QImage | None) -> None:
    cache[key] = image
    total = sum(i.sizeInBytes() for i in cache.values() if i is not None)
    while total > CACHE_BYTES and len(cache) > 1:
        _, old = cache.popitem(last=False)
        total -= old.sizeInBytes() if old is not None else 0


def _cached(cache: OrderedDict, key: tuple):
    if key in cache:
        cache.move_to_end(key)
        return True, cache[key]
    return False, None


class ImageCache:
    """Доступ до зображень з кешем; файл перечитується, якщо змінився час модифікації."""

    def __init__(self) -> None:
        self._svg: dict[Path, tuple[float, QSvgRenderer | None]] = {}

    def without_white(self, path: Path, tolerance: int, drawn_side: float | None = None) -> QImage | None:
        """Растрове фото з прозорим білим фоном.

        drawn_side — більша сторона фото на екрані/картці в пікселях: дрібне (мініатюри, стрічка
        перегляду) обробляється у зменшеному вигляді — це в десятки разів швидше.
        """
        natural = self.natural_size(path)
        if natural is None:
            return None
        side = processing_side(round(max(natural.width(), natural.height())), drawn_side)
        key = (path, _mtime(path), tolerance, side)
        found, image = _cached(_NO_WHITE, key)
        if not found:
            source = self.raster(path, drawn_side)
            image = remove_white_background(source, tolerance) if source is not None else None
            _remember(_NO_WHITE, key, image)
        return image

    def raster(self, path: Path, drawn_side: float | None = None) -> QImage | None:
        """Растр; з drawn_side — зменшений під розмір на екрані (див. processing_side)."""
        natural = self.natural_size(path)
        if natural is None:
            return None
        side = processing_side(round(max(natural.width(), natural.height())), drawn_side)
        key = (path, _mtime(path), side)
        found, image = _cached(_RASTER, key)
        if not found:
            image = load_scaled(path, side)
            _remember(_RASTER, key, image)
        return image

    def svg(self, path: Path) -> QSvgRenderer | None:
        mtime = _mtime(path)
        if mtime is None:
            return None
        cached = self._svg.get(path)
        if cached is None or cached[0] != mtime:
            renderer = QSvgRenderer(str(path))
            cached = (mtime, renderer if renderer.isValid() else None)
            self._svg[path] = cached
        return cached[1]

    def natural_size(self, path: Path) -> QSizeF | None:
        if path.suffix.lower() == ".svg":
            renderer = self.svg(path)
            return QSizeF(renderer.defaultSize()) if renderer else None
        mtime = _mtime(path)
        if mtime is None:
            return None
        key = (path, mtime)
        if key not in _SIZES:  # лише заголовок файлу, без декодування
            size = QImageReader(str(path)).size()
            _SIZES[key] = size if size.isValid() and not size.isEmpty() else None
        size = _SIZES[key]
        return QSizeF(size) if size is not None else None


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def fit_rect(natural: QSizeF, frame: QRectF, mode: str) -> QRectF:
    """Прямокутник зображення в рамці: contain — вписати, cover — заповнити, stretch — розтягнути."""
    if mode == "stretch" or natural.isEmpty():
        return QRectF(frame)
    sx = frame.width() / natural.width()
    sy = frame.height() / natural.height()
    s = min(sx, sy) if mode == "contain" else max(sx, sy)
    w, h = natural.width() * s, natural.height() * s
    return QRectF(frame.center().x() - w / 2, frame.center().y() - h / 2, w, h)


def draw_file(painter: QPainter, cache: ImageCache, path: Path, target: QRectF,
              tint: QColor | None = None) -> bool:
    """Малює файл у target. З tint — перефарбовує непрозорі пікселі (для іконок)."""
    is_svg = path.suffix.lower() == ".svg"
    if is_svg:
        renderer = cache.svg(path)
        if renderer is None:
            return False
    else:
        t = painter.worldTransform()
        device = (t.m11() ** 2 + t.m12() ** 2) ** 0.5  # пікселів пристрою на одиницю картки
        image = cache.raster(path, max(target.width(), target.height()) * device)
        if image is None:
            return False

    if tint is None:
        if is_svg:
            renderer.render(painter, target)
        else:
            painter.drawImage(target, image)
        return True

    # Перефарбування через проміжне зображення в роздільності пристрою.
    t = painter.worldTransform()
    scale = max((t.m11() ** 2 + t.m12() ** 2) ** 0.5, 1.0)
    w = max(1, round(target.width() * scale))
    h = max(1, round(target.height() * scale))
    layer = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    layer.fill(Qt.GlobalColor.transparent)
    lp = QPainter(layer)
    lp.setRenderHint(QPainter.RenderHint.Antialiasing)
    lp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if is_svg:
        renderer.render(lp, QRectF(0, 0, w, h))
    else:
        lp.drawImage(QRectF(0, 0, w, h), image)
    lp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    lp.fillRect(QRectF(0, 0, w, h), tint)
    lp.end()
    painter.drawImage(target, layer)
    return True
