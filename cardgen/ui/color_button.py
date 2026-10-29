"""Кнопка вибору кольору з останніми кольорами, як у Canva."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QColorDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from ..render.colors import is_valid, normalize, qcolor, to_hex

PALETTE = [
    "#000000", "#545454", "#A6A6A6", "#FFFFFF", "#0B1F44", "#1E5BFF", "#38B6FF", "#5CE1E6",
    "#00BF63", "#7ED957", "#FFDE59", "#FFD54A", "#FF914D", "#FF5757", "#FF66C4", "#8C52FF",
]
SWATCH = 22


def swatch_icon(color: str, size: int = SWATCH) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if color and is_valid(color):
        # шахівниця під напівпрозорим кольором
        if len(color) == 9:
            p.fillRect(0, 0, size, size, QColor("#FFFFFF"))
            half = size // 2
            p.fillRect(0, 0, half, half, QColor("#CCCCCC"))
            p.fillRect(half, half, size - half, size - half, QColor("#CCCCCC"))
        p.setBrush(qcolor(color))
        p.setPen(QColor("#B0B6C0"))
        p.drawRoundedRect(0.5, 0.5, size - 1, size - 1, 4, 4)
    else:  # без кольору — перекреслений квадрат
        p.setPen(QColor("#B0B6C0"))
        p.setBrush(QColor("#FFFFFF"))
        p.drawRoundedRect(0.5, 0.5, size - 1, size - 1, 4, 4)
        p.setPen(QColor("#E5484D"))
        p.drawLine(3, size - 3, size - 3, 3)
    p.end()
    return QIcon(pixmap)


class ColorPopup(QWidget):
    picked = Signal(str)

    def __init__(self, current: str, recent: list[str], allow_none: bool, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        if recent:
            layout.addWidget(QLabel("Останні кольори"))
            layout.addLayout(self._grid(recent, "recent"))
        layout.addWidget(QLabel("Палітра"))
        layout.addLayout(self._grid(PALETTE, "palette"))

        row = QHBoxLayout()
        self.hex_edit = QLineEdit(current)
        self.hex_edit.setObjectName("hexEdit")
        self.hex_edit.setPlaceholderText("#RRGGBB")
        self.hex_edit.setMaximumWidth(110)
        self.hex_edit.returnPressed.connect(self._hex_entered)
        row.addWidget(self.hex_edit)
        more = QPushButton("Інший колір…")
        more.clicked.connect(lambda: self._dialog(current))
        row.addWidget(more)
        layout.addLayout(row)

        if allow_none:
            none = QPushButton("Без кольору")
            none.setObjectName("btn_no_color")
            none.clicked.connect(lambda: self.picked.emit(""))
            layout.addWidget(none)

    def _grid(self, colors: list[str], name: str) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(4)
        for i, color in enumerate(colors):
            button = QToolButton()
            button.setObjectName(f"{name}_{i}")
            button.setIcon(swatch_icon(color))
            button.setIconSize(QSize(SWATCH, SWATCH))
            button.setToolTip(color)
            button.setAutoRaise(True)
            button.clicked.connect(lambda _=False, c=color: self.picked.emit(c))
            grid.addWidget(button, i // 8, i % 8)
        return grid

    def _hex_entered(self) -> None:
        try:
            self.picked.emit(normalize(self.hex_edit.text()))
        except ValueError:
            self.hex_edit.selectAll()

    def _dialog(self, current: str) -> None:
        color = QColorDialog.getColor(qcolor(current, "#FFFFFF"), self, "Колір",
                                      QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            self.picked.emit(to_hex(color))


class ColorButton(QToolButton):
    """Показує поточний колір; клік відкриває палітру. Сигнал colorChanged(hex або '')."""

    colorChanged = Signal(str)

    def __init__(self, recent_provider: Callable[[], list[str]],
                 remember: Callable[[str], object], *, allow_none: bool = False, parent=None):
        super().__init__(parent)
        self._color = ""
        self._recent = recent_provider
        self._remember = remember
        self._allow_none = allow_none
        self.setIconSize(QSize(SWATCH, SWATCH))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.clicked.connect(self.open_popup)
        self.set_color("")

    def color(self) -> str:
        return self._color

    def set_color(self, color: str) -> None:
        self._color = color
        self.setIcon(swatch_icon(color))
        self.setText(color or "немає")

    def choose(self, color: str) -> None:
        """Вибір користувача: оновлює кнопку, запам'ятовує колір, повідомляє."""
        self.set_color(color)
        if color:
            self._remember(color)
        self.colorChanged.emit(color)

    def open_popup(self) -> None:
        menu = QMenu(self)
        popup = ColorPopup(self._color, self._recent(), self._allow_none)
        action = QWidgetAction(menu)
        action.setDefaultWidget(popup)
        menu.addAction(action)
        popup.picked.connect(lambda c: (menu.close(), self.choose(c)))
        menu.exec(self.mapToGlobal(self.rect().bottomLeft()))
