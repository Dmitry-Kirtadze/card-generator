"""Розділ панелі властивостей для таблиці.

Зверху — налаштування всієї таблиці, далі — мініатюра таблиці (QTableWidget),
де вибираються клітинки й вводиться текст, і стиль вибраних клітинок.
Стиль змінюється одразу в усіх вибраних клітинках через AttrProxy.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QGridLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...model import TableElement
from ...model import table_ops
from ..color_button import ColorButton

if TYPE_CHECKING:
    from .properties import PropertiesPanel


class AttrProxy:
    """Читання — з першого об'єкта, запис — в усі. Для редагування кількох клітинок разом."""

    def __init__(self, objects: list[Any]):
        object.__setattr__(self, "_objects", objects)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._objects[0], name)

    def __setattr__(self, name: str, value: Any) -> None:
        for obj in self._objects:
            setattr(obj, name, value)


def paint_color(panel: PropertiesPanel, label: str, paint: Any, key: str) -> ColorButton:
    """Колір заливки з варіантом «без заливки» (Paint.kind none/solid)."""
    button = ColorButton(panel.workspace.recent_colors, panel.workspace.add_recent_color, allow_none=True)
    button.setObjectName(key)

    def apply(value: str) -> None:
        paint.kind = "solid" if value else "none"
        if value:
            paint.color = value
        panel._emit(key)

    button.colorChanged.connect(apply)
    panel._refreshers.append(lambda: button.set_color(paint.color if paint.kind != "none" else ""))
    panel._form.addRow(label, button)
    return button


def build_table(panel: PropertiesPanel, t: TableElement) -> None:
    cells = {(r, c) for r, c in panel.table_cells if r < t.rows and c < t.cols}
    panel.table_cells = cells

    panel._section("Таблиця")
    size = QWidget()
    size_layout = QGridLayout(size)
    size_layout.setContentsMargins(0, 0, 0, 0)
    rows = QSpinBox()
    rows.setObjectName("table_rows")
    rows.setRange(1, 100)
    rows.setValue(t.rows)
    cols = QSpinBox()
    cols.setObjectName("table_cols")
    cols.setRange(1, 20)
    cols.setValue(t.cols)
    for spin in (rows, cols):
        spin.setKeyboardTracking(False)

    def resize_table() -> None:
        table_ops.resize(t, rows.value(), cols.value())
        structure_changed(panel, t, "table_size")

    rows.valueChanged.connect(lambda _v: resize_table())
    cols.valueChanged.connect(lambda _v: resize_table())
    size_layout.addWidget(QLabel("Рядків"), 0, 0)
    size_layout.addWidget(rows, 0, 1)
    size_layout.addWidget(QLabel("Стовпців"), 1, 0)
    size_layout.addWidget(cols, 1, 1)
    panel._form.addRow(size)

    # рядок/стовпець, відносно якого вставляємо — перша вибрана клітинка (або останній)
    def row() -> int:
        return min((r for r, _ in panel.table_cells), default=t.rows - 1)

    def col() -> int:
        return min((c for _, c in panel.table_cells), default=t.cols - 1)

    buttons = QWidget()
    grid = QGridLayout(buttons)
    grid.setContentsMargins(0, 0, 0, 0)
    actions = [
        ("row_above", "+ Рядок вище", lambda: table_ops.insert_row(t, row())),
        ("row_below", "+ Рядок нижче", lambda: table_ops.insert_row(t, row() + 1)),
        ("col_left", "+ Стовпець зліва", lambda: table_ops.insert_col(t, col())),
        ("col_right", "+ Стовпець справа", lambda: table_ops.insert_col(t, col() + 1)),
        ("row_delete", "− Рядок", lambda: table_ops.delete_row(t, row())),
        ("col_delete", "− Стовпець", lambda: table_ops.delete_col(t, col())),
        ("equal_cols", "Рівні стовпці", lambda: setattr(t, "col_widths", table_ops.equalize(t.col_widths))),
        ("equal_rows", "Рівні рядки", lambda: setattr(t, "row_heights", table_ops.equalize(t.row_heights))),
    ]
    for i, (key, text, operation) in enumerate(actions):
        button = QPushButton(text)
        button.setObjectName(f"btn_{key}")

        def run(_=False, op=operation, k=key) -> None:
            try:
                op()
            except table_ops.TableError:
                return
            structure_changed(panel, t, k)

        button.clicked.connect(run)
        grid.addWidget(button, i // 2, i % 2)
    panel._form.addRow(buttons)

    panel._section("Рамка і фон")
    panel.color("Колір ліній", t.border, "color", key="table_border_color")
    panel.number("Товщина ліній", t.border, "width", 0, 50, step=0.5, decimals=1, key="table_border_width")
    panel.check("Зовнішня рамка", t, "border_outer")
    panel.check("Лінії між рядками", t, "border_inner_h")
    panel.check("Лінії між стовпцями", t, "border_inner_v")
    panel.number("Скруглення", t, "corner_radius", 0, 2000, suffix=" px", key="table_radius")
    paint_color(panel, "Фон таблиці", t.background, "table_background")
    paint_color(panel, "Кожен 2-й рядок", t.stripe, "table_stripe")

    panel._section("Клітинки")
    hint = QLabel("Виберіть клітинки тут або клацанням по таблиці на полотні (Shift — кілька). "
                  "Текст можна вводити просто в цій мініатюрі. Межі стовпців і рядків "
                  "перетягуються мишею на полотні.")
    hint.setWordWrap(True)
    hint.setStyleSheet("color: #6B7280;")
    panel._form.addRow(hint)
    section = CellSection(panel, t)
    panel._form.addRow(_mirror(panel, t, section))
    panel._form.addRow(section.container)
    section.rebuild()


class CellSection:
    """Розділ «Вибрані клітинки», що перебудовується окремо від решти панелі
    (щоб не переривати виділення мишею в мініатюрі)."""

    def __init__(self, panel: PropertiesPanel, t: TableElement):
        self.panel = panel
        self.table = t
        self.container = QWidget()
        self.container.setObjectName("cellSection")
        self._layout = QVBoxLayout(self.container)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._inner: QWidget | None = None
        self._refreshers: list = []
        panel._refreshers.append(lambda: [refresh() for refresh in self._refreshers])

    def rebuild(self) -> None:
        panel = self.panel
        if self._inner is not None:
            self._layout.removeWidget(self._inner)
            self._inner.hide()
            self._inner.deleteLater()
        self._inner = QWidget()
        form = QFormLayout(self._inner)
        form.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self._inner)
        saved_form, saved_refreshers = panel._form, panel._refreshers
        panel._form, panel._refreshers = form, []
        panel._rebuild_cells = self.rebuild  # для галочки «Заповнюване» в клітинках
        try:
            _build_cells(panel, self.table)
            self._refreshers = panel._refreshers
        finally:
            panel._form, panel._refreshers = saved_form, saved_refreshers
        self._inner.show()  # після заповнення — тоді й поля показуються одразу
        panel._updating = True
        try:
            for refresh in self._refreshers:
                refresh()
        finally:
            panel._updating = False


