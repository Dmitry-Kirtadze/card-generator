"""Шаблон картки та категорія."""
from __future__ import annotations

from dataclasses import dataclass, field

from .elements import Element, new_id


@dataclass
class Background:
    """Фонове зображення: масштабується, але не перехоплює мишу в редакторі."""

    color: str = "#FFFFFF"
    asset: str = ""
    fit: str = "cover"  # cover | contain | stretch
    scale: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0


DEFAULT_FILENAME_MASK = "{Артикул}_{№}"


@dataclass
class ExportSettings:
    """Маска імені файлу: {Артикул}, {будь-який стовпець даних}, {№} — номер картинки шаблону,
    {шаблон} — назва шаблону. Номер відрізняє картинки одного товару з різних шаблонів:
    AWG-18_1.jpg — обкладинка, AWG-18_2.jpg — характеристики."""

    filename_mask: str = DEFAULT_FILENAME_MASK
    number: int = 1
    jpeg_quality: int = 92
    preset: str = "prom_rozetka"


@dataclass
class Template:
    id: str = field(default_factory=new_id)
    name: str = "Новий шаблон"
    width: int = 1000
    height: int = 1000
    background: Background = field(default_factory=Background)
    elements: list[Element] = field(default_factory=list)
    export: ExportSettings = field(default_factory=ExportSettings)


@dataclass
class Category:
    id: str = field(default_factory=new_id)
    name: str = "Нова категорія"
    created_at: str = ""
    protected: bool = False  # вбудована категорія (Маркет): не видаляється й не перейменовується
    seeded: list[str] = field(default_factory=list)  # Маркет: які пакети шаблонів уже завантажено
