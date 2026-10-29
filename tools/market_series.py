"""Серії шаблонів Маркету: 10 макетів × товар зі своєю палітрою й текстами.

Макети ті самі, що й у перших 10 шаблонах (обкладинка, характеристики, мінімал, темний,
градієнт, комплектація, розміри, переваги, застосування, акція), але колір, шрифт,
іконки й дані беруться з теми та товару.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from build_market import Spec, bind, circle, hline, icon, photo, rect, soft_shadow, text, vline
from cardgen.model import Background, Paint, Shadow, Stroke, TableElement, Template


@dataclass
class Theme:
    accent: str
    accent2: str
    ink: str  # заголовки
    muted: str  # другорядний текст
    light: str  # світлий фон
    soft: str  # світлий відтінок акценту (кола, плитки)
    highlight: str  # плашки, бейджі
    highlight_ink: str  # текст на highlight
    dark: str  # фон темних макетів
    glow: str  # акцент на темному
    title_font: str = "Arial Black"
    # для генерації фонів (RGB)
    light_rgb: tuple = (243, 246, 251)
    dot_rgb: tuple = (180, 190, 220)
    dark_rgb: tuple = (9, 14, 30)
    accent_rgb: tuple = (34, 211, 238)
    rays_top: tuple = (255, 153, 0)
    rays_bottom: tuple = (255, 72, 0)
    rays_light: tuple = (255, 230, 160)
    pop: str = ""  # яскравий акцент на темному фоні (якщо highlight темний); порожньо = highlight
    pop_ink: str = ""

    def __post_init__(self):
        self.pop = self.pop or self.highlight
        self.pop_ink = self.pop_ink or self.highlight_ink


@dataclass
class Product:
    key: str  # зразок фото
    title: str  # назва серії в Маркеті
    category: str
    article: str
    name: str
    model: str
    tag: str
    pill: str
    detail: str  # другий рядок-плашка в обкладинці
    stats: list[tuple[str, str]]  # (назва, значення) × 3
    hero: tuple[str, str]  # велике число + підпис
    features: list[tuple[str, str, str]]  # (іконка, заголовок, опис) × 3
    footer: list[tuple[str, str]]  # (іконка, підпис) × 4
    specs: list[tuple[str, str]]  # 7 рядків таблиці
    kit: str
    guarantee: str
    dims: dict[str, str]  # Довжина, Ширина, Товщина, Вага, Монтаж
    apps: list[tuple[str, str]]  # (іконка, підпис) × 4
    price: str
    old_price: str
    discount: str
    label: str  # мітка в мінімалі
    sale_note: str = "Пропозиція діє до кінця місяця"
    extra: dict[str, str] = field(default_factory=dict)


def cover(th: Theme, p: Product) -> tuple[Template, dict]:
    e = [
        photo("Фото товару", 560, 150, 420, 500),
        text("Назва", 50, 40, 520, 170, p.name, 58, th.ink, family=th.title_font, line=1.04,
             b=bind("Назва", required=True), min_size=30),
        text("Модель", 50, 212, 520, 90, p.model, 72, th.accent, family=th.title_font, wrap=False,
             b=bind("Модель", required=True)),
        rect("Плашка", 50, 318, 520, 52, th.highlight, radius=26),
        text("Плашка — текст", 66, 318, 488, 52, p.pill, 24, th.highlight_ink, bold=True, align="center",
             valign="middle", wrap=False, b=bind("Плашка")),
    ]
    for i, x in enumerate((50, 320)):
        label, value = p.stats[i]
        e += [
            rect(f"Показник {i + 1} — фон", x, 390, 250, 150, th.accent, color2=th.accent2, radius=18,
                 shadow=Shadow(enabled=True, color=th.accent + "55", blur=18, offset_y=8)),
            text(f"Показник {i + 1}", x + 10, 400, 230, 80, value, 50, "#FFFFFF", family=th.title_font,
                 align="center", valign="middle", wrap=False, b=bind(label)),
            hline(f"Показник {i + 1} — риска", x + 30, 487, 190, "#FFFFFF99"),
            text(f"Показник {i + 1} — підпис", x + 10, 492, 230, 38, label, 26, "#FFFFFF", align="center",
                 valign="middle"),
        ]
    e += [
        rect("Деталь — рамка", 50, 560, 520, 50, "#FFFFFF", radius=25, stroke=Stroke(color=th.soft, width=2)),
        icon("Деталь — іконка", "коробка", 70, 569, 32, th.accent),
        text("Деталь", 112, 560, 440, 50, p.detail, 23, th.ink, valign="middle", b=bind("Деталь")),
    ]
    for i, y in enumerate((630, 720)):
        key, title, sub = p.features[i]
        e += [
            circle(f"Перевага {i + 1} — коло", 50, y, 74, th.accent),
            icon(f"Перевага {i + 1} — іконка", key, 67, y + 17, 40, "#FFFFFF"),
            text(f"Перевага {i + 1}", 142, y + 4, 420, 36, title, 28, th.ink, bold=True),
            text(f"Перевага {i + 1} — опис", 142, y + 40, 420, 32, sub, 23, th.muted),
        ]
    e.append(rect("Нижня панель", 40, 830, 920, 140, "#FFFFFF", radius=22, shadow=soft_shadow()))
    for i, (key, label) in enumerate(p.footer):
        cx = 40 + 115 + i * 230
        e.append(icon(f"Внизу {i + 1} — іконка", key, cx - 26, 846, 52, th.accent))
        e.append(text(f"Внизу {i + 1}", cx - 105, 904, 210, 56, label, 20, th.ink, align="center",
                      valign="middle", line=1.1))
        if i:
            e.append(vline("Розділювач", 40 + i * 230, 860, 90, th.soft))
    row = {"Назва": p.name, "Модель": p.model, "Плашка": p.pill, p.stats[0][0]: p.stats[0][1],
           p.stats[1][0]: p.stats[1][1], "Деталь": p.detail}
    return Template(name="обкладинка", elements=e, background=Background(color=th.light)), row


def specs(th: Theme, p: Product) -> tuple[Template, dict]:
    table = TableElement.create(len(p.specs), 2, name="Таблиця характеристик", x=50, y=360, width=480, height=440,
                                corner_radius=16, border=Stroke(color="#E2E8F0", width=2),
                                background=Paint(color="#FFFFFF"), stripe=Paint(color=th.light))
    table.col_widths = [1.0, 1.25]
    for r, (label, value) in enumerate(p.specs):
        a, b = table.cells[r]
        a.text = label
        a.style.font_size = b.style.font_size = 23
        a.style.color = th.muted
        b.style.color = th.accent
        b.style.bold = True
        a.padding = b.padding = 14
        b.binding = bind(label)
    e = [
        text("Заголовок", 50, 36, 620, 84, "Характеристики", 62, th.ink, family=th.title_font, wrap=False),
        text("Назва", 50, 120, 620, 44, f"{p.name} {p.model}", 28, th.muted, b=bind("Назва", required=True),
             wrap=False),
        rect("Показники — фон", 50, 185, 480, 150, th.accent, color2=th.accent2, radius=20,
             shadow=Shadow(enabled=True, color=th.accent + "55", blur=18, offset_y=8)),
        vline("Показники — розділювач", 290, 205, 110, "#FFFFFF88"),
    ]
    for i, x in enumerate((60, 300)):
        label, value = p.stats[i]
        e += [
            text(f"Показник {i + 1}", x, 195, 220, 80, value, 46, "#FFFFFF", family=th.title_font, align="center",
                 valign="middle", wrap=False, b=bind(f"{label} (показник)")),
            text(f"Показник {i + 1} — підпис", x, 275, 220, 40, label, 26, "#FFFFFF", align="center",
                 valign="middle"),
        ]
    e += [
        table,
        photo("Фото товару", 560, 140, 400, 330),
        text("Розміри — заголовок", 560, 490, 300, 44, "Розміри", 32, th.accent, bold=True),
        rect("Розміри — фон", 560, 540, 400, 260, "#FFFFFF", radius=18, stroke=Stroke(color="#E2E8F0", width=2)),
        photo("Креслення розмірів", 575, 555, 370, 230, column="Фото розмірів", required=False),
        rect("Нижня панель", 40, 830, 920, 140, "#FFFFFF", radius=22, shadow=soft_shadow()),
    ]
    for i, (key, label) in enumerate(p.footer[:3]):
        cx = 40 + 153 + i * 307
        e.append(icon(f"Внизу {i + 1} — іконка", key, cx - 28, 848, 56, th.accent))
        e.append(text(f"Внизу {i + 1}", cx - 140, 906, 280, 56, label, 22, th.ink, align="center",
                      valign="middle", line=1.1))
        if i:
            e.append(vline("Розділювач", 40 + i * 307, 860, 90, th.soft))
    row = {"Назва": f"{p.name} {p.model}", **dict(p.specs),
           **{f"{label} (показник)": value for label, value in p.stats[:2]}}
    return Template(name="характеристики", elements=e, background=Background(color="#F7F8FB")), row


def minimal(th: Theme, p: Product) -> tuple[Template, dict]:
    e = [
        photo("Фото товару", 80, 60, 840, 740),
        hline("Риска", 80, 840, 840, "#E5E7EB"),
        text("Назва", 80, 858, 660, 70, f"{p.name} {p.model}", 32, "#111827", bold=True,
             b=bind("Назва", required=True), min_size=20),
        text("Артикул", 80, 928, 500, 40, f"Арт. {p.article}", 22, "#6B7280", b=bind("Артикул", prefix="Арт. ")),
        rect("Мітка — фон", 740, 872, 180, 48, th.accent, radius=24),
        text("Мітка", 740, 872, 180, 48, p.label, 21, "#FFFFFF", bold=True, align="center", valign="middle",
             wrap=False, b=bind("Мітка")),
    ]
    row = {"Назва": f"{p.name} {p.model}", "Мітка": p.label}
    return Template(name="мінімал (білий фон)", elements=e, background=Background(color="#FFFFFF")), row


def dark(th: Theme, p: Product) -> tuple[Template, dict]:
    card = "#FFFFFF10"
    e = [
        circle("Сяйво під фото", 600, 170, 360, th.dark,
               shadow=Shadow(enabled=True, color=th.glow + "66", blur=90, offset_y=0)),
        photo("Фото товару", 540, 110, 440, 520),
        rect("Категорія — рамка", 50, 50, 240, 42, None, radius=21, stroke=Stroke(color=th.glow, width=2)),
        text("Категорія", 50, 50, 240, 42, p.tag, 20, th.glow, bold=True, align="center", valign="middle",
             wrap=False, spacing=2, b=bind("Категорія")),
        text("Назва", 50, 110, 490, 170, p.name, 46, "#FFFFFF", family=th.title_font, line=1.08,
             b=bind("Назва", required=True), min_size=26),
        text("Модель", 50, 285, 490, 80, p.model, 56, th.glow, family=th.title_font, wrap=False,
             b=bind("Модель", required=True)),
    ]
    for i, (label, value) in enumerate(p.stats):
        x = 50 + i * 168
        e += [
            rect(f"Параметр {i + 1} — фон", x, 390, 152, 112, card, radius=16, stroke=Stroke(color="#FFFFFF26", width=2)),
            text(f"Параметр {i + 1}", x + 6, 400, 140, 56, value, 30, "#FFFFFF", bold=True, align="center",
                 valign="middle", wrap=False, b=bind(label)),
            text(f"Параметр {i + 1} — підпис", x + 6, 458, 140, 32, label, 19, "#94A3B8", align="center",
                 valign="middle"),
        ]
    for i, (key, title, _sub) in enumerate(p.features):
        y = 540 + i * 85
        e += [
            circle(f"Перевага {i + 1} — коло", 50, y, 64, th.dark, stroke=Stroke(color=th.glow, width=2)),
            icon(f"Перевага {i + 1} — іконка", key, 64, y + 14, 36, th.glow),
            text(f"Перевага {i + 1}", 132, y, 400, 64, title, 26, "#E2E8F0", valign="middle",
                 b=bind(f"Перевага {i + 1}")),
        ]
    e += [
        rect("Нижня смуга", 0, 880, 1000, 120, "#00000055"),
        hline("Нижня смуга — лінія", 0, 880, 1000, th.glow, 3),
        text("Нижня смуга — текст", 50, 880, 900, 120, p.guarantee, 28, th.glow, bold=True, align="center",
             valign="middle", b=bind("Плашка")),
    ]
    row = {"Категорія": p.tag, "Назва": p.name, "Модель": p.model, **dict(p.stats),
           **{f"Перевага {i + 1}": f[1] for i, f in enumerate(p.features)}, "Плашка": p.guarantee}
    return Template(name="темний", elements=e, background=Background(color=th.dark)), row


def gradient(th: Theme, p: Product) -> tuple[Template, dict]:
    value, caption = p.hero
    e = [
        photo("Фото товару", 470, 130, 510, 520),
        text("Назва", 50, 50, 440, 140, p.name, 46, "#FFFFFF", family=th.title_font, line=1.05,
             b=bind("Назва", required=True), min_size=26),
        text("Головне число", 46, 190, 440, 130, value, 120, "#FFFFFF", family=th.title_font, line=1.0,
             wrap=False, b=bind("Головне число")),
        text("Головне число — підпис", 50, 318, 400, 50, caption, 32, "#FFFFFFDD", bold=True,
             b=bind("Головне число — підпис")),
    ]
    for i, (label, val) in enumerate(p.stats):
        y = 390 + i * 104
        e += [
            rect(f"Параметр {i + 1} — фон", 50, y, 400, 88, "#FFFFFF33", radius=18,
                 stroke=Stroke(color="#FFFFFF66", width=2)),
            text(f"Параметр {i + 1} — підпис", 72, y, 200, 88, label, 22, "#FFFFFFDD", valign="middle"),
            text(f"Параметр {i + 1}", 230, y, 206, 88, val, 32, "#FFFFFF", family=th.title_font, align="right",
                 valign="middle", wrap=False, b=bind(label)),
        ]
    e += [
        rect("Нижня панель", 40, 730, 920, 230, "#FFFFFF", radius=26, shadow=soft_shadow("33", 26, 10)),
        text("Підходить для — заголовок", 80, 752, 400, 40, "Підходить для:", 26, th.accent2, bold=True),
    ]
    for i, (key, label) in enumerate(p.apps):
        cx = 40 + 115 + i * 230
        e.append(circle(f"Застосування {i + 1} — коло", cx - 38, 798, 76, th.soft))
        e.append(icon(f"Застосування {i + 1} — іконка", key, cx - 22, 814, 44, th.accent2))
        e.append(text(f"Застосування {i + 1}", cx - 110, 880, 220, 64, label, 22, "#1F2937", align="center",
                      valign="middle", line=1.1, b=bind(f"Застосування {i + 1}")))
    row = {"Назва": p.name, "Головне число": value, "Головне число — підпис": caption, **dict(p.stats),
           **{f"Застосування {i + 1}": a[1] for i, a in enumerate(p.apps)}}
    return Template(name="яскравий", elements=e, background=Background(color=th.accent)), row


def kit(th: Theme, p: Product) -> tuple[Template, dict]:
    e = [
        rect("Шапка", 0, 0, 1000, 180, th.accent, color2=th.accent2, angle=0),
        text("Заголовок", 50, 34, 900, 84, "Комплектація", 62, "#FFFFFF", family=th.title_font, wrap=False),
        text("Назва", 50, 116, 900, 44, f"{p.name} {p.model}", 28, "#FFFFFFDD", b=bind("Назва", required=True),
             wrap=False),
        rect("Фото — картка", 40, 210, 460, 600, "#FFFFFF", radius=26, shadow=soft_shadow()),
        photo("Фото товару", 60, 240, 420, 540),
        rect("Список — картка", 530, 210, 430, 600, "#FFFFFF", radius=26, shadow=soft_shadow()),
        text("Список — заголовок", 570, 240, 360, 44, "У коробці:", 30, th.ink, bold=True),
        hline("Список — риска", 570, 296, 350, "#E2E8F0"),
        text("Список", 562, 316, 380, 470, p.kit, 25, "#1E293B", line=1.6, b=bind("Комплектація", required=True),
             min_size=16),
        rect("Плашка", 40, 840, 920, 120, th.ink, radius=60),
        icon("Плашка — іконка", "щит", 90, 870, 60, th.pop),
        text("Плашка — текст", 170, 840, 760, 120, p.guarantee, 28, "#FFFFFF", bold=True, valign="middle",
             b=bind("Плашка")),
    ]
    row = {"Назва": f"{p.name} {p.model}", "Комплектація": p.kit, "Плашка": p.guarantee}
    return Template(name="комплектація", elements=e, background=Background(color=th.light)), row


def dims(th: Theme, p: Product) -> tuple[Template, dict]:
    c = th.accent
    d = p.dims
    e = [
        text("Заголовок", 50, 36, 700, 84, "Розміри", 62, th.ink, family=th.title_font, wrap=False),
        text("Назва", 50, 116, 700, 44, f"{p.name} {p.model}", 28, th.muted, b=bind("Назва", required=True),
             wrap=False),
        photo("Фото товару", 190, 200, 580, 500),
        hline("Довжина — лінія", 190, 740, 580, c, 3),
        vline("Довжина — лівий упор", 190, 722, 36, c, 3),
        vline("Довжина — правий упор", 770, 722, 36, c, 3),
        rect("Довжина — фон", 400, 718, 160, 44, th.light),
        text("Довжина", 400, 718, 160, 44, f"{d['Довжина']} мм", 30, c, bold=True, align="center",
             valign="middle", wrap=False, b=bind("Довжина, мм", suffix=" мм")),
        vline("Висота — лінія", 830, 200, 500, c, 3),
        hline("Висота — верхній упор", 812, 200, 36, c, 3),
        hline("Висота — нижній упор", 812, 700, 36, c, 3),
        rect("Висота — фон", 750, 428, 160, 44, th.light, rotation=-90),
        text("Висота", 750, 428, 160, 44, f"{d['Ширина']} мм", 30, c, bold=True, align="center", valign="middle",
             wrap=False, rotation=-90, b=bind("Ширина, мм", suffix=" мм")),
    ]
    for i, (key, label, column, suffix) in enumerate([("лінійка", "Товщина", "Товщина, мм", " мм"),
                                                      ("коробка", "Вага", "Вага, г", " г"),
                                                      ("шестерня", "Монтаж", "Монтаж", "")]):
        x = 40 + i * 310
        source = column.split(",")[0]
        e += [
            rect(f"Картка {i + 1}", x, 820, 290, 140, "#FFFFFF", radius=20, shadow=soft_shadow()),
            icon(f"Картка {i + 1} — іконка", key, x + 24, 856, 56, c),
            text(f"Картка {i + 1} — підпис", x + 100, 842, 180, 36, label, 22, "#64748B"),
            text(f"Картка {i + 1} — значення", x + 100, 880, 180, 56, d[source] + suffix, 34, th.ink,
                 family=th.title_font, wrap=False, b=bind(column, suffix=suffix)),
        ]
    row = {"Назва": f"{p.name} {p.model}", "Довжина, мм": d["Довжина"], "Ширина, мм": d["Ширина"],
           "Товщина, мм": d["Товщина"], "Вага, г": d["Вага"], "Монтаж": d["Монтаж"]}
    return Template(name="розміри", elements=e, background=Background(color=th.light)), row


def advantages(th: Theme, p: Product) -> tuple[Template, dict]:
    e = [
        rect("Права частина", 470, 0, 530, 1000, th.dark),
        text("Назва", 40, 40, 400, 150, f"{p.name} {p.model}", 38, th.ink, family=th.title_font, line=1.08,
             b=bind("Назва", required=True), min_size=22),
        photo("Фото товару", 20, 230, 430, 560),
        rect("Ціна — фон", 40, 830, 380, 120, th.pop, radius=24),
        text("Ціна", 40, 830, 380, 120, f"{p.price} ₴", 56, th.pop_ink, family=th.title_font, align="center",
             valign="middle", wrap=False, b=bind("Ціна", suffix=" ₴")),
        text("Підзаголовок", 520, 60, 440, 40, "ЧОМУ ОБИРАЮТЬ", 24, th.pop, bold=True, spacing=3),
    ]
    for i, (key, title, sub) in enumerate(p.features, start=1):
        y = 130 + (i - 1) * 280
        e += [
            circle(f"Перевага {i} — коло", 520, y, 90, th.pop),
            icon(f"Перевага {i} — іконка", key, 543, y + 23, 44, th.pop_ink),
            text(f"Перевага {i} — номер", 870, y, 90, 50, f"0{i}", 36, "#FFFFFF33", family=th.title_font,
                 align="right", wrap=False),
            text(f"Перевага {i}", 520, y + 110, 440, 50, title, 32, "#FFFFFF", bold=True, b=bind(f"Перевага {i}"),
                 min_size=20),
            text(f"Перевага {i} — опис", 520, y + 160, 440, 80, sub, 23, "#FFFFFFAA", line=1.25,
                 b=bind(f"Опис {i}")),
        ]
        if i < 3:
            e.append(hline("Розділювач", 520, y + 255, 440, "#FFFFFF1F"))
    row = {"Назва": f"{p.name} {p.model}", "Ціна": p.price,
           **{f"Перевага {i}": f[1] for i, f in enumerate(p.features, start=1)},
           **{f"Опис {i}": f[2] for i, f in enumerate(p.features, start=1)}}
    return Template(name="три переваги", elements=e, background=Background(color="#FFFFFF")), row


def applications(th: Theme, p: Product) -> tuple[Template, dict]:
    e = [
        text("Заголовок", 50, 50, 520, 150, "Де\nзастосовується", 56, th.ink, family=th.title_font, line=1.0,
             min_size=34),
        text("Назва", 50, 210, 520, 80, f"{p.name} {p.model}", 30, th.accent, bold=True,
             b=bind("Назва", required=True)),
        circle("Фото — підкладка", 600, 30, 340, th.soft),
        photo("Фото товару", 580, 40, 380, 320),
    ]
    for i, (key, label) in enumerate(p.apps):
        x = 40 + (i % 2) * 470
        y = 390 + (i // 2) * 290
        e += [
            rect(f"Плитка {i + 1}", x, y, 450, 270, "#FFFFFF", radius=26, shadow=soft_shadow()),
            circle(f"Плитка {i + 1} — коло", x + 40, y + 40, 100, th.soft),
            icon(f"Плитка {i + 1} — іконка", key, x + 64, y + 64, 52, th.accent),
            text(f"Плитка {i + 1} — номер", x + 330, y + 40, 80, 60, f"0{i + 1}", 40, th.soft,
                 family=th.title_font, align="right", wrap=False),
            text(f"Застосування {i + 1}", x + 40, y + 160, 380, 90, label, 32, th.ink, bold=True, line=1.1,
                 b=bind(f"Застосування {i + 1}"), min_size=20),
        ]
    row = {"Назва": f"{p.name} {p.model}", **{f"Застосування {i + 1}": a[1] for i, a in enumerate(p.apps)}}
    return Template(name="застосування", elements=e, background=Background(color=th.light)), row


def sale(th: Theme, p: Product) -> tuple[Template, dict]:
    e = [
        rect("Смуга", -150, 330, 1300, 380, th.pop, rotation=-10),
        text("Назва", 50, 50, 640, 170, f"{p.name} {p.model}", 48, "#FFFFFF", family=th.title_font, line=1.05,
             b=bind("Назва", required=True), min_size=28),
        circle("Знижка — коло", 760, 40, 200, th.accent,
               shadow=Shadow(enabled=True, color=th.accent + "66", blur=30, offset_y=8)),
        text("Знижка", 760, 40, 200, 200, p.discount, 62, "#FFFFFF", family=th.title_font, align="center",
             valign="middle", wrap=False, b=bind("Знижка", required=True)),
        photo("Фото товару", 150, 230, 640, 520),
        rect("Ціна — фон", 40, 780, 560, 180, "#FFFFFF", radius=28, shadow=soft_shadow("40", 26, 10)),
        text("Ціна — підпис", 76, 798, 300, 36, "Ціна зараз", 24, "#6B7280"),
        text("Ціна", 70, 830, 520, 110, f"{p.price} ₴", 84, "#111827", family=th.title_font, valign="middle",
             wrap=False, b=bind("Ціна", suffix=" ₴", required=True)),
        text("Стара ціна", 640, 790, 320, 60, f"{p.old_price} ₴", 40, "#9CA3AF", bold=True, wrap=False,
             b=bind("Стара ціна", suffix=" ₴")),
        hline("Стара ціна — перекреслення", 640, 822, 150, th.accent, 4),
        text("Термін акції", 640, 860, 320, 100, p.sale_note, 24, "#FFFFFF", line=1.2, b=bind("Плашка")),
    ]
    row = {"Назва": f"{p.name} {p.model}", "Знижка": p.discount, "Ціна": p.price, "Стара ціна": p.old_price,
           "Плашка": p.sale_note}
    return Template(name="акція", elements=e, background=Background(color=th.dark)), row


LAYOUTS = [  # (макет, фон з ресурсів: суфікс ключа або None)
    (cover, "dots"), (specs, None), (minimal, None), (dark, "dark"), (gradient, "rays"),
    (kit, None), (dims, None), (advantages, None), (applications, None), (sale, None),
]


# --- Теми й товари ---------------------------------------------------------------------

THEMES = {
    "sensor": Theme("#0D9488", "#0F766E", "#042F2E", "#4B6B68", "#EEF7F6", "#CCF0EC", "#FBBF24", "#1F2937",
                    "#061A1C", "#2DD4BF", "Arial Black", (238, 247, 246), (150, 210, 200), (6, 26, 28),
                    (45, 212, 191), (20, 184, 166), (8, 110, 100), (180, 255, 240)),
    "led": Theme("#7C3AED", "#6D28D9", "#2E1065", "#5B4B7A", "#F5F3FF", "#E4DCFE", "#F472B6", "#FFFFFF",
                 "#0F0820", "#C084FC", "Segoe UI Black", (245, 243, 255), (196, 170, 250), (15, 8, 32),
                 (192, 132, 252), (168, 85, 247), (91, 33, 182), (240, 200, 255)),
    "motor": Theme("#D97706", "#B45309", "#1C1917", "#57534E", "#FFFBEB", "#FDECC8", "#1C1917", "#FBBF24",
                   "#171412", "#FBBF24", "Impact", (255, 251, 235), (240, 200, 120), (23, 20, 18),
                   (251, 191, 36), (251, 191, 36), (217, 119, 6), (255, 240, 180), pop="#FBBF24",
                   pop_ink="#1C1917"),
    "connector": Theme("#DC2626", "#B91C1C", "#1F2937", "#4B5563", "#FEF2F2", "#FDDADA", "#FACC15", "#1F2937",
                       "#180C0E", "#F87171", "Arial Black", (254, 242, 242), (245, 170, 170), (24, 12, 14),
                       (248, 113, 113), (239, 68, 68), (153, 27, 27), (255, 200, 200)),
}

PRODUCTS = [
    Product(
        key="sensor", title="Датчик", category="Датчики", article="HC-SR04",
        name="Ультразвуковий датчик відстані", model="HC-SR04", tag="ДАТЧИК",
        pill="2–400 см • 5 V • точність 3 мм", detail="Плата 45 × 20 мм, 4 виводи",
        stats=[("Дальність", "4 м"), ("Живлення", "5 V"), ("Кут", "15°")], hero=("400", "см дальності"),
        features=[("сигнал", "Безконтактне вимірювання", "від 2 см до 4 метрів"),
                  ("мікросхема", "Простий сигнал Trig/Echo", "працює з Arduino та ESP32"),
                  ("шестерня", "Стабільні показники", "точність до 3 мм")],
        footer=[("робот", "Роботи"), ("авто", "Паркувальні\nсистеми"), ("дім", "Розумний дім"),
                ("паяльник", "DIY-проєкти")],
        specs=[("Модель", "HC-SR04"), ("Дальність", "2–400 см"), ("Точність", "3 мм"), ("Кут огляду", "15°"),
               ("Живлення", "5 V DC"), ("Струм", "15 мА"), ("Розміри", "45 × 20 × 15 мм")],
        kit="✓ Датчик HC-SR04 — 1 шт\n✓ Кріплення — 1 шт\n✓ Дроти Dupont — 4 шт\n✓ Інструкція",
        guarantee="Гарантія 6 місяців • Перевірено перед відправкою",
        dims={"Довжина": "45", "Ширина": "20", "Товщина": "15", "Вага": "9", "Монтаж": "4 pin"},
        apps=[("робот", "Робототехніка"), ("авто", "Паркувальні\nдатчики"), ("дім", "Розумний дім"),
              ("сигнал", "Вимірювання\nрівня")],
        price="89", old_price="110", discount="-20%", label="Хіт продажів"),
    Product(
        key="led", title="Світлодіоди", category="Світлодіоди", article="LED-5MM-RGB100",
        name="Світлодіоди 5 мм, набір", model="RGB 100 шт", tag="СВІТЛОДІОДИ",
        pill="Червоні • Зелені • Сині • 20 мА", detail="Діаметр 5 мм, ніжки 28 мм",
        stats=[("Діаметр", "5 мм"), ("Струм", "20 мА"), ("Напруга", "2–3.2 V")], hero=("100", "штук у наборі"),
        features=[("блискавка", "Яскраве світіння", "до 20 000 мкд"),
                  ("годинник", "Довгий ресурс", "понад 50 000 годин"),
                  ("щит", "Низьке споживання", "лише 20 мА на діод")],
        footer=[("дім", "Підсвітка"), ("робот", "Індикація"), ("паяльник", "Макетування"), ("зірка", "Декор")],
        specs=[("Діаметр", "5 мм"), ("Кольори", "червоний, зелений, синій"), ("Напруга", "1.8–3.2 V"),
               ("Струм", "20 мА"), ("Яскравість", "до 20 000 мкд"), ("Кут світіння", "30°"), ("Кількість", "100 шт")],
        kit="✓ Червоні — 35 шт\n✓ Зелені — 35 шт\n✓ Сині — 30 шт\n✓ Резистори 220 Ом — 100 шт",
        guarantee="Відправка в день замовлення • Обмін 14 днів",
        dims={"Довжина": "34", "Ширина": "5", "Товщина": "5", "Вага": "0,3", "Монтаж": "THT"},
        apps=[("дім", "Підсвітка"), ("робот", "Індикація\nстанів"), ("паяльник", "Навчання\nта DIY"),
              ("зірка", "Декор і\nсвяткове світло")],
        price="149", old_price="199", discount="-25%", label="Набір 100 шт"),
    Product(
        key="motor", title="Мотор", category="Мотори", article="TT-MOTOR-148",
        name="Мотор-редуктор для робота", model="TT 1:48", tag="МОТОР",
        pill="3–6 V • 200 об/хв • подвійний вал", detail="Редуктор 1:48, вал 5,5 мм",
        stats=[("Напруга", "3–6 V"), ("Оберти", "200 об/хв"), ("Момент", "0,8 кг·см")], hero=("200", "обертів за хвилину"),
        features=[("шестерня", "Редуктор 1:48", "високий крутний момент"),
                  ("блискавка", "Живлення 3–6 V", "від акумулятора чи батарейок"),
                  ("робот", "Подвійний вал", "для коліс і механізмів")],
        footer=[("робот", "Роботи"), ("авто", "RC-машинки"), ("паяльник", "STEM-набори"), ("шестерня", "Механізми")],
        specs=[("Модель", "TT"), ("Передатне число", "1:48"), ("Напруга", "3–6 V"), ("Оберти", "200 об/хв"),
               ("Струм", "150 мА"), ("Момент", "0,8 кг·см"), ("Вага", "30 г")],
        kit="✓ Мотор-редуктор — 1 шт\n✓ Колесо 65 мм — 1 шт\n✓ Кріплення — 1 шт\n✓ Гвинти M3 — 2 шт",
        guarantee="Гарантія 3 місяці • Перевірено перед відправкою",
        dims={"Довжина": "70", "Ширина": "22", "Товщина": "37", "Вага": "30", "Монтаж": "Гвинти M3"},
        apps=[("робот", "Колісні роботи"), ("авто", "RC-машинки"), ("паяльник", "STEM-навчання"),
              ("шестерня", "Механізми та\nприводи")],
        price="75", old_price="95", discount="-20%", label="Для Arduino"),
    Product(
        key="connector", title="Роз'єм", category="Роз'єми", article="XT60-PAIR",
        name="Роз'єм силовий", model="XT60", tag="РОЗ'ЄМ",
        pill="60 A • 500 V • позолочені контакти", detail="Пара: «тато» + «мама»",
        stats=[("Струм", "60 A"), ("Пік", "180 A"), ("Кабель", "12 AWG")], hero=("60", "ампер тривало"),
        features=[("блискавка", "Високий струм", "до 60 A тривало"),
                  ("термометр", "Термостійкий нейлон", "не плавиться під час паяння"),
                  ("щит", "Захист від переполюсування", "форма не дає помилитися")],
        footer=[("дрон", "FPV-дрони"), ("батарея", "Акумулятори"), ("авто", "RC-моделі"), ("блискавка", "Живлення")],
        specs=[("Тип", "XT60 (тато + мама)"), ("Струм", "60 A"), ("Пік", "180 A"), ("Напруга", "500 V DC"),
               ("Опір контакту", "0,8 мОм"), ("Кабель", "12–14 AWG"), ("Матеріал", "нейлон PA")],
        kit="✓ Роз'єм «тато» — 1 шт\n✓ Роз'єм «мама» — 1 шт\n✓ Термоусадка — 2 шт",
        guarantee="Оригінальна якість • Відправка в день замовлення",
        dims={"Довжина": "16", "Ширина": "8", "Товщина": "16", "Вага": "4", "Монтаж": "Пайка"},
        apps=[("дрон", "FPV-дрони"), ("батарея", "Акумулятори\nLiPo"), ("авто", "RC-моделі"),
              ("блискавка", "Силові\nз'єднання")],
        price="39", old_price="49", discount="-20%", label="Пара тато+мама"),
]


def series_specs() -> list[Spec]:
    specs_out = []
    number = 11
    for product in PRODUCTS:
        theme = THEMES[product.key]
        for layout, bg in LAYOUTS:
            template, row = layout(theme, product)
            template.name = f"{product.title} — {template.name}"
            full_row = {"Артикул": product.article, **row}
            extra = {"Фото розмірів": product.key} if layout is specs else {}
            specs_out.append(Spec(f"{number:02d} {template.name}", product.category, template, full_row,
                                  product.key, background=f"{product.key}_{bg}" if bg else None,
                                  extra_photos=extra))
            number += 1
    return specs_out


def series_palettes() -> dict[str, dict]:
    return {key: {"light_rgb": t.light_rgb, "dot_rgb": t.dot_rgb, "dark_rgb": t.dark_rgb,
                  "accent_rgb": t.accent_rgb, "rays_top": t.rays_top, "rays_bottom": t.rays_bottom,
                  "rays_light": t.rays_light} for key, t in THEMES.items()}
