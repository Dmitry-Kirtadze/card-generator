"""Операції з таблицею: рядки, стовпці, розміри — як у Word.

Новий рядок/стовпець копіює стиль сусіднього (але не текст), щоб таблиця
лишалася однорідною.
"""
from __future__ import annotations

import copy

from .elements import FieldBinding, TableCell, TableElement

MIN_FRACTION = 0.02  # стовпець/рядок не вужчий за 2 % таблиці


class TableError(Exception):
    pass


def _blank_like(cell: TableCell | None) -> TableCell:
    if cell is None:
        return TableCell()
    new = copy.deepcopy(cell)
    new.text = ""
    new.binding = FieldBinding()
    return new


def check(table: TableElement) -> None:
    """Перевірка узгодженості (для тестів і після завантаження)."""
    assert table.rows == len(table.cells) == len(table.row_heights)
    assert all(len(row) == table.cols for row in table.cells)
    assert table.cols == len(table.col_widths)


def insert_row(table: TableElement, index: int) -> None:
    """Вставити рядок перед index (index == rows — у кінець)."""
    index = max(0, min(index, table.rows))
    source = table.cells[min(index, table.rows - 1)] if table.rows else None
    row = [_blank_like(source[c] if source else None) for c in range(table.cols)]
    height = table.row_heights[min(index, table.rows - 1)] if table.rows else 1.0
    table.cells.insert(index, row)
    table.row_heights.insert(index, height)
    table.rows += 1


def delete_row(table: TableElement, index: int) -> None:
    if table.rows <= 1:
        raise TableError("У таблиці має лишитися хоча б один рядок")
    del table.cells[index]
    del table.row_heights[index]
    table.rows -= 1


def insert_col(table: TableElement, index: int) -> None:
    index = max(0, min(index, table.cols))
    width = table.col_widths[min(index, table.cols - 1)] if table.cols else 1.0
    for row in table.cells:
        source = row[min(index, table.cols - 1)] if table.cols else None
        row.insert(index, _blank_like(source))
    table.col_widths.insert(index, width)
    table.cols += 1


def delete_col(table: TableElement, index: int) -> None:
    if table.cols <= 1:
        raise TableError("У таблиці має лишитися хоча б один стовпець")
    for row in table.cells:
        del row[index]
    del table.col_widths[index]
    table.cols -= 1


def resize(table: TableElement, rows: int, cols: int) -> None:
    """Змінити кількість рядків/стовпців: додаються/прибираються в кінці, решта даних зберігається."""
    if rows < 1 or cols < 1:
        raise TableError("Мінімум 1 рядок і 1 стовпець")
    while table.rows < rows:
        insert_row(table, table.rows)
    while table.rows > rows:
        delete_row(table, table.rows - 1)
    while table.cols < cols:
        insert_col(table, table.cols)
    while table.cols > cols:
        delete_col(table, table.cols - 1)


def positions(weights: list[float], total: float) -> list[float]:
    """Межі смуг: [0, x1, x2, …, total]."""
    s = sum(weights) or 1.0
    result = [0.0]
    for w in weights:
        result.append(result[-1] + total * w / s)
    result[-1] = total
    return result


def move_divider(weights: list[float], index: int, position: float, total: float) -> list[float]:
    """Перетягнути межу між смугами index і index+1 у точку position (0..total).

    Сума часток не змінюється; змінюються лише дві сусідні смуги.
    """
    edges = positions(weights, total)
    lo = edges[index] + total * MIN_FRACTION
    hi = edges[index + 2] - total * MIN_FRACTION
    position = max(lo, min(hi, position))
    s = sum(weights) or 1.0
    pair = weights[index] + weights[index + 1]
    left = (position - edges[index]) / total * s
    result = list(weights)
    result[index] = left
    result[index + 1] = pair - left
    return result


def equalize(weights: list[float]) -> list[float]:
    return [1.0] * len(weights)


def cells_in(table: TableElement, cells: set[tuple[int, int]]) -> list[TableCell]:
    return [table.cells[r][c] for r, c in sorted(cells) if r < table.rows and c < table.cols]
