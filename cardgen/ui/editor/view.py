"""Вид полотна: масштаб коліщатком з Ctrl, прокрутка, пересування пробілом."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGraphicsView

from ...render.painter import setup_painter
from .items import EditorScene, ElementItem

ZOOM_MIN, ZOOM_MAX = 0.05, 8.0


class CanvasView(QGraphicsView):
    zoomChanged = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackgroundBrush(QColor("#5B6170"))
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        painter_hints = QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform \
            | QPainter.RenderHint.TextAntialiasing
        self.setRenderHints(painter_hints)
        self._space = False

    def editor_scene(self) -> EditorScene:
        return self.scene()

    def zoom(self) -> float:
        return self.transform().m11()

    def set_zoom(self, value: float) -> None:
        value = max(ZOOM_MIN, min(ZOOM_MAX, value))
        self.resetTransform()
        self.scale(value, value)
        self._zoom_updated()

    def zoom_by(self, factor: float) -> None:
        target = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom() * factor))
        self.scale(target / self.zoom(), target / self.zoom())
        self._zoom_updated()

    def fit_canvas(self) -> None:
        scene = self.editor_scene()
        if scene is None:
            return
        rect = scene.canvas_rect()
        margin = 40
        vw = max(1, self.viewport().width() - margin * 2)
        vh = max(1, self.viewport().height() - margin * 2)
        self.set_zoom(min(vw / rect.width(), vh / rect.height()))
        self.centerOn(rect.center())

    def _zoom_updated(self) -> None:
        # маркери мають сталий розмір на екрані -> межі елементів змінились
        for item in self.scene().items() if self.scene() else []:
            if isinstance(item, ElementItem):
                item.prepareGeometryChange()
        self.zoomChanged.emit(self.zoom())

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_by(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat() and not self._space:
            self._space = True
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.setInteractive(False)
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat() and self._space:
            self._space = False
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.setInteractive(True)
            return
        super().keyReleaseEvent(event)

    def drawBackground(self, painter: QPainter, rect) -> None:
        setup_painter(painter)
        super().drawBackground(painter, rect)