def _build_cells(panel: PropertiesPanel, t: TableElement) -> None:
    cells = panel.table_cells
    if not cells:
        select_all = QPushButton("Вибрати всі клітинки")
        select_all.setObjectName("btn_select_all_cells")
        select_all.clicked.connect(
            lambda: panel.select_cells({(r, c) for r in range(t.rows) for c in range(t.cols)}))
        panel._form.addRow(select_all)
        return

    chosen = table_ops.cells_in(t, cells)
    panel._section(f"Вибрані клітинки: {len(chosen)}")
    style = AttrProxy([c.style for c in chosen])
    cell = AttrProxy(chosen)
    panel.font("Шрифт", style, "font_family")
    panel.number("Розмір", style, "font_size", 1, 1000, suffix=" px", key="cell_font_size")
    panel.check("Жирний", style, "bold", key="cell_bold")
    panel.check("Курсив", style, "italic", key="cell_italic")
    panel.color("Колір тексту", style, "color", key="cell_color")
    panel.combo("Вирівнювання", style, "align", [("left", "Ліворуч"), ("center", "По центру"),
                                                 ("right", "Праворуч")], key="cell_align")
    panel.combo("По вертикалі", style, "valign", [("top", "Зверху"), ("middle", "Посередині"),
                                                  ("bottom", "Знизу")], key="cell_valign")
    paint_color(panel, "Фон клітинок", AttrProxy([c.background for c in chosen]), "cell_background")
    panel.number("Відступ", cell, "padding", 0, 500, suffix=" px", key="cell_padding")
    panel.check("Переносити рядки", cell, "wrap", key="cell_wrap")
    panel.check("Зменшувати шрифт", cell, "auto_shrink", key="cell_shrink")
    panel.number("Мінімальний розмір", cell, "min_font_size", 1, 500, suffix=" px", key="cell_min_size")

    panel.binding_section(AttrProxy([c.binding for c in chosen]), key="cell",
                          rebuild=panel._rebuild_cells)


def structure_changed(panel: PropertiesPanel, t: TableElement, key: str) -> None:
    """Змінилась кількість рядків/стовпців або розміри — перебудувати панель."""
    table_ops.check(t)
    panel.table_cells = {(r, c) for r, c in panel.table_cells if r < t.rows and c < t.cols}
    panel._emit(key)
    panel.set_target(t)
    panel.cellsSelected.emit(panel.table_cells)


def _mirror(panel: PropertiesPanel, t: TableElement, section: CellSection) -> QTableWidget:
    view = QTableWidget(t.rows, t.cols)
    view.setObjectName("tableMirror")
    view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    view.verticalHeader().setDefaultSectionSize(26)
    view.setMinimumHeight(min(60 + 26 * t.rows, 320))
    for r in range(t.rows):
        for c in range(t.cols):
            cell = t.cells[r][c]
            item = QTableWidgetItem(cell.text)
            if cell.binding.enabled:
                item.setToolTip(f"Заповнюється зі стовпця «{cell.binding.column}»")
                item.setForeground(QColor("#4C8DFF"))  # видно і на світлій, і на темній темі
            view.setItem(r, c, item)
    for r, c in panel.table_cells:
        view.item(r, c).setSelected(True)

    def edited(item: QTableWidgetItem) -> None:
        r, c = item.row(), item.column()
        if t.cells[r][c].text != item.text():
            t.cells[r][c].text = item.text()
            panel._emit(f"cell_text:{r}:{c}")

    def selected() -> None:
        cells = {(i.row(), i.column()) for i in view.selectedItems()}
        if cells != panel.table_cells:
            panel.table_cells = cells
            panel.cellsSelected.emit(cells)
            section.rebuild()

    view.itemChanged.connect(edited)
    view.itemSelectionChanged.connect(selected)
    return view
