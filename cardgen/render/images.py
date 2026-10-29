"""Завантаження растрових і SVG-зображень з кешем."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from .background import remove_white_background


class ImageCache:
    """Кеш за шляхом; файл перечитується, якщо змінився час модифікації."""

    def __init__(self) -> None:
        self._raster: dict[Path, tuple[float, QImage | None]] = {}
        self._svg: dict[Path, tuple[float, QSvgRenderer | None]] = {}
        self._no_white: dict[tuple[Path, int], tuple[float, QImage | None]] = {}

    def without_white(self, path: Path, tolerance: int) -> QImage | None:
        """Растрове фото з прозорим білим фоном (обчислюється один раз на файл)."""
        image = self.raster(path)
        if image is None:
            return None
        mtime = _mtime(path)
        key = (path, tolerance)
        cached = self._no_white.get(key)
        if cached is None or cached[0] != mtime:
            cached = (mtime, remove_white_background(image, tolerance))
            self._no_white[key] = cached
        return cached[1]

    def raster(self, path: Path) -> QImage | None:
        mtime = _mtime(path)
        if mtime is None:
            return None
        cached = self._raster.get(path)
        if cached is None or cached[0] != mtime:
            image = QImage(str(path))
            cached = (mtime, None if image.isNull() else image)
            self._raster[path] = cached
        return cached[1]

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
        image = self.raster(path)
        return QSizeF(image.size()) if image else None


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
        image = cache.raster(path)
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
