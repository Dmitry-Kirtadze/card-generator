"""Схема таблиці даних: які стовпці потрібні шаблону.

Стовпці збираються з усіх заповнюваних блоків і клітинок у порядку їх появи.
Першим завжди йде «Артикул» — унікальний ключ товару.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..model import PhotoElement, TableElement, Template, TextElement
from ..model.walk import iter_elements

KEY_COLUMN = "Артикул"
TYPE_TITLES = {"text": "Текст", "number": "Число", "list": "Список", "image": "Фото"}


@dataclass
class FieldSpec:
    column: str
    field_type: str = "text"
    required: bool = False
    options: list[str] = field(default_factory=list)
    used_in: list[str] = field(default_factory=list)  # назви блоків, де використано

    @property
    def is_image(self) -> bool:
        return self.field_type == "image"


@dataclass
class Schema:
    fields: list[FieldSpec]
    conflicts: list[str] = field(default_factory=list)  # один стовпець з різними типами

    @property
    def columns(self) -> list[str]:
        return [f.column for f in self.fields]

    def get(self, column: str) -> FieldSpec | None:
        key = normalize_column(column)
        return next((f for f in self.fields if normalize_column(f.column) == key), None)


def normalize_column(name: str) -> str:
    return " ".join(str(name).split()).casefold()


def _bindings(template: Template):
    """(binding, назва місця) для кожного заповнюваного поля в порядку появи."""
    for element in iter_elements(template.elements):
        name = element.name or element.TYPE
        if isinstance(element, (TextElement, PhotoElement)):
            yield element.binding, name
        elif isinstance(element, TableElement):
            for r, row in enumerate(element.cells):
                for c, cell in enumerate(row):
                    yield cell.binding, f"{name} [{r + 1}:{c + 1}]"


def build_schema(template: Template) -> Schema:
    specs: dict[str, FieldSpec] = {}
    conflicts: list[str] = []
    key = FieldSpec(KEY_COLUMN, "text", required=True, used_in=["ключ товару"])
    specs[normalize_column(KEY_COLUMN)] = key
    for binding, place in _bindings(template):
        if not binding.enabled or not binding.column.strip():
            continue
        column = " ".join(binding.column.split())
        norm = normalize_column(column)
        spec = specs.get(norm)
        if spec is None:
            specs[norm] = FieldSpec(column, binding.field_type, binding.required,
                                    list(binding.options), [place])
            continue
        spec.used_in.append(place)
        spec.required = spec.required or binding.required
        for option in binding.options:
            if option not in spec.options:
                spec.options.append(option)
        if spec.field_type != binding.field_type and norm != normalize_column(KEY_COLUMN):
            message = (f"Стовпець «{spec.column}» використано як "
                       f"«{TYPE_TITLES.get(spec.field_type)}» і як «{TYPE_TITLES.get(binding.field_type)}»")
            if message not in conflicts:
                conflicts.append(message)
    return Schema(list(specs.values()), conflicts)
