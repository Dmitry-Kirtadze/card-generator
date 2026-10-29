"""Збирає 10 готових шаблонів для Маркету: market/NN Назва.cardgen.zip

    .venv\\Scripts\\python tools\\build_market.py            — зібрати пакети
    .venv\\Scripts\\python tools\\build_market.py --preview  — ще й аркуш-прев'ю всіх карток

Кожен пакет — категорія з одним шаблоном і прикладом товару (щоб у Маркеті й
перегляді одразу було видно, як виглядає картка).
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter  # noqa: E402

from cardgen.data.dataset import DataSet, images_dir, save_dataset  # noqa: E402
from cardgen.data.photos import store_image  # noqa: E402
from cardgen.model import (  # noqa: E402
    Background,
    FieldBinding,
    IconElement,
    Paint,
    PhotoElement,
    Shadow,
    ShapeElement,
    Stroke,
    TableElement,
    Template,
    TextElement,
    TextStyle,
)
from cardgen.products import Products  # noqa: E402
from cardgen.storage import Workspace  # noqa: E402
from cardgen.transfer import export_category  # noqa: E402
from market_assets import build_assets, write_icons  # noqa: E402

MARKET = ROOT / "market"

# --- Короткі конструктори блоків ----------------------------------------------------


def bind(column: str, prefix: str = "", suffix: str = "", *, kind: str = "text", required: bool = False,
         options: list[str] | None = None) -> FieldBinding:
    return FieldBinding(enabled=True, column=column, prefix=prefix, suffix=suffix, field_type=kind,
                        required=required, options=options or [])


def text(name, x, y, w, h, value, size, color="#0B1F44", *, family="Arial", bold=False, align="left",
         valign="top", line=1.15, b=None, min_size=None, wrap=True, rotation=0.0, spacing=0.0):
    return TextElement(name=name, x=x, y=y, width=w, height=h, text=value, wrap=wrap, rotation=rotation,
                       style=TextStyle(font_family=family, font_size=size, bold=bold, color=color, align=align,
                                       valign=valign, line_height=line, letter_spacing=spacing),
                       min_font_size=min_size or max(10, round(size * 0.55)), binding=b or FieldBinding())


def rect(name, x, y, w, h, color, *, radius=0, stroke=None, shadow=None, color2=None, angle=90, rotation=0.0):
    fill = Paint(kind="none") if color is None else (
        Paint(kind="linear", color=color, color2=color2, angle=angle) if color2 else Paint(color=color))
    return ShapeElement(name=name, x=x, y=y, width=w, height=h, corner_radius=radius, fill=fill,
                        stroke=stroke or Stroke(), shadow=shadow or Shadow(), rotation=rotation)


def circle(name, x, y, d, color, *, stroke=None, shadow=None):
    return ShapeElement(name=name, shape="ellipse", x=x, y=y, width=d, height=d,
                        fill=Paint(kind="none") if color is None else Paint(color=color),
                        stroke=stroke or Stroke(), shadow=shadow or Shadow())


def hline(name, x, y, w, color, width=2.0):
    return ShapeElement(name=name, shape="line", x=x, y=y - 5, width=w, height=10, fill=Paint(kind="none"),
                        stroke=Stroke(color=color, width=width))


def vline(name, x, y, h, color, width=2.0):
    return ShapeElement(name=name, shape="line", x=x - h / 2, y=y + h / 2 - 5, width=h, height=10, rotation=90,
                        fill=Paint(kind="none"), stroke=Stroke(color=color, width=width))


def soft_shadow(alpha="1F", blur=22, dy=8):
    return Shadow(enabled=True, color=f"#0B1F44{alpha}", blur=blur, offset_y=dy)


@dataclass
class Spec:
    file: str  # назва пакета без розширення
    category: str
    template: Template
    row: dict[str, str]
    photo: str  # ключ зразка фото
    background: str | None = None  # ключ фону з бібліотеки
    extra_photos: dict[str, str] = field(default_factory=dict)  # стовпець -> ключ зразка


class Kit:
    """Посилання на ресурси бібліотеки, заповнюються під час збирання."""

    icons: dict[str, str] = {}
    backgrounds: dict[str, str] = {}


def icon(name, key, x, y, s, tint):
    return IconElement(name=name, x=x, y=y, width=s, height=s, asset=Kit.icons[key], tint=tint)


def photo(name, x, y, w, h, *, column="Фото", fit="contain", required=True, shadow=None, radius=0):
    return PhotoElement(name=name, x=x, y=y, width=w, height=h, fit=fit, remove_white=True, corner_radius=radius,
                        shadow=shadow or Shadow(), binding=bind(column, kind="image", required=required))


# --- 1. Компонент — обкладинка -------------------------------------------------------

def t01() -> Spec:
    blue, navy = "#2563EB", "#0B1F44"
    e = [
        photo("Фото товару", 560, 140, 420, 520),
        text("Назва", 50, 40, 520, 170, "Конденсатор керамічний", 62, navy, family="Arial Black", line=1.02,
             b=bind("Назва", required=True), min_size=34),
        text("Модель", 50, 212, 520, 90, "SMD 0805", 76, blue, family="Arial Black", line=1.0, wrap=False,
             b=bind("Модель", required=True)),
        rect("Плашка", 50, 318, 520, 52, "#FFC21A", radius=26),
        text("Плашка — текст", 66, 318, 488, 52, "10 мкФ (10uF) • 25 V • X7R", 25, navy, bold=True,
             align="center", valign="middle", wrap=False, b=bind("Плашка")),
    ]
    for i, (x, value, column, label) in enumerate([(50, "10 мкФ", "Параметр 1", "Ємність"),
                                                    (320, "25 V", "Параметр 2", "Напруга")], start=1):
        e += [
            rect(f"Показник {i} — фон", x, 390, 250, 150, blue, color2="#1D4ED8", radius=18,
                 shadow=Shadow(enabled=True, color="#2563EB55", blur=18, offset_y=8)),
            text(f"Показник {i} — значення", x + 10, 400, 230, 80, value, 52, "#FFFFFF", family="Arial Black",
                 align="center", valign="middle", wrap=False, b=bind(column)),
            hline(f"Показник {i} — риска", x + 30, 487, 190, "#FFFFFF99"),
            text(f"Показник {i} — підпис", x + 10, 492, 230, 38, label, 26, "#FFFFFF", align="center",
                 valign="middle", b=bind(f"{column} — назва")),
        ]
    e += [
        rect("Корпус — рамка", 50, 560, 520, 50, "#FFFFFF", radius=25, stroke=Stroke(color="#C7D5F2", width=2)),
        icon("Корпус — іконка", "коробка", 70, 569, 32, blue),
        text("Корпус — текст", 112, 560, 440, 50, "Корпус 0805 (2012 Metric)", 24, navy, valign="middle",
             b=bind("Корпус", prefix="Корпус ")),
    ]
    for i, (y, key, title, sub) in enumerate([(630, "ракета", "Висока ємність", "у компактному корпусі"),
                                               (720, "щит", "Надійний вибір", "для сучасної електроніки")], 1):
        e += [
            circle(f"Перевага {i} — коло", 50, y, 74, blue),
            icon(f"Перевага {i} — іконка", key, 67, y + 17, 40, "#FFFFFF"),
            text(f"Перевага {i} — заголовок", 142, y + 4, 420, 36, title, 28, navy, bold=True),
            text(f"Перевага {i} — опис", 142, y + 40, 420, 32, sub, 23, "#475569"),
        ]
    e.append(rect("Нижня панель", 40, 830, 920, 140, "#FFFFFF", radius=22, shadow=soft_shadow()))
    cells = [("пульс", "Стабільна\nробота"), ("smd", "Компактний\nкорпус"), ("мікросхема", "Ідеальний для\nSMD пристроїв"),
             ("шестерня", "Для електроніки\nта ремонту")]
    for i, (key, label) in enumerate(cells):
        cx = 40 + 115 + i * 230
        e.append(icon(f"Переваги внизу {i + 1} — іконка", key, cx - 26, 846, 52, blue))
        e.append(text(f"Переваги внизу {i + 1} — підпис", cx - 105, 904, 210, 56, label, 20, navy,
                      align="center", valign="middle", line=1.1))
        if i:
            e.append(vline("Розділювач", 40 + i * 230, 860, 90, "#D5DEEE"))
    t = Template(name="Компонент — обкладинка", elements=e, background=Background(color="#F3F6FB"))
    row = {"Артикул": "CAP-0805-10UF", "Назва": "Конденсатор керамічний", "Модель": "SMD 0805",
           "Плашка": "10 мкФ (10uF) • 25 V • X7R", "Параметр 1": "10 мкФ", "Параметр 1 — назва": "Ємність",
           "Параметр 2": "25 V", "Параметр 2 — назва": "Напруга", "Корпус": "0805 (2012 Metric)"}
    return Spec("01 Компонент — обкладинка", "Компоненти", t, row, "capacitor", background="bg_dots")


# --- 2. Характеристики — таблиця --------------------------------------------------------

def t02() -> Spec:
    blue, navy = "#2563EB", "#0B1F44"
    rows = [("Ємність", "10 мкФ"), ("Напруга", "25 V"), ("Діелектрик", "X7R"),
            ("Корпус", "0805 (2012 Metric)"), ("Розміри", "2.0 × 1.25 мм"), ("Монтаж", "SMD"),
            ("Призначення", "Для сучасної електроніки")]
    table = TableElement.create(len(rows), 2, name="Таблиця характеристик", x=50, y=360, width=480, height=440,
                                corner_radius=16, border=Stroke(color="#E2E8F0", width=2),
                                background=Paint(color="#FFFFFF"))
    table.col_widths = [1.0, 1.25]
    for r, (label, value) in enumerate(rows):
        a, b = table.cells[r]
        a.text = label
        a.style.font_size = b.style.font_size = 23
        a.style.color = "#334155"
        b.style.color = blue
        b.style.bold = True
        a.padding = b.padding = 14
        b.binding = bind(label)
    e = [
        text("Заголовок", 50, 36, 620, 84, "Характеристики", 64, navy, family="Arial Black", wrap=False),
        text("Назва", 50, 120, 620, 44, "Конденсатор керамічний SMD 0805", 28, "#475569",
             b=bind("Назва", required=True), wrap=False),
        rect("Показники — фон", 50, 185, 480, 150, blue, color2="#1D4ED8", radius=20,
             shadow=Shadow(enabled=True, color="#2563EB55", blur=18, offset_y=8)),
        vline("Показники — розділювач", 290, 205, 110, "#FFFFFF88"),
        text("Показник 1", 60, 195, 220, 80, "10 мкФ", 50, "#FFFFFF", family="Arial Black", align="center",
             valign="middle", wrap=False, b=bind("Ємність")),
        text("Показник 1 — підпис", 60, 275, 220, 40, "Ємність", 26, "#FFFFFF", align="center", valign="middle"),
        text("Показник 2", 300, 195, 220, 80, "25 V", 50, "#FFFFFF", family="Arial Black", align="center",
             valign="middle", wrap=False, b=bind("Напруга")),
        text("Показник 2 — підпис", 300, 275, 220, 40, "Напруга", 26, "#FFFFFF", align="center", valign="middle"),
        table,
        photo("Фото товару", 560, 140, 400, 330),
        text("Розміри — заголовок", 560, 490, 300, 44, "Розміри", 32, blue, bold=True),
        rect("Розміри — фон", 560, 540, 400, 260, "#FFFFFF", radius=18, stroke=Stroke(color="#E2E8F0", width=2)),
        photo("Креслення розмірів", 575, 555, 370, 230, column="Фото розмірів", required=False),
        rect("Нижня панель", 40, 830, 920, 140, "#FFFFFF", radius=22, shadow=soft_shadow()),
    ]
    for i, (key, label) in enumerate([("ракета", "Компактний"), ("пульс", "Стабільні параметри"),
                                      ("мікросхема", "Для електроніки\nта ремонту")]):
        cx = 40 + 153 + i * 307
        e.append(icon(f"Внизу {i + 1} — іконка", key, cx - 28, 848, 56, blue))
        e.append(text(f"Внизу {i + 1} — підпис", cx - 140, 906, 280, 56, label, 22, navy, align="center",
                      valign="middle", line=1.1))
        if i:
            e.append(vline("Розділювач", 40 + i * 307, 860, 90, "#D5DEEE"))
    t = Template(name="Характеристики — таблиця", elements=e, background=Background(color="#F5F7FB"))
    row = {"Артикул": "CAP-0805-10UF", "Назва": "Конденсатор керамічний SMD 0805", **dict(rows)}
    return Spec("02 Характеристики — таблиця", "Компоненти", t, row, "capacitor",
                extra_photos={"Фото розмірів": "capacitor"})


# --- 3. Мінімал — білий фон -----------------------------------------------------------------

def t03() -> Spec:
    e = [
        photo("Фото товару", 80, 60, 840, 740),
        hline("Риска", 80, 840, 840, "#E5E7EB"),
        text("Назва", 80, 858, 660, 70, "Arduino Nano V3.0 (ATmega328P)", 34, "#111827", bold=True,
             b=bind("Назва", required=True), min_size=22),
        text("Артикул", 80, 928, 500, 40, "Арт. 001234", 22, "#6B7280", b=bind("Артикул", prefix="Арт. ")),
        rect("Мітка — фон", 760, 872, 160, 48, "#111827", radius=24),
        text("Мітка", 760, 872, 160, 48, "Оригінал", 22, "#FFFFFF", bold=True, align="center", valign="middle",
             wrap=False, b=bind("Мітка")),
    ]
    t = Template(name="Мінімал — білий фон", elements=e, background=Background(color="#FFFFFF"))
    row = {"Артикул": "001234", "Назва": "Arduino Nano V3.0 (ATmega328P)", "Мітка": "Оригінал"}
    return Spec("03 Мінімал — білий фон", "Модулі", t, row, "board")


# --- 4. Модуль — темний техно -----------------------------------------------------------------

def t04() -> Spec:
    cyan, card = "#22D3EE", "#101A33"
    e = [
        circle("Сяйво під фото", 600, 170, 360, "#0F1E3D",
               shadow=Shadow(enabled=True, color="#22D3EE66", blur=90, offset_y=0)),
        photo("Фото товару", 540, 110, 440, 520),
        rect("Категорія — рамка", 50, 50, 230, 42, None, radius=21, stroke=Stroke(color=cyan, width=2)),
        text("Категорія", 50, 50, 230, 42, "МОДУЛЬ", 20, cyan, bold=True, align="center", valign="middle",
             wrap=False, spacing=2, b=bind("Категорія")),
        text("Назва", 50, 110, 490, 170, "Плата розробника на базі ATmega328P", 46, "#FFFFFF",
             family="Arial Black", line=1.08, b=bind("Назва", required=True), min_size=28),
        text("Модель", 50, 285, 490, 80, "Arduino Nano", 58, cyan, family="Arial Black", wrap=False,
             b=bind("Модель", required=True)),
    ]
    for i, (value, column, label) in enumerate([("5 V", "Живлення", "Живлення"), ("USB-C", "Інтерфейс", "Інтерфейс"),
                                                ("16 МГц", "Частота", "Частота")]):
        x = 50 + i * 168
        e += [
            rect(f"Параметр {i + 1} — фон", x, 390, 152, 112, card, radius=16, stroke=Stroke(color="#1E3A5F", width=2)),
            text(f"Параметр {i + 1}", x + 6, 400, 140, 56, value, 32, "#FFFFFF", bold=True, align="center",
                 valign="middle", wrap=False, b=bind(column)),
            text(f"Параметр {i + 1} — підпис", x + 6, 458, 140, 32, label, 19, "#94A3B8", align="center",
                 valign="middle"),
        ]
    for i, (y, key, value) in enumerate([(540, "мікросхема", "Сумісний з Arduino IDE"),
                                         (625, "блискавка", "Стабілізатор живлення на платі"),
                                         (710, "робот", "Для робототехніки та DIY")], 1):
        e += [
            circle(f"Перевага {i} — коло", 50, y, 64, card, stroke=Stroke(color=cyan, width=2)),
            icon(f"Перевага {i} — іконка", key, 64, y + 14, 36, cyan),
            text(f"Перевага {i}", 132, y, 400, 64, value, 26, "#E2E8F0", valign="middle", b=bind(f"Перевага {i}")),
        ]
    e += [
        rect("Нижня смуга", 0, 880, 1000, 120, "#0E1630"),
        hline("Нижня смуга — лінія", 0, 880, 1000, cyan, 3),
        text("Нижня смуга — текст", 50, 880, 900, 120, "Гарантія 12 місяців • Відправка в день замовлення", 28,
             cyan, bold=True, align="center", valign="middle", b=bind("Плашка")),
    ]
    t = Template(name="Модуль — темний техно", elements=e, background=Background(color="#090E1E"))
    row = {"Артикул": "NANO-C", "Категорія": "МОДУЛЬ", "Назва": "Плата розробника на базі ATmega328P",
           "Модель": "Arduino Nano", "Живлення": "5 V", "Інтерфейс": "USB-C", "Частота": "16 МГц",
           "Перевага 1": "Сумісний з Arduino IDE", "Перевага 2": "Стабілізатор живлення на платі",
           "Перевага 3": "Для робототехніки та DIY", "Плашка": "Гарантія 12 місяців • Відправка в день замовлення"}
    return Spec("04 Модуль — темний техно", "Модулі", t, row, "board", background="bg_tech")


# --- 5. Акумулятор — енергія -----------------------------------------------------------------

def t05() -> Spec:
    e = [
        photo("Фото товару", 470, 130, 510, 520),
        text("Назва", 50, 50, 460, 140, "Акумулятор LiPo", 52, "#FFFFFF", family="Arial Black", line=1.05,
             b=bind("Назва", required=True), min_size=30),
        text("Ємність", 46, 190, 480, 130, "5000", 120, "#FFFFFF", family="Arial Black", line=1.0, wrap=False,
             b=bind("Ємність, мАг", kind="number")),
        text("Ємність — одиниця", 50, 318, 300, 50, "мАг", 40, "#FFF3D6", bold=True),
    ]
    for i, (value, column, label) in enumerate([("14.8 V", "Напруга", "Напруга"), ("100C", "Струмовіддача", "Струмовіддача"),
                                                ("4S1P", "Конфігурація", "Конфігурація")]):
        y = 390 + i * 104
        e += [
            rect(f"Параметр {i + 1} — фон", 50, y, 400, 88, "#FFFFFF33", radius=18,
                 stroke=Stroke(color="#FFFFFF66", width=2)),
            text(f"Параметр {i + 1} — підпис", 72, y, 200, 88, label, 22, "#FFF3D6", valign="middle"),
            text(f"Параметр {i + 1}", 250, y, 186, 88, value, 34, "#FFFFFF", family="Arial Black", align="right",
                 valign="middle", wrap=False, b=bind(column)),
        ]
    e += [
        rect("Нижня панель", 40, 730, 920, 230, "#FFFFFF", radius=26, shadow=soft_shadow("33", 26, 10)),
        text("Підходить для — заголовок", 80, 752, 400, 40, "Підходить для:", 26, "#9A3412", bold=True),
    ]
    for i, (key, label) in enumerate([("дрон", "FPV-дронів"), ("авто", "RC-моделей"), ("робот", "Робототехніки"),
                                      ("блискавка", "Портативного\nживлення")]):
        cx = 40 + 115 + i * 230
        e.append(circle(f"Застосування {i + 1} — коло", cx - 38, 798, 76, "#FFF1E6"))
        e.append(icon(f"Застосування {i + 1} — іконка", key, cx - 22, 814, 44, "#EA580C"))
        e.append(text(f"Застосування {i + 1}", cx - 110, 880, 220, 64, label, 22, "#1F2937", align="center",
                      valign="middle", line=1.1, b=bind(f"Застосування {i + 1}")))
    t = Template(name="Акумулятор — енергія", elements=e, background=Background(color="#FF7A00"))
    row = {"Артикул": "LIPO-5000-4S", "Назва": "Акумулятор LiPo", "Ємність, мАг": "5000", "Напруга": "14.8 V",
           "Струмовіддача": "100C", "Конфігурація": "4S1P", "Застосування 1": "FPV-дронів",
           "Застосування 2": "RC-моделей", "Застосування 3": "Робототехніки",
           "Застосування 4": "Портативного\nживлення"}
    return Spec("05 Акумулятор — енергія", "Акумулятори", t, row, "battery", background="bg_energy")


# --- 6. Комплектація ----------------------------------------------------------------------------

def t06() -> Spec:
    e = [
        rect("Шапка", 0, 0, 1000, 180, "#0EA5E9", color2="#2563EB", angle=0),
        text("Заголовок", 50, 34, 900, 84, "Комплектація", 64, "#FFFFFF", family="Arial Black", wrap=False),
        text("Назва", 50, 116, 900, 44, "Набір Arduino Nano для початківців", 28, "#E0F2FE",
             b=bind("Назва", required=True), wrap=False),
        rect("Фото — картка", 40, 210, 460, 600, "#FFFFFF", radius=26, shadow=soft_shadow()),
        photo("Фото товару", 60, 240, 420, 540),
        rect("Список — картка", 530, 210, 430, 600, "#FFFFFF", radius=26, shadow=soft_shadow()),
        text("Список — заголовок", 570, 240, 360, 44, "У коробці:", 30, "#0F172A", bold=True),
        hline("Список — риска", 570, 296, 350, "#E2E8F0"),
        text("Список", 562, 316, 380, 470, "✓ Плата Arduino Nano — 1 шт\n✓ Кабель USB-C — 1 шт\n"
             "✓ Штирьові лінійки — 2 шт\n✓ Перемички — 10 шт\n✓ Інструкція", 25, "#1E293B", line=1.6,
             b=bind("Комплектація", required=True), min_size=18),
        rect("Плашка", 40, 840, 920, 120, "#0F172A", radius=60),
        icon("Плашка — іконка", "щит", 90, 870, 60, "#38BDF8"),
        text("Плашка — текст", 170, 840, 760, 120, "Гарантія 12 місяців • Перевірено перед відправкою", 28,
             "#FFFFFF", bold=True, valign="middle", b=bind("Плашка")),
    ]
    t = Template(name="Комплектація", elements=e, background=Background(color="#F8FAFC"))
    row = {"Артикул": "KIT-NANO", "Назва": "Набір Arduino Nano для початківців",
           "Комплектація": "✓ Плата Arduino Nano — 1 шт\n✓ Кабель USB-C — 1 шт\n✓ Штирьові лінійки — 2 шт\n"
                           "✓ Перемички — 10 шт\n✓ Інструкція",
           "Плашка": "Гарантія 12 місяців • Перевірено перед відправкою"}
    return Spec("06 Комплектація", "Модулі", t, row, "board")


# --- 7. Розміри --------------------------------------------------------------------------------

def t07() -> Spec:
    blue = "#2563EB"
    e = [
        text("Заголовок", 50, 36, 700, 84, "Розміри", 64, "#0B1F44", family="Arial Black", wrap=False),
        text("Назва", 50, 116, 700, 44, "Arduino Nano V3.0", 28, "#475569", b=bind("Назва", required=True),
             wrap=False),
        photo("Фото товару", 190, 200, 580, 500),
        hline("Довжина — лінія", 190, 740, 580, blue, 3),
        vline("Довжина — лівий упор", 190, 722, 36, blue, 3),
        vline("Довжина — правий упор", 770, 722, 36, blue, 3),
        rect("Довжина — фон", 400, 718, 160, 44, "#F1F5F9"),
        text("Довжина", 400, 718, 160, 44, "45 мм", 30, blue, bold=True, align="center", valign="middle",
             wrap=False, b=bind("Довжина, мм", suffix=" мм")),
        vline("Висота — лінія", 830, 200, 500, blue, 3),
        hline("Висота — верхній упор", 812, 200, 36, blue, 3),
        hline("Висота — нижній упор", 812, 700, 36, blue, 3),
        rect("Висота — фон", 750, 428, 160, 44, "#F1F5F9", rotation=-90),
        text("Висота", 750, 428, 160, 44, "18 мм", 30, blue, bold=True, align="center", valign="middle",
             wrap=False, rotation=-90, b=bind("Ширина, мм", suffix=" мм")),
    ]
    for i, (key, label, value, column, suffix) in enumerate([("лінійка", "Товщина", "8", "Товщина, мм", " мм"),
                                                             ("коробка", "Вага", "7", "Вага, г", " г"),
                                                             ("шестерня", "Монтаж", "DIP", "Монтаж", "")]):
        x = 40 + i * 310
        e += [
            rect(f"Картка {i + 1}", x, 820, 290, 140, "#FFFFFF", radius=20, shadow=soft_shadow()),
            icon(f"Картка {i + 1} — іконка", key, x + 24, 856, 56, blue),
            text(f"Картка {i + 1} — підпис", x + 100, 842, 180, 36, label, 22, "#64748B"),
            text(f"Картка {i + 1} — значення", x + 100, 880, 180, 56, value, 36, "#0B1F44", family="Arial Black",
                 wrap=False, b=bind(column, suffix=suffix)),
        ]
    t = Template(name="Розміри", elements=e, background=Background(color="#F1F5F9"))
    row = {"Артикул": "001234", "Назва": "Arduino Nano V3.0", "Довжина, мм": "45", "Ширина, мм": "18",
           "Товщина, мм": "8", "Вага, г": "7", "Монтаж": "DIP"}
    return Spec("07 Розміри", "Модулі", t, row, "board")


# --- 8. Три переваги ----------------------------------------------------------------------------

def t08() -> Spec:
    yellow, dark = "#FACC15", "#0F172A"
    e = [
        rect("Права частина", 470, 0, 530, 1000, dark),
        text("Назва", 40, 40, 400, 150, "Акумулятор LiPo 5000 мАг", 40, dark, family="Arial Black", line=1.08,
             b=bind("Назва", required=True), min_size=24),
        photo("Фото товару", 20, 230, 430, 560),
        rect("Ціна — фон", 40, 830, 380, 120, yellow, radius=24),
        text("Ціна", 40, 830, 380, 120, "1 890 ₴", 56, dark, family="Arial Black", align="center", valign="middle",
             wrap=False, b=bind("Ціна", suffix=" ₴")),
        text("Підзаголовок", 520, 60, 440, 40, "ЧОМУ ОБИРАЮТЬ", 24, yellow, bold=True, spacing=3),
    ]
    items = [("блискавка", "Висока струмовіддача", "До 100C — потужність для швидких польотів"),
             ("щит", "Захищений корпус", "Міцна оболонка та якісні контакти"),
             ("годинник", "Довгий ресурс", "Понад 300 циклів заряду без втрати ємності")]
    for i, (key, title, sub) in enumerate(items, start=1):
        y = 130 + (i - 1) * 280
        e += [
            circle(f"Перевага {i} — коло", 520, y, 90, yellow),
            icon(f"Перевага {i} — іконка", key, 543, y + 23, 44, dark),
            text(f"Перевага {i} — номер", 870, y, 90, 50, f"0{i}", 36, "#334155", family="Arial Black",
                 align="right", wrap=False),
            text(f"Перевага {i}", 520, y + 110, 440, 50, title, 32, "#FFFFFF", bold=True,
                 b=bind(f"Перевага {i}"), min_size=20),
            text(f"Перевага {i} — опис", 520, y + 160, 440, 80, sub, 23, "#94A3B8", line=1.25,
                 b=bind(f"Опис {i}")),
        ]
        if i < 3:
            e.append(hline("Розділювач", 520, y + 255, 440, "#1E293B"))
    t = Template(name="Три переваги", elements=e, background=Background(color="#FFFFFF"))
    row = {"Артикул": "LIPO-5000-4S", "Назва": "Акумулятор LiPo 5000 мАг", "Ціна": "1 890",
           **{f"Перевага {i}": items[i - 1][1] for i in (1, 2, 3)},
           **{f"Опис {i}": items[i - 1][2] for i in (1, 2, 3)}}
    return Spec("08 Три переваги", "Акумулятори", t, row, "battery")


# --- 9. Застосування ------------------------------------------------------------------------------

def t09() -> Spec:
    indigo = "#4F46E5"
    e = [
        text("Заголовок", 50, 50, 520, 150, "Де\nзастосовується", 58, "#1E1B4B", family="Arial Black",
             line=1.0, min_size=36),
        text("Назва", 50, 210, 520, 80, "Модуль Arduino Nano", 30, "#4338CA", bold=True,
             b=bind("Назва", required=True)),
        circle("Фото — підкладка", 600, 30, 340, "#E0E7FF"),
        photo("Фото товару", 580, 40, 380, 320),
    ]
    tiles = [("робот", "Робототехніка"), ("дім", "Розумний дім"), ("сигнал", "IoT та бездротові\nпроєкти"),
             ("паяльник", "Навчання та DIY")]
    for i, (key, label) in enumerate(tiles):
        x = 40 + (i % 2) * 470
        y = 390 + (i // 2) * 290
        e += [
            rect(f"Плитка {i + 1}", x, y, 450, 270, "#FFFFFF", radius=26, shadow=soft_shadow()),
            circle(f"Плитка {i + 1} — коло", x + 40, y + 40, 100, "#EEF2FF"),
            icon(f"Плитка {i + 1} — іконка", key, x + 64, y + 64, 52, indigo),
            text(f"Плитка {i + 1} — номер", x + 330, y + 40, 80, 60, f"0{i + 1}", 40, "#E0E7FF",
                 family="Arial Black", align="right", wrap=False),
            text(f"Застосування {i + 1}", x + 40, y + 160, 380, 90, label, 32, "#1E1B4B", bold=True,
                 line=1.1, b=bind(f"Застосування {i + 1}"), min_size=20),
        ]
    t = Template(name="Застосування", elements=e, background=Background(color="#EEF2FF"))
    row = {"Артикул": "001234", "Назва": "Модуль Arduino Nano",
           **{f"Застосування {i + 1}": tiles[i][1] for i in range(4)}}
    return Spec("09 Застосування", "Модулі", t, row, "board")


# --- 10. Акція — знижка -----------------------------------------------------------------------------

def t10() -> Spec:
    yellow, red = "#FACC15", "#EF4444"
    e = [
        rect("Жовта смуга", -150, 330, 1300, 380, yellow, rotation=-10),
        text("Назва", 50, 50, 640, 170, "Акумулятор LiPo 5000 мАг 4S", 52, "#FFFFFF", family="Arial Black",
             line=1.05, b=bind("Назва", required=True), min_size=30),
        circle("Знижка — коло", 760, 40, 200, red, shadow=Shadow(enabled=True, color="#EF444466", blur=30, offset_y=8)),
        text("Знижка", 760, 40, 200, 200, "-15%", 64, "#FFFFFF", family="Arial Black", align="center",
             valign="middle", wrap=False, b=bind("Знижка", required=True)),
        photo("Фото товару", 150, 230, 640, 520),
        rect("Ціна — фон", 40, 780, 560, 180, "#FFFFFF", radius=28, shadow=soft_shadow("40", 26, 10)),
        text("Ціна — підпис", 76, 798, 300, 36, "Ціна зараз", 24, "#6B7280"),
        text("Ціна", 70, 830, 520, 110, "1 599 ₴", 86, "#111827", family="Arial Black", valign="middle",
             wrap=False, b=bind("Ціна", suffix=" ₴", required=True)),
        text("Стара ціна", 640, 790, 320, 60, "1 890 ₴", 40, "#9CA3AF", bold=True, wrap=False,
             b=bind("Стара ціна", suffix=" ₴")),
        hline("Стара ціна — перекреслення", 640, 822, 190, "#EF4444", 4),
        text("Термін акції", 640, 860, 320, 100, "Пропозиція діє до 30.11", 24, "#FFFFFF", line=1.2,
             b=bind("Плашка")),
    ]
    t = Template(name="Акція — знижка", elements=e, background=Background(color="#111827"))
    row = {"Артикул": "LIPO-5000-4S", "Назва": "Акумулятор LiPo 5000 мАг 4S", "Знижка": "-15%",
           "Ціна": "1 599", "Стара ціна": "1 890", "Плашка": "Пропозиція діє до 30.11"}
    return Spec("10 Акція — знижка", "Акумулятори", t, row, "battery")


SPECS = [t01, t02, t03, t04, t05, t06, t07, t08, t09, t10]


# --- Збирання ------------------------------------------------------------------------------------

def build(preview: Path | None = None) -> list[Path]:
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    packages: list[Path] = []
    rendered: list[QImage] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        from market_assets import build_series_assets
        from market_series import series_palettes, series_specs

        assets = build_assets(tmp / "assets")
        assets.update(build_series_assets(tmp / "series", series_palettes()))
        icon_files = write_icons(tmp / "icons")
        ws = Workspace(tmp / "ws")
        Kit.icons = {name: ws.add_to_library("icons", path) for name, path in icon_files.items()}
        Kit.backgrounds = {key: ws.add_to_library("backgrounds", path) for key, path in assets.items()
                           if key.startswith("bg_") or key.endswith(("_dots", "_dark", "_rays"))}
        for spec in [make() for make in SPECS] + series_specs():
            category = ws.create_category(spec.file)
            t = spec.template
            if spec.background:
                t.background.asset = Kit.backgrounds[spec.background]
            # фото-зразок у ресурсах категорії — видно в редакторі та на мініатюрах
            sample = ws.add_category_asset(category.id, assets[spec.photo])
            for element in t.elements:
                if isinstance(element, PhotoElement):
                    column = element.binding.column
                    key = spec.photo if column == "Фото" else spec.extra_photos.get(column, spec.photo)
                    element.placeholder = ws.add_category_asset(category.id, assets[key]) if key != spec.photo \
                        else sample
            ws.save_template(category.id, t)
            tables = ws.tables_dir(category.id, t.id)
            row = dict(spec.row)
            row["Фото"] = store_image(assets[spec.photo].read_bytes(), images_dir(tables), row["Артикул"], "Фото")
            for column, key in spec.extra_photos.items():
                row[column] = store_image(assets[key].read_bytes(), images_dir(tables), row["Артикул"], column)
            save_dataset(tables, DataSet(columns=list(row), rows=[row]))
            products = Products(ws, category.id, t.id)
            issues = [i.message for i in products.issues]
            card = products.render(0, 0.5)
            if issues or card.overflow:
                print(f"! {spec.file}: проблеми {issues}, не вміщується {card.overflow}")
            rendered.append(card.image)
            ws.rename_category(category.id, spec.category if spec.category not in
                               [c.name for c in ws.list_categories()] else f"{spec.category} {spec.file[:2]}")
            target = MARKET / f"{spec.file}.cardgen.zip"
            MARKET.mkdir(exist_ok=True)
            export_category(ws, category.id, target)
            packages.append(target)
            print("ok", target.name)
    if preview is not None:  # аркуші по 10 карток: <ім'я>-1.png, <ім'я>-2.png…
        cols, cell = 5, 400
        for n, start in enumerate(range(0, len(rendered), 10), start=1):
            chunk = rendered[start:start + 10]
            sheet = QImage(cols * cell, ((len(chunk) + cols - 1) // cols) * cell, QImage.Format.Format_RGB32)
            sheet.fill(QColor("#333333"))
            painter = QPainter(sheet)
            for i, image in enumerate(chunk):
                painter.drawImage(QRectF((i % cols) * cell + 5, (i // cols) * cell + 5, cell - 10, cell - 10), image)
            painter.end()
            path = preview.with_name(f"{preview.stem}-{n}{preview.suffix}")
            sheet.save(str(path))
            print("preview", path)
    return packages


if __name__ == "__main__":
    import build_market  # серії імпортують цей модуль — працюємо з одним його екземпляром

    out = None
    if "--preview" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--preview") + 1]) if len(sys.argv) > sys.argv.index("--preview") + 1 \
            else ROOT / "market-preview.png"
    build_market.build(out)
