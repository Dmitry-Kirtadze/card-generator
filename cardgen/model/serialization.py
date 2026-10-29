"""Перетворення моделі у словники для JSON і назад.

Сумісність версій:
- зайві (невідомі) поля в файлі ігноруються;
- відсутні поля отримують значення за замовчуванням;
- для змін структури, які так не покриваються, є MIGRATIONS:
  функція з версії N у N+1 над сирим словником.
"""
from __future__ import annotations

import dataclasses
import typing
from typing import Any, Callable, TypeVar

from .elements import ELEMENT_TYPES, Element
from .template import DEFAULT_FILENAME_MASK, Category, Template

SCHEMA_VERSION = 2


def _v1_to_v2(data: dict) -> dict:
    """Етап 8: стара маска «{Артикул}» давала однакові імена файлів для різних шаблонів."""
    export = data.get("export")
    if isinstance(export, dict) and export.get("filename_mask", "{Артикул}") == "{Артикул}":
        export["filename_mask"] = DEFAULT_FILENAME_MASK
    return data


# версія N -> функція, що перетворює словник шаблону з версії N у N+1
MIGRATIONS: dict[int, Callable[[dict], dict]] = {1: _v1_to_v2}

T = TypeVar("T")


class SchemaError(Exception):
    pass


def to_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        data: dict[str, Any] = {}
        if isinstance(obj, Element):
            data["type"] = obj.TYPE
        for f in dataclasses.fields(obj):
            data[f.name] = to_dict(getattr(obj, f.name))
        return data
    if isinstance(obj, list):
        return [to_dict(item) for item in obj]
    return obj


def from_dict(cls: type[T], data: Any) -> T:
    return _convert(cls, data)


def _convert(hint: Any, value: Any) -> Any:
    if isinstance(hint, type) and dataclasses.is_dataclass(hint):
        # блоки поліморфні: конкретний клас визначається полем "type"
        if issubclass(hint, Element):
            return _element_from_dict(value)
        return _dataclass_from_dict(hint, value)
    origin = typing.get_origin(hint)
    if origin is list:
        (item_hint,) = typing.get_args(hint)
        if not isinstance(value, list):
            raise SchemaError(f"Очікувався список, отримано {type(value).__name__}")
        return [_convert(item_hint, item) for item in value]
    if hint is float and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    return value


def _dataclass_from_dict(cls: type[T], data: Any) -> T:
    if not isinstance(data, dict):
        raise SchemaError(f"{cls.__name__}: очікувався об'єкт, отримано {type(data).__name__}")
    hints = typing.get_type_hints(cls)
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name in data:
            kwargs[f.name] = _convert(hints[f.name], data[f.name])
    return cls(**kwargs)


def _element_from_dict(data: Any) -> Element:
    if not isinstance(data, dict):
        raise SchemaError("Блок має бути об'єктом")
    type_name = data.get("type")
    cls = ELEMENT_TYPES.get(type_name)
    if cls is None:
        raise SchemaError(f"Невідомий тип блоку: {type_name!r}")
    return _dataclass_from_dict(cls, data)


# --- Шаблон і категорія ---------------------------------------------------

def template_to_dict(template: Template) -> dict:
    return {"schema_version": SCHEMA_VERSION, **to_dict(template)}


def template_from_dict(data: dict) -> Template:
    data = _migrate(dict(data))
    return from_dict(Template, data)


def category_to_dict(category: Category) -> dict:
    return {"schema_version": SCHEMA_VERSION, **to_dict(category)}


def category_from_dict(data: dict) -> Category:
    return from_dict(Category, data)


def _migrate(data: dict) -> dict:
    version = data.get("schema_version", 1)
    if not isinstance(version, int) or version < 1:
        raise SchemaError(f"Некоректна версія формату: {version!r}")
    if version > SCHEMA_VERSION:
        raise SchemaError(
            f"Шаблон створено новішою версією програми (формат {version}, "
            f"підтримується до {SCHEMA_VERSION}). Оновіть програму."
        )
    while version < SCHEMA_VERSION:
        migrate = MIGRATIONS.get(version)
        if migrate is None:
            raise SchemaError(f"Немає міграції з версії {version}")
        data = migrate(data)
        version += 1
        data["schema_version"] = version
    return data
