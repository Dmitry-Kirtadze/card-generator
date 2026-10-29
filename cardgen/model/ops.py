"""Операції над блоками шаблону: пошук, групування, порядок шарів, копіювання.

Усі функції працюють лише з моделлю і не знають про інтерфейс.
Порядок у списку = порядок шарів: останній елемент — найвищий.
"""
from __future__ import annotations

import copy
from collections.abc import Iterable

from .elements import Element, GroupElement, new_id
from .template import Template
from .walk import iter_elements


class OpError(Exception):
    pass


def find(template: Template, element_id: str) -> Element | None:
    return next((e for e in iter_elements(template.elements) if e.id == element_id), None)


def parent_list(template: Template, element_id: str) -> list[Element]:
    """Список, у якому лежить блок (верхній рівень або діти групи)."""
    def search(elements: list[Element]) -> list[Element] | None:
        for e in elements:
            if e.id == element_id:
                return elements
            if isinstance(e, GroupElement):
                found = search(e.children)
                if found is not None:
                    return found
        return None

    result = search(template.elements)
    if result is None:
        raise OpError(f"Блок {element_id} не знайдено")
    return result


def parent_group(template: Template, element_id: str) -> GroupElement | None:
    siblings = parent_list(template, element_id)
    if siblings is template.elements:
        return None
    return next(g for g in iter_elements(template.elements)
                if isinstance(g, GroupElement) and g.children is siblings)


def top_level(template: Template, element_id: str) -> Element:
    """Блок верхнього рівня, що містить цей блок (або сам блок)."""
    for e in template.elements:
        if e.id == element_id or (isinstance(e, GroupElement)
                                  and any(c.id == element_id for c in iter_elements(e.children))):
            return e
    raise OpError(f"Блок {element_id} не знайдено")


def leaves(elements: Iterable[Element]) -> list[Element]:
    """Усі «справжні» блоки без груп, у порядку малювання."""
    return [e for e in iter_elements(elements) if not isinstance(e, GroupElement)]


def update_group_bounds(element: Element) -> None:
    """Рамка групи = рамка всіх дітей (без урахування повороту дітей)."""
    if not isinstance(element, GroupElement):
        return
    for child in element.children:
        update_group_bounds(child)
    if not element.children:
        return
    left = min(c.x for c in element.children)
    top = min(c.y for c in element.children)
    right = max(c.x + c.width for c in element.children)
    bottom = max(c.y + c.height for c in element.children)
    element.x, element.y, element.width, element.height = left, top, right - left, bottom - top


def update_all_group_bounds(template: Template) -> None:
    for e in template.elements:
        update_group_bounds(e)


def move_by(element: Element, dx: float, dy: float) -> None:
    element.x += dx
    element.y += dy
    if isinstance(element, GroupElement):
        for child in element.children:
            move_by(child, dx, dy)


# --- Групування ------------------------------------------------------------

def group(template: Template, ids: list[str], name: str = "Група") -> GroupElement:
    """Об'єднує блоки одного рівня в групу. Група стає на місце найвищого з них."""
    if len(ids) < 2:
        raise OpError("Для групи потрібно щонайменше два блоки")
    siblings = parent_list(template, ids[0])
    if any(parent_list(template, i) is not siblings for i in ids):
        raise OpError("Групувати можна лише блоки одного рівня")
    id_set = set(ids)
    members = [e for e in siblings if e.id in id_set]
    position = max(i for i, e in enumerate(siblings) if e.id in id_set)
    new_group = GroupElement(name=name, children=members)
    update_group_bounds(new_group)
    siblings.insert(position + 1, new_group)
    siblings[:] = [e for e in siblings if e.id not in id_set]
    return new_group


def ungroup(template: Template, group_id: str) -> list[str]:
    siblings = parent_list(template, group_id)
    index = next(i for i, e in enumerate(siblings) if e.id == group_id)
    g = siblings[index]
    if not isinstance(g, GroupElement):
        raise OpError("Це не група")
    siblings[index:index + 1] = g.children
    return [c.id for c in g.children]


# --- Порядок шарів ------------------------------------------------------------

def reorder(template: Template, ids: list[str], mode: str) -> None:
    """mode: up — на шар вище, down — нижче, front — нагору, back — донизу."""
    if not ids:
        return
    siblings = parent_list(template, ids[0])
    id_set = {i for i in ids if parent_list(template, i) is siblings}
    if mode == "front":
        siblings[:] = [e for e in siblings if e.id not in id_set] + [e for e in siblings if e.id in id_set]
    elif mode == "back":
        siblings[:] = [e for e in siblings if e.id in id_set] + [e for e in siblings if e.id not in id_set]
    elif mode == "up":
        for i in range(len(siblings) - 2, -1, -1):
            if siblings[i].id in id_set and siblings[i + 1].id not in id_set:
                siblings[i], siblings[i + 1] = siblings[i + 1], siblings[i]
    elif mode == "down":
        for i in range(1, len(siblings)):
            if siblings[i].id in id_set and siblings[i - 1].id not in id_set:
                siblings[i], siblings[i - 1] = siblings[i - 1], siblings[i]
    else:
        raise ValueError(mode)


# --- Видалення й копіювання -------------------------------------------------

def delete(template: Template, ids: Iterable[str]) -> None:
    id_set = set(ids)

    def prune(elements: list[Element]) -> list[Element]:
        result = []
        for e in elements:
            if e.id in id_set:
                continue
            if isinstance(e, GroupElement):
                e.children = prune(e.children)
                if len(e.children) < 2:  # група з одного блоку не має сенсу
                    result.extend(e.children)
                    continue
            result.append(e)
        return result

    template.elements = prune(template.elements)


def clone(element: Element) -> Element:
    """Глибока копія з новими id (для групи — і в усіх дітей)."""
    copied = copy.deepcopy(element)
    for e in iter_elements([copied]):
        e.id = new_id()
    return copied


def topmost_units(template: Template, ids: Iterable[str]) -> list[Element]:
    """Перетворює набір id на блоки без вкладених повторів (якщо вибрано групу і її дитину — лише група),
    у порядку малювання."""
    id_set = set(ids)
    result: list[Element] = []

    def walk(elements: list[Element]) -> None:
        for e in elements:
            if e.id in id_set:
                result.append(e)
            elif isinstance(e, GroupElement):
                walk(e.children)

    walk(template.elements)
    return result
