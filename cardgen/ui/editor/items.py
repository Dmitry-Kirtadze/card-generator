"""Елементи полотна редактора.

Кожен блок шаблону — ElementItem. Малює його той самий рушій, що й експорт
(paint_element_local), а позицію й поворот задає сам QGraphicsItem —
у точній відповідності до paint_element.

Групи не мають власного елемента на полотні: група — це блоки, які
виділяються й рухаються разом (див. EditorPage).
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsScene,
    QStyleOptionGraphicsItem,
)

from ...model import Element, IconElement, PhotoElement, ShapeElement, TableElement, Template
from ...model.ops import leaves
from ...model.table_ops import move_divider, positions
from ...render import RenderContext, paint_background, paint_element_local
from ...render.effects import shadow_margin
from .snapping import snap_angle, snap_rect, snap_value

HANDLE_PX = 10  # розмір маркера на екрані
ROTATE_OFFSET_PX = 28  # відстань маркера повороту над блоком
SNAP_PX = 6  # поріг прилипання на екрані
DIVIDER_PX = 5  # зона захоплення межі стовпця/рядка таблиці
CELL_HIGHLIGHT = QColor(30, 91, 255, 45)
MIN_SIZE = 4.0
SELECTION_COLOR = QColor("#1E5BFF")
OVERFLOW_COLOR = QColor("#E5484D")
GUIDE_COLOR = QColor("#FF2E9A")
GRID_COLOR = QColor(30, 91, 255, 40)

# маркер -> напрямок по x та y (-1 ліво/верх, 1 право/низ, 0 без змін)
HANDLES = {
    "nw": (-1, -1), "n": (0, -1), "ne": (1, -1),
    "w": (-1, 0), "e": (1, 0),
    "sw": (-1, 1), "s": (0, 1), "se": (1, 1),
}
CURSORS = {
    "nw": Qt.CursorShape.SizeFDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor, "sw": Qt.CursorShape.SizeBDiagCursor,
    "n": Qt.CursorShape.SizeVerCursor, "s": Qt.CursorShape.SizeVerCursor,
    "w": Qt.CursorShape.SizeHorCursor, "e": Qt.CursorShape.SizeHorCursor,
    "rotate": Qt.CursorShape.CrossCursor,
}


def view_scale(item_or_scene) -> float:
    scene = item_or_scene if isinstance(item_or_scene, QGraphicsScene) else item_or_scene.scene()
    if scene is None or not scene.views():
        return 1.0
    t = scene.views()[0].transform()
    return max((t.m11() ** 2 + t.m12() ** 2) ** 0.5, 1e-3)


def keeps_ratio(element: Element) -> bool:
    """Фото й іконки за кути масштабуються пропорційно (як у Canva)."""
    return isinstance(element, (IconElement, PhotoElement))


def no_snap_modifier() -> bool:
    """Alt тимчасово вимикає прилипання."""
    return bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier)


class BackgroundItem(QGraphicsItem):
    """Полотно з фоном. Не реагує на мишу — не заважає працювати з блоками."""

    def __init__(self, template: Template, ctx: RenderContext):
        super().__init__()
        self.template = template
        self.ctx = ctx
        self.setZValue(-1_000_000)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.template.width, self.template.height)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        paint_background(painter, self.template, self.ctx)

    def sync(self) -> None:
        self.prepareGeometryChange()
        self.update()


class ElementItem(QGraphicsObject):
    moved = Signal(str)  # під час перетягування / зміни розміру / повороту
    committed = Signal(str, str)  # id, назва дії — дію завершено
    doubleClicked = Signal(str)
    cellClicked = Signal(str, int, int, bool)  # id таблиці, рядок, стовпець, додати до виділених

    def __init__(self, element: Element, ctx: RenderContext):
        super().__init__()
        self.element = element
        self.ctx = ctx
        self._resize: tuple[str, QRectF, QTransform] | None = None
        self._rotating = False
        self._drag: tuple[QPointF, dict[ElementItem, QPointF], QRectF] | None = None
        self._dragged = False
        self._syncing = False
        self._divider: tuple[str, int, list[float]] | None = None
        self.selected_cells: set[tuple[int, int]] = set()  # для таблиці
        # успадковане від груп, у яких лежить блок
        self.parent_hidden = False
        self.parent_locked = False
        self.parent_opacity = 1.0
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.setAcceptHoverEvents(True)
        self.sync_from_model()

    def editor_scene(self) -> EditorScene | None:
        scene = self.scene()
        return scene if isinstance(scene, EditorScene) else None

    # --- Модель -> елемент --------------------------------------------------

    def sync_from_model(self) -> None:
        e = self.element
        self._syncing = True
        self.prepareGeometryChange()
        self.setPos(e.x, e.y)
        self.setTransformOriginPoint(e.width / 2, e.height / 2)
        self.setRotation(e.rotation)
        self.setOpacity(e.opacity * self.parent_opacity)
        self.setVisible(e.visible and not self.parent_hidden)
        # «рухомий» потрібен, щоб Qt зберігав множинне виділення при натисканні;
        # саме перетягування робимо власним кодом (mouseMoveEvent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not self.locked())
        self._syncing = False
        self.update()

    def locked(self) -> bool:
        return self.element.locked or self.parent_locked

    def local_rect(self) -> QRectF:
        return QRectF(0, 0, self.element.width, self.element.height)

    def scene_rect(self) -> QRectF:
        """Рамка блоку на полотні з урахуванням повороту."""
        return self.mapToScene(self.local_rect()).boundingRect()

    # --- Геометрія ----------------------------------------------------------

    def _handle_size(self) -> float:
        return HANDLE_PX / view_scale(self)

    def boundingRect(self) -> QRectF:
        s = view_scale(self)
        m = (HANDLE_PX + 2) / s
        if hasattr(self.element, "shadow"):
            m = max(m, shadow_margin(self.element.shadow))
        if isinstance(self.element, ShapeElement) and self.element.shape == "line":
            m = max(m, self.element.stroke.width)
        rect = self.local_rect().adjusted(-m, -m, m, m)
        top = -(ROTATE_OFFSET_PX + HANDLE_PX) / s
        if rect.top() > top:
            rect.setTop(top)
        return rect

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.local_rect())
        if self.isSelected():
            for rect in self._handle_rects().values():
                path.addRect(rect)
        return path

    def _shows_handles(self) -> bool:
        """Маркери — лише коли це єдиний вибраний блок."""
        scene = self.scene()
        return (self.isSelected() and not self.locked() and scene is not None
                and len(scene.selectedItems()) == 1)

    def _handle_names(self) -> list[str]:
        if not self._shows_handles():
            return []
        if isinstance(self.element, ShapeElement) and self.element.shape == "line":
            return ["w", "e", "rotate"]
        return [*HANDLES, "rotate"]

    def _handle_rects(self) -> dict[str, QRectF]:
        s = self._handle_size()
        r = self.local_rect()
        result = {}
        for name in self._handle_names():
            if name == "rotate":
                cx, cy = r.center().x(), -ROTATE_OFFSET_PX / view_scale(self)
            else:
                hx, hy = HANDLES[name]
                cx = r.center().x() + hx * r.width() / 2
                cy = r.center().y() + hy * r.height() / 2
            result[name] = QRectF(cx - s / 2, cy - s / 2, s, s)
        return result

    def handle_at(self, local: QPointF) -> str | None:
        for name, rect in self._handle_rects().items():
            if rect.adjusted(-2, -2, 2, 2).contains(local):
                return name
        return None

    # --- Таблиця ------------------------------------------------------------

    def divider_at(self, local: QPointF) -> tuple[str, int] | None:
        """Межа між стовпцями ("col", i) або рядками ("row", i) під курсором."""
        t = self.element
        if not isinstance(t, TableElement) or not self._shows_handles():
            return None
        if not self.local_rect().contains(local):
            return None
        threshold = DIVIDER_PX / view_scale(self)
        xs = positions(t.col_widths, t.width)
        for i, x in enumerate(xs[1:-1]):
            if abs(local.x() - x) <= threshold:
                return "col", i
        ys = positions(t.row_heights, t.height)
        for i, y in enumerate(ys[1:-1]):
            if abs(local.y() - y) <= threshold:
                return "row", i
        return None

    def cell_at(self, local: QPointF) -> tuple[int, int] | None:
        t = self.element
        if not isinstance(t, TableElement) or not self.local_rect().contains(local):
            return None
        xs = positions(t.col_widths, t.width)
        ys = positions(t.row_heights, t.height)
        col = next((i for i in range(t.cols) if local.x() <= xs[i + 1]), t.cols - 1)
        row = next((i for i in range(t.rows) if local.y() <= ys[i + 1]), t.rows - 1)
        return row, col

    def cell_rect(self, row: int, col: int) -> QRectF:
        t = self.element
        xs = positions(t.col_widths, t.width)
        ys = positions(t.row_heights, t.height)
        return QRectF(xs[col], ys[row], xs[col + 1] - xs[col], ys[row + 1] - ys[row])

    def begin_divider(self, axis: str, index: int) -> None:
        weights = self.element.col_widths if axis == "col" else self.element.row_heights
        self._divider = (axis, index, list(weights))

    def divider_to(self, scene_pos: QPointF) -> None:
        axis, index, weights = self._divider
        local = self.mapFromScene(scene_pos)
        t = self.element
        if axis == "col":
            t.col_widths = move_divider(weights, index, local.x(), t.width)
        else:
            t.row_heights = move_divider(weights, index, local.y(), t.height)
        self.update()
        self.moved.emit(t.id)

    # --- Малювання ----------------------------------------------------------

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None) -> None:
        paint_element_local(painter, self.element, self.ctx)
        scale = view_scale(self)
        if self.element.id in self.ctx.overflow:
            painter.setPen(QPen(OVERFLOW_COLOR, 2 / scale, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.local_rect())
        if self.isSelected() and isinstance(self.element, TableElement) and self.selected_cells:
            painter.setPen(QPen(SELECTION_COLOR, 2 / scale))
            painter.setBrush(CELL_HIGHLIGHT)
            for row, col in self.selected_cells:
                if row < self.element.rows and col < self.element.cols:
                    painter.drawRect(self.cell_rect(row, col))
        if self.isSelected():
            painter.setOpacity(1.0)
            style = Qt.PenStyle.DashLine if self.locked() else Qt.PenStyle.SolidLine
            painter.setPen(QPen(SELECTION_COLOR, 1.5 / scale, style))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.local_rect())
            handles = self._handle_rects()
            if "rotate" in handles:
                top_center = QPointF(self.local_rect().center().x(), 0)
                painter.drawLine(top_center, handles["rotate"].center())
            painter.setBrush(QBrush(QColor("#FFFFFF")))
            for name, rect in handles.items():
                if name == "rotate":
                    painter.drawEllipse(rect)
                else:
                    painter.drawRect(rect)

    # --- Миша ---------------------------------------------------------------

    def hoverMoveEvent(self, event) -> None:
        handle = self.handle_at(event.pos()) if self.isSelected() else None
        divider = self.divider_at(event.pos()) if not handle else None
        if handle:
            self.setCursor(CURSORS[handle])
        elif divider:
            self.setCursor(Qt.CursorShape.SplitHCursor if divider[0] == "col" else Qt.CursorShape.SplitVCursor)
        elif not self.locked():
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.unsetCursor()
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        handle = self.handle_at(event.pos()) if self.isSelected() else None
        if handle and event.button() == Qt.MouseButton.LeftButton:
            if handle == "rotate":
                self._rotating = True
            else:
                self.begin_resize(handle)
            event.accept()
            return
        divider = self.divider_at(event.pos()) if event.button() == Qt.MouseButton.LeftButton else None
        if divider:
            self.begin_divider(*divider)
            event.accept()
            return
        super().mousePressEvent(event)  # виділення (з Ctrl — додати до виділених)
        if event.button() == Qt.MouseButton.LeftButton and self.isSelected():
            cell = self.cell_at(event.pos())
            if cell is not None:
                add = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                self.cellClicked.emit(self.element.id, cell[0], cell[1], add)
            self.begin_drag(event.scenePos())

    def mouseMoveEvent(self, event) -> None:
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self._resize is not None:
            self.resize_to(event.scenePos(), keeps_ratio(self.element) != shift)
        elif self._divider is not None:
            self.divider_to(event.scenePos())
        elif self._rotating:
            self.rotate_to(event.scenePos(), step=15 if shift else None)
        elif self._drag is not None:
            self.drag_to(event.scenePos(), axis_lock=shift)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        action = None
        if self._resize is not None:
            action = "Розмір"
        elif self._divider is not None:
            action = "Ширина стовпця" if self._divider[0] == "col" else "Висота рядка"
        elif self._rotating:
            action = "Поворот"
        elif self._drag is not None and self._dragged:
            action = "Переміщення"
        self._resize = None
        self._divider = None
        self._rotating = False
        self._drag = None
        self._dragged = False
        if (scene := self.editor_scene()) is not None:
            scene.set_guides(None, None)
        if action:
            self.committed.emit(self.element.id, action)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self.doubleClicked.emit(self.element.id)
        super().mouseDoubleClickEvent(event)

    # --- Перетягування ------------------------------------------------------

    def begin_drag(self, scene_pos: QPointF) -> None:
        scene = self.editor_scene()
        selected = [i for i in (scene.selectedItems() if scene else [self])
                    if isinstance(i, ElementItem) and not i.locked()]
        if self.locked() or not selected:
            self._drag = None
            return
        union = QRectF()
        for item in selected:
            union = union.united(item.scene_rect())
        self._drag = (scene_pos, {item: item.pos() for item in selected}, union)
        self._dragged = False

    def drag_to(self, scene_pos: QPointF, axis_lock: bool = False) -> None:
        start, positions, union = self._drag
        delta = scene_pos - start
        if not self._dragged and abs(delta.x()) + abs(delta.y()) < 1 / view_scale(self):
            return
        self._dragged = True
        if axis_lock:
            if abs(delta.x()) >= abs(delta.y()):
                delta.setY(0)
            else:
                delta.setX(0)
        scene = self.editor_scene()
        if scene is not None and scene.snap_enabled and not no_snap_modifier():
            moved = union.translated(delta)
            xs, ys = scene.snap_targets({i.element.id for i in positions})
            sx, sy = snap_rect(moved.left(), moved.top(), moved.width(), moved.height(), xs, ys,
                               scene.snap_threshold(), scene.grid_step())
            if axis_lock and delta.y() == 0:
                sy.delta, sy.guide = 0.0, None
            if axis_lock and delta.x() == 0:
                sx.delta, sx.guide = 0.0, None
            delta += QPointF(sx.delta, sy.delta)
            scene.set_guides(sx.guide, sy.guide)
        for item, pos in positions.items():
            item.setPos(pos + delta)

    # --- Зміна розміру ------------------------------------------------------

    def begin_resize(self, handle: str) -> None:
        self._resize = (handle, self.local_rect(), self.sceneTransform())

    def resize_to(self, scene_pos: QPointF, keep_ratio: bool = False) -> None:
        handle, r0, transform = self._resize
        hx, hy = HANDLES[handle]
        inverse, _ = transform.inverted()
        p = inverse.map(scene_pos)
        left, top, right, bottom = r0.left(), r0.top(), r0.right(), r0.bottom()
        if hx < 0:
            left = min(p.x(), right - MIN_SIZE)
        elif hx > 0:
            right = max(p.x(), left + MIN_SIZE)
        if hy < 0:
            top = min(p.y(), bottom - MIN_SIZE)
        elif hy > 0:
            bottom = max(p.y(), top + MIN_SIZE)

        guides: list[float | None] = [None, None]
        scene = self.editor_scene()
        unrotated = abs(transform.m12()) < 1e-9 and abs(transform.m21()) < 1e-9
        if (scene is not None and scene.snap_enabled and not no_snap_modifier() and unrotated
                and not (keep_ratio and hx and hy)):
            # без повороту локальні координати = координати полотна мінус зсув
            ox, oy = transform.dx(), transform.dy()
            xs, ys = scene.snap_targets({self.element.id})
            thr, grid = scene.snap_threshold(), scene.grid_step()
            if hx:
                edge = left if hx < 0 else right
                s = snap_value(edge + ox, xs, thr, grid)
                if s.guide is not None:
                    edge += s.delta
                    guides[0] = s.guide
                    if hx < 0:
                        left = min(edge, right - MIN_SIZE)
                    else:
                        right = max(edge, left + MIN_SIZE)
            if hy:
                edge = top if hy < 0 else bottom
                s = snap_value(edge + oy, ys, thr, grid)
                if s.guide is not None:
                    edge += s.delta
                    guides[1] = s.guide
                    if hy < 0:
                        top = min(edge, bottom - MIN_SIZE)
                    else:
                        bottom = max(edge, top + MIN_SIZE)
            scene.set_guides(*guides)

        w, h = right - left, bottom - top
        if keep_ratio and hx and hy and r0.width() > 0 and r0.height() > 0:
            k = max(w / r0.width(), h / r0.height())
            w, h = r0.width() * k, r0.height() * k
            left = r0.right() - w if hx < 0 else r0.left()
            top = r0.bottom() - h if hy < 0 else r0.top()
        new_local = QRectF(left, top, w, h)
        # центр нового прямокутника лишається там, де він на екрані зараз;
        # поворот навколо центру, тож позиція = центр - половина розміру
        center = transform.map(new_local.center())
        e = self.element
        e.width, e.height = w, h
        e.x, e.y = center.x() - w / 2, center.y() - h / 2
        self.sync_from_model()
        self.moved.emit(e.id)

    # --- Поворот ------------------------------------------------------------

    def rotate_to(self, scene_pos: QPointF, step: float | None = None) -> None:
        center = self.mapToScene(self.local_rect().center())
        dx, dy = scene_pos.x() - center.x(), scene_pos.y() - center.y()
        if dx == 0 and dy == 0:
            return
        angle = math.degrees(math.atan2(dy, dx)) + 90
        self.element.rotation = snap_angle(angle, step)
        self.sync_from_model()
        self.moved.emit(self.element.id)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and not self._syncing:
            self.element.x, self.element.y = value.x(), value.y()
            self.moved.emit(self.element.id)
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.prepareGeometryChange()
        return super().itemChange(change, value)


class EditorScene(QGraphicsScene):
    """Сцена: полотно + блоки. Усе поза полотном затемнюється (в експорт не потрапляє)."""

    def __init__(self, template: Template, ctx: RenderContext, parent=None):
        super().__init__(parent)
        self.template = template
        self.ctx = ctx
        self.background = BackgroundItem(template, ctx)
        self.addItem(self.background)
        self.items_by_id: dict[str, ElementItem] = {}
        self.snap_enabled = True
        self.grid_enabled = False
        self.grid_size = 50.0
        self.guides: tuple[float | None, float | None] = (None, None)
        self.group_outlines: list[QRectF] = []
        self.update_scene_rect()

    def canvas_rect(self) -> QRectF:
        return QRectF(0, 0, self.template.width, self.template.height)

    def update_scene_rect(self) -> None:
        m = max(self.template.width, self.template.height) * 0.6
        self.setSceneRect(self.canvas_rect().adjusted(-m, -m, m, m))
        self.background.sync()

    # --- Блоки --------------------------------------------------------------

    def add_element_item(self, element: Element) -> ElementItem:
        item = ElementItem(element, self.ctx)
        self.addItem(item)
        self.items_by_id[element.id] = item
        return item

    def remove_element_item(self, element_id: str) -> None:
        item = self.items_by_id.pop(element_id, None)
        if item is not None:
            self.removeItem(item)

    def restack(self) -> None:
        """z-порядок = порядок блоків у шаблоні (з урахуванням груп)."""
        for z, element in enumerate(leaves(self.template.elements)):
            item = self.items_by_id.get(element.id)
            if item is not None:
                item.setZValue(z)

    # --- Прилипання ---------------------------------------------------------

    def snap_threshold(self) -> float:
        return SNAP_PX / view_scale(self)

    def grid_step(self) -> float:
        return self.grid_size if self.grid_enabled else 0.0

    def snap_targets(self, exclude: set[str]) -> tuple[list[float], list[float]]:
        """Лінії, до яких прилипаємо: краї й центр полотна та інших видимих блоків."""
        w, h = self.template.width, self.template.height
        xs, ys = [0.0, w / 2, float(w)], [0.0, h / 2, float(h)]
        for element_id, item in self.items_by_id.items():
            if element_id in exclude or not item.isVisible():
                continue
            r = item.scene_rect()
            xs += [r.left(), r.center().x(), r.right()]
            ys += [r.top(), r.center().y(), r.bottom()]
        return xs, ys

    def set_guides(self, x: float | None, y: float | None) -> None:
        if self.guides != (x, y):
            self.guides = (x, y)
            self.update()

    # --- Передній план: затемнення, сітка, підказки --------------------------

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        canvas = self.canvas_rect()
        scale = view_scale(self)
        if self.grid_enabled and self.grid_size * scale >= 4:
            painter.setPen(QPen(GRID_COLOR, 0))
            x = self.grid_size
            while x < canvas.right():
                painter.drawLine(QPointF(x, 0), QPointF(x, canvas.bottom()))
                x += self.grid_size
            y = self.grid_size
            while y < canvas.bottom():
                painter.drawLine(QPointF(0, y), QPointF(canvas.right(), y))
                y += self.grid_size

        outside = QPainterPath()
        outside.addRect(rect)
        inside = QPainterPath()
        inside.addRect(canvas)
        painter.fillPath(outside.subtracted(inside), QColor(40, 44, 52, 110))
        painter.setPen(QPen(QColor("#B0B6C0"), 0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(canvas)

        if self.group_outlines:
            painter.setPen(QPen(SELECTION_COLOR, 1.5 / scale, Qt.PenStyle.DashLine))
            for outline in self.group_outlines:
                painter.drawRect(outline)

        gx, gy = self.guides
        painter.setPen(QPen(GUIDE_COLOR, 1 / scale))
        if gx is not None:
            painter.drawLine(QPointF(gx, rect.top()), QPointF(gx, rect.bottom()))
        if gy is not None:
            painter.drawLine(QPointF(rect.left(), gy), QPointF(rect.right(), gy))
