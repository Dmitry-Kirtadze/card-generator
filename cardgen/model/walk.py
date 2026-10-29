"""Обхід шаблону: усі блоки (включно з вкладеними в групи), посилання на ресурси, шрифти."""
from __future__ import annotations

from collections.abc import Iterable, Iterator

from .elements import Element, GroupElement, IconElement, PhotoElement, TableElement, TextElement, TextStyle
from .template import Template


def iter_elements(elements: Iterable[Element]) -> Iterator[Element]:
    for element in elements:
        yield element
        if isinstance(element, GroupElement):
            yield from iter_elements(element.children)


def iter_text_styles(template: Template) -> Iterator[TextStyle]:
    for element in iter_elements(template.elements):
        if isinstance(element, TextElement):
            yield element.style
        elif isinstance(element, TableElement):
            for row in element.cells:
                for cell in row:
                    yield cell.style


def font_families(template: Template) -> set[str]:
    return {style.font_family for style in iter_text_styles(template)}


def _asset_slots(template: Template) -> Iterator[tuple[object, str]]:
    """Пари (об'єкт, назва атрибута), де зберігається посилання на ресурс."""
    yield template.background, "asset"
    for element in iter_elements(template.elements):
        if isinstance(element, IconElement):
            yield element, "asset"
        elif isinstance(element, PhotoElement):
            yield element, "placeholder"


def asset_refs(template: Template) -> set[str]:
    return {getattr(obj, attr) for obj, attr in _asset_slots(template) if getattr(obj, attr)}


def replace_asset_refs(template: Template, mapping: dict[str, str]) -> bool:
    """Замінює посилання за словником. Повертає True, якщо щось змінилося."""
    changed = False
    for obj, attr in _asset_slots(template):
        old = getattr(obj, attr)
        if old in mapping:
            setattr(obj, attr, mapping[old])
            changed = True
    return changed
