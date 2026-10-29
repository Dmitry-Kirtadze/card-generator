"""Єдиний рушій відмальовування: його використовують і редактор, і експорт.

paint_element_local малює блок у його власних координатах (0, 0, ширина, висота) —
так його викликає елемент полотна редактора, який сам застосовує позицію й поворот.
paint_element додає позицію, поворот і прозорість — так малюється готова картка.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
)

from ..model import (
    Element,
    GroupElement,
    IconElement,
    Paint,
    PhotoElement,
    ShapeElement,
    TableElement,
    Template,
    TextElement,
)
from ..model.table_ops import positions
from ..storage import StorageError, Workspace
from .colors import qcolor
from .effects import draw_shadow
from .images import ImageCache, draw_file, fit_rect
from .text import draw_text, layout_text

PLACEHOLDER_FILL = QColor("#D9DEE7")
PLACEHOLDER_TEXT = QColor("#7A8597")


@dataclass
class RenderContext:
    workspace: Workspace
    category_id: str | None
    images: ImageCache = field(default_factory=ImageCache)
    # блоки, текст яких не вмістився навіть з мінімальним шрифтом
    overflow: set[str] = field(default_factory=set)
    # папка фото з таблиці даних шаблону (посилання "data:<файл>")
    data_images: Path | None = None
    # сірі заглушки «Фото»/«Іконка» без зображення: так — у редакторі, ні — на готових картках
    placeholders: bool = True

    def resolve(self, ref: str):
        if not ref:
            return None
        if ref.startswith("data:"):
            name = Path(ref[len("data:"):]).name  # лише ім'я файлу, без шляхів
            return self.data_images / name if self.data_images and name else None
        try:
            return self.workspace.resolve_asset(ref, self.category_id)
        except StorageError:
            return None


def setup_painter(painter: QPainter) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)


# --- Заливки ---------------------------------------------------------------

def make_brush(paint: Paint, rect: QRectF) -> QBrush:
    if paint.kind == "none":
        return QBrush(Qt.BrushStyle.NoBrush)
    if paint.kind == "linear":
        a = math.radians(paint.angle)
        dx, dy = math.cos(a), math.sin(a)
        half = (abs(rect.width() * dx) + abs(rect.height() * dy)) / 2
        c = rect.center()
        gradient = QLinearGradient(QPointF(c.x() - dx * half, c.y() - dy * half),
                                   QPointF(c.x() + dx * half, c.y() + dy * half))
        gradient.setColorAt(0, qcolor(paint.color))
        gradient.setColorAt(1, qcolor(paint.color2))
        return QBrush(gradient)
    return QBrush(qcolor(paint.color))


def rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    r = max(0.0, min(radius, rect.width() / 2, rect.height() / 2))
    if r > 0:
        path.addRoundedRect(rect, r, r)
    else:
        path.addRect(rect)
    return path


# --- Фон -------------------------------------------------------------------

def paint_background(painter: QPainter, template: Template, ctx: RenderContext) -> None:
    canvas = QRectF(0, 0, template.width, template.height)
    bg = template.background
    painter.fillRect(canvas, qcolor(bg.color, "#FFFFFF"))
    path = ctx.resolve(bg.asset)
    if path is None:
        return
    natural = ctx.images.natural_size(path)
    if natural is None:
        return
    target = fit_rect(natural, canvas, bg.fit)
    c = target.center()
    w, h = target.width() * bg.scale, target.height() * bg.scale
    target = QRectF(c.x() - w / 2 + bg.offset_x, c.y() - h / 2 + bg.offset_y, w, h)
    painter.save()
    painter.setClipRect(canvas)
    draw_file(painter, ctx.images, path, target)
    painter.restore()


# --- Блоки -----------------------------------------------------------------

def paint_element(painter: QPainter, element: Element, ctx: RenderContext) -> None:
    if not element.visible:
        return
    if isinstance(element, GroupElement):
        painter.save()
        painter.setOpacity(painter.opacity() * element.opacity)
        for child in element.children:
            paint_element(painter, child, ctx)
        painter.restore()
        return
    painter.save()
    painter.translate(element.x, element.y)
    if element.rotation:
        painter.translate(element.width / 2, element.height / 2)
        painter.rotate(element.rotation)
        painter.translate(-element.width / 2, -element.height / 2)
    painter.setOpacity(painter.opacity() * element.opacity)
    paint_element_local(painter, element, ctx)
    painter.restore()


def paint_element_local(painter: QPainter, element: Element, ctx: RenderContext) -> None:
    rect = QRectF(0, 0, element.width, element.height)
    if isinstance(element, ShapeElement):
        _paint_shape(painter, element, rect)
    elif isinstance(element, TextElement):
        _paint_text(painter, element, rect, ctx)
    elif isinstance(element, IconElement):
        _paint_icon(painter, element, rect, ctx)
    elif isinstance(element, PhotoElement):
        _paint_photo(painter, element, rect, ctx)
    elif isinstance(element, TableElement):
        _paint_table(painter, element, rect, ctx)


def bound_text(text: str, binding) -> str:
    """Текст блоку/клітинки з префіксом і суфіксом заповнюваного поля.

    Без прикладу тексту в редакторі показується назва стовпця: «[Переріз] AWG».
    """
    if binding.enabled:
        if not text and binding.column.strip():
            text = f"[{binding.column.strip()}]"
        return f"{binding.prefix}{text}{binding.suffix}"
    return text


def display_text(element: TextElement) -> str:
    return bound_text(element.text, element.binding)


def cell_overflow_id(table_id: str, row: int, col: int) -> str:
    return f"{table_id}:{row}:{col}"


def _paint_shape(painter: QPainter, element: ShapeElement, rect: QRectF) -> None:
    if element.shape == "line":
        y = rect.height() / 2
        pen = QPen(qcolor(element.stroke.color), max(element.stroke.width, 1.0))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap if element.corner_radius > 0 else Qt.PenCapStyle.FlatCap)
        path = QPainterPath(QPointF(0, y))
        path.lineTo(rect.width(), y)
        if element.shadow.enabled:
            draw_shadow(painter, QPainterPathStroker(pen).createStroke(path), element.shadow)
        painter.setPen(pen)
        painter.drawPath(path)
        return

    path = QPainterPath()
    if element.shape == "ellipse":
        path.addEllipse(rect)
    else:
        path = rounded_path(rect, element.corner_radius)
    draw_shadow(painter, path, element.shadow)
    painter.fillPath(path, make_brush(element.fill, rect))
    if element.stroke.width > 0:
        pen = QPen(qcolor(element.stroke.color), element.stroke.width)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.strokePath(path, pen)


def _paint_text(painter: QPainter, element: TextElement, rect: QRectF, ctx: RenderContext) -> None:
    layout = layout_text(display_text(element), element.style, rect.width(), rect.height(),
                         wrap=element.wrap, auto_shrink=element.auto_shrink,
                         min_font_size=element.min_font_size)
    if layout.overflow:
        ctx.overflow.add(element.id)
    else:
        ctx.overflow.discard(element.id)
    draw_text(painter, rect, layout, element.style)


def _paint_icon(painter: QPainter, element: IconElement, rect: QRectF, ctx: RenderContext) -> None:
    path = ctx.resolve(element.asset)
    natural = ctx.images.natural_size(path) if path else None
    if natural is None:
        if ctx.placeholders:
            _placeholder(painter, rect, "Іконка", 0)
        return
    tint = qcolor(element.tint) if element.tint else None
    draw_file(painter, ctx.images, path, fit_rect(natural, rect, "contain"), tint)


def _paint_photo(painter: QPainter, element: PhotoElement, rect: QRectF, ctx: RenderContext) -> None:
    frame = rounded_path(rect, element.corner_radius)
    path = ctx.resolve(element.placeholder)
    natural = ctx.images.natural_size(path) if path else None
    if natural is None and not ctx.placeholders:
        return  # на готовій картці товару без фото — порожньо
    cut_out = element.remove_white and natural is not None and path.suffix.lower() != ".svg"
    if not cut_out:  # тінь рамки; у вирізаного товару рамки немає — і тіні теж
        draw_shadow(painter, frame, element.shadow)
    if natural is None:
        _placeholder(painter, rect, "Фото", element.corner_radius)
        return
    target = fit_rect(natural, rect, element.fit)
    c = target.center()
    w, h = target.width() * element.content_scale, target.height() * element.content_scale
    target = QRectF(c.x() - w / 2 + element.content_offset_x,
                    c.y() - h / 2 + element.content_offset_y, w, h)
    painter.save()
    painter.setClipPath(frame, Qt.ClipOperation.IntersectClip)
    image = ctx.images.without_white(path, element.white_tolerance) if cut_out else None
    if image is not None:
        painter.drawImage(target, image)
    else:
        draw_file(painter, ctx.images, path, target)
    painter.restore()


def _paint_table(painter: QPainter, table: TableElement, rect: QRectF, ctx: RenderContext) -> None:
    xs = positions(table.col_widths, rect.width())
    ys = positions(table.row_heights, rect.height())
    outline = rounded_path(rect, table.corner_radius)

    painter.save()
    painter.setClipPath(outline, Qt.ClipOperation.IntersectClip)
    painter.fillPath(outline, make_brush(table.background, rect))
    any_overflow = False
    for r in range(table.rows):
        row_rect = QRectF(0, ys[r], rect.width(), ys[r + 1] - ys[r])
        if r % 2 == 1 and table.stripe.kind != "none":
            painter.fillRect(row_rect, make_brush(table.stripe, row_rect))
        for c in range(table.cols):
            cell = table.cells[r][c]
            cell_rect = QRectF(xs[c], ys[r], xs[c + 1] - xs[c], ys[r + 1] - ys[r])
            if cell.background.kind != "none":
                painter.fillRect(cell_rect, make_brush(cell.background, cell_rect))
            text = bound_text(cell.text, cell.binding)
            if not text:
                continue
            inner = cell_rect.adjusted(cell.padding, cell.padding, -cell.padding, -cell.padding)
            if inner.width() <= 0 or inner.height() <= 0:
                continue
            layout = layout_text(text, cell.style, inner.width(), inner.height(), wrap=cell.wrap,
                                 auto_shrink=cell.auto_shrink, min_font_size=cell.min_font_size)
            key = cell_overflow_id(table.id, r, c)
            if layout.overflow:
                ctx.overflow.add(key)
                any_overflow = True
            else:
                ctx.overflow.discard(key)
            painter.save()
            painter.setClipRect(cell_rect, Qt.ClipOperation.IntersectClip)
            draw_text(painter, inner, layout, cell.style)
            painter.restore()
    painter.restore()
    if any_overflow:
        ctx.overflow.add(table.id)
    else:
        ctx.overflow.discard(table.id)

    if table.border.width <= 0:
        return
    pen = QPen(qcolor(table.border.color, "#DDDDDD"), table.border.width)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if table.border_inner_h:
        for y in ys[1:-1]:
            painter.drawLine(QPointF(0, y), QPointF(rect.width(), y))
    if table.border_inner_v:
        for x in xs[1:-1]:
            painter.drawLine(QPointF(x, 0), QPointF(x, rect.height()))
    if table.border_outer:
        painter.drawPath(outline)


def _placeholder(painter: QPainter, rect: QRectF, label: str, radius: float) -> None:
    painter.fillPath(rounded_path(rect, radius), PLACEHOLDER_FILL)
    font = painter.font()
    font.setPixelSize(max(10, int(min(rect.width(), rect.height()) / 6)))
    painter.setFont(font)
    painter.setPen(PLACEHOLDER_TEXT)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)


# --- Уся картка ------------------------------------------------------------

def render_template(template: Template, ctx: RenderContext, scale: float = 1.0) -> QImage:
    w = max(1, round(template.width * scale))
    h = max(1, round(template.height * scale))
    image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#FFFFFF"))
    painter = QPainter(image)
    setup_painter(painter)
    painter.scale(scale, scale)
    paint_background(painter, template, ctx)
    for element in template.elements:
        paint_element(painter, element, ctx)
    painter.end()
    return image
