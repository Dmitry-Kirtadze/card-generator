"""Блоки, з яких складається шаблон картки.

Усі координати й розміри — у пікселях полотна шаблону (не екрана).
Кольори — рядки "#RRGGBB" або "#RRGGBBAA".
Порядок блоків у списку = порядок шарів: останній блок — найвищий.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import ClassVar


def new_id() -> str:
    return uuid.uuid4().hex[:12]


# --- Допоміжні структури -------------------------------------------------

FIELD_TYPES = ("text", "number", "list", "image")


@dataclass
class FieldBinding:
    """Налаштування «заповнюване»: з якого стовпця таблиці блок бере дані."""

    enabled: bool = False
    column: str = ""
    field_type: str = "text"  # text | number | list | image
    prefix: str = ""
    suffix: str = ""
    required: bool = False
    options: list[str] = field(default_factory=list)  # для field_type == "list"


@dataclass
class Paint:
    """Заливка: без заливки, суцільний колір або лінійний градієнт."""

    kind: str = "solid"  # none | solid | linear
    color: str = "#FFFFFF"
    color2: str = "#000000"
    angle: float = 90.0


@dataclass
class Stroke:
    color: str = "#000000"
    width: float = 0.0


@dataclass
class Shadow:
    enabled: bool = False
    color: str = "#00000055"
    offset_x: float = 0.0
    offset_y: float = 4.0
    blur: float = 12.0


@dataclass
class TextStyle:
    font_family: str = "Arial"
    font_size: float = 32.0
    bold: bool = False
    italic: bool = False
    color: str = "#111111"
    align: str = "left"  # left | center | right
    valign: str = "top"  # top | middle | bottom
    line_height: float = 1.2
    letter_spacing: float = 0.0


# --- Блоки ---------------------------------------------------------------

ELEMENT_TYPES: dict[str, type[Element]] = {}


def register(cls: type[Element]) -> type[Element]:
    ELEMENT_TYPES[cls.TYPE] = cls
    return cls


@dataclass
class Element:
    """Спільні властивості будь-якого блоку."""

    TYPE: ClassVar[str] = ""

    id: str = field(default_factory=new_id)
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 100.0
    height: float = 100.0
    rotation: float = 0.0
    opacity: float = 1.0
    visible: bool = True
    locked: bool = False


@register
@dataclass
class TextElement(Element):
    TYPE: ClassVar[str] = "text"

    text: str = "Текст"
    style: TextStyle = field(default_factory=TextStyle)
    wrap: bool = True
    auto_shrink: bool = True
    min_font_size: float = 10.0
    binding: FieldBinding = field(default_factory=FieldBinding)


SHAPES = ("rect", "ellipse", "line")


@register
@dataclass
class ShapeElement(Element):
    TYPE: ClassVar[str] = "shape"

    shape: str = "rect"  # rect | ellipse | line
    fill: Paint = field(default_factory=Paint)
    stroke: Stroke = field(default_factory=Stroke)
    corner_radius: float = 0.0
    shadow: Shadow = field(default_factory=Shadow)


@register
@dataclass
class IconElement(Element):
    """Статична іконка з бібліотеки."""

    TYPE: ClassVar[str] = "icon"

    asset: str = ""  # посилання на ресурс, див. storage.resolve_asset
    tint: str = ""  # порожньо = оригінальні кольори


@register
@dataclass
class PhotoElement(Element):
    """Фото товару: підставляється з таблиці, вільно масштабується в рамці."""

    TYPE: ClassVar[str] = "photo"

    placeholder: str = ""  # зображення для редактора, поки немає даних
    fit: str = "contain"  # contain | cover | stretch
    content_scale: float = 1.0
    content_offset_x: float = 0.0
    content_offset_y: float = 0.0
    corner_radius: float = 0.0
    shadow: Shadow = field(default_factory=Shadow)
    # білий фон навколо товару стає прозорим (для фото магазину на білому тлі)
    remove_white: bool = False
    white_tolerance: int = 20  # наскільки «не зовсім білі» пікселі теж вважати фоном, 1–80
    binding: FieldBinding = field(
        default_factory=lambda: FieldBinding(enabled=True, column="Фото", field_type="image")
    )


@dataclass
class TableCell:
    text: str = ""
    style: TextStyle = field(default_factory=lambda: TextStyle(font_size=24.0, valign="middle"))
    background: Paint = field(default_factory=lambda: Paint(kind="none"))
    padding: float = 8.0
    wrap: bool = True
    auto_shrink: bool = True
    min_font_size: float = 10.0
    binding: FieldBinding = field(default_factory=FieldBinding)


@register
@dataclass
class TableElement(Element):
    """Таблиця як у Word: рядки × стовпці, кожна клітинка — окремий текст зі своїм стилем.

    Ширини стовпців і висоти рядків — відносні частки від розміру блоку.
    Зміни структури робити через model.table_ops, щоб rows/cols/cells збігалися.
    """

    TYPE: ClassVar[str] = "table"

    rows: int = 0
    cols: int = 0
    col_widths: list[float] = field(default_factory=list)  # відносні частки
    row_heights: list[float] = field(default_factory=list)  # відносні частки
    cells: list[list[TableCell]] = field(default_factory=list)
    border: Stroke = field(default_factory=lambda: Stroke(color="#DDDDDD", width=1.0))
    border_outer: bool = True
    border_inner_h: bool = True  # лінії між рядками
    border_inner_v: bool = True  # лінії між стовпцями
    background: Paint = field(default_factory=lambda: Paint(kind="none"))
    stripe: Paint = field(default_factory=lambda: Paint(kind="none"))  # заливка кожного другого рядка
    corner_radius: float = 0.0

    @classmethod
    def create(cls, rows: int, cols: int, **kwargs) -> TableElement:
        return cls(
            rows=rows,
            cols=cols,
            col_widths=[1.0] * cols,
            row_heights=[1.0] * rows,
            cells=[[TableCell() for _ in range(cols)] for _ in range(rows)],
            **kwargs,
        )


@register
@dataclass
class GroupElement(Element):
    """Група: дочірні блоки мають координати полотна, група лише об'єднує їх."""

    TYPE: ClassVar[str] = "group"

    children: list[Element] = field(default_factory=list)
