"""Ресурси для шаблонів Маркету: іконки (SVG), фони та зразки фото товарів (PNG).

Усе малюється кодом, тож шаблони можна перезібрати будь-коли: python tools/build_market.py
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none" stroke="#000" '
       'stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round">{}</svg>')

ICONS = {
    "ракета": '<path d="M32 6c9 6 14 16 14 28l-6 8H24l-6-8C18 22 23 12 32 6z"/><circle cx="32" cy="26" r="5"/>'
              '<path d="M24 42l-6 10 8-3M40 42l6 10-8-3M28 50l4 8 4-8"/>',
    "щит": '<path d="M32 6 52 13v15c0 14-9 24-20 30C21 52 12 42 12 28V13z"/><path d="M23 32l6 6 12-13"/>',
    "пульс": '<path d="M4 34h12l6-14 8 26 8-34 6 22h16"/>',
    "мікросхема": '<rect x="18" y="18" width="28" height="28" rx="3"/><path d="M24 18v-8M32 18v-8M40 18v-8'
                  'M24 54v-8M32 54v-8M40 54v-8M18 24h-8M18 32h-8M18 40h-8M54 24h-8M54 32h-8M54 40h-8"/>'
                  '<circle cx="25" cy="25" r="1.5"/>',
    "smd": '<rect x="6" y="40" width="52" height="12" rx="2"/><rect x="20" y="22" width="24" height="18" rx="2"/>'
           '<path d="M14 40v-6h6M50 40v-6h-6"/>',
    "коробка": '<path d="M8 20 32 8l24 12v24L32 56 8 44z"/><path d="M8 20l24 12 24-12M32 32v24"/>',
    "галочка": '<circle cx="32" cy="32" r="24"/><path d="M21 33l7 7 15-16"/>',
    "блискавка": '<path d="M36 4 14 36h16l-4 24 24-34H34z"/>',
    "лінійка": '<rect x="6" y="20" width="52" height="24" rx="3"/><path d="M14 20v8M22 20v12M30 20v8M38 20v12'
               'M46 20v8M54 20v8"/>',
    "термометр": '<path d="M26 40V12a6 6 0 0 1 12 0v28a10 10 0 1 1-12 0z"/><path d="M32 22v24"/>',
    "вилка": '<path d="M24 6v12M40 6v12M18 18h28v12a14 14 0 0 1-28 0z"/><path d="M32 44v14"/>',
    "шестерня": '<circle cx="32" cy="32" r="9"/><circle cx="32" cy="32" r="18"/><path d="M32 6v8M32 50v8M6 32h8'
                'M50 32h8M13.6 13.6l5.7 5.7M44.7 44.7l5.7 5.7M13.6 50.4l5.7-5.7M44.7 19.3l5.7-5.7"/>',
    "сигнал": '<path d="M8 24a34 34 0 0 1 48 0M16 32a22 22 0 0 1 32 0M24 40a10 10 0 0 1 16 0"/>'
              '<circle cx="32" cy="48" r="3"/>',
    "дрон": '<circle cx="14" cy="14" r="8"/><circle cx="50" cy="14" r="8"/><circle cx="14" cy="50" r="8"/>'
            '<circle cx="50" cy="50" r="8"/><rect x="24" y="24" width="16" height="16" rx="3"/>'
            '<path d="M20 20l4 4M44 20l-4 4M20 44l4-4M44 44l-4-4"/>',
    "авто": '<path d="M8 40l4-14c1-4 4-6 8-6h24c4 0 7 2 8 6l4 14v10H8z"/><circle cx="18" cy="44" r="4"/>'
            '<circle cx="46" cy="44" r="4"/><path d="M14 30h36"/>',
    "дім": '<path d="M8 30 32 10l24 20"/><path d="M14 26v28h36V26"/><path d="M27 54V40h10v14"/>',
    "зірка": '<path d="M32 6l7.6 16.4L58 25l-13 12.6L48 56 32 47.4 16 56l3-18.4L6 25l18.4-2.6z"/>',
    "доставка": '<path d="M4 16h34v28H4zM38 26h12l10 10v8H38z"/><circle cx="16" cy="48" r="5"/>'
                '<circle cx="48" cy="48" r="5"/>',
    "знижка": '<path d="M34 6h22v22L30 54 10 34z"/><circle cx="46" cy="16" r="3"/>',
    "годинник": '<circle cx="32" cy="32" r="24"/><path d="M32 18v14l10 6"/>',
    "батарея": '<rect x="6" y="20" width="48" height="24" rx="4"/><path d="M58 28v8"/>'
               '<path d="M34 24l-8 9h8l-4 8"/>',
    "паяльник": '<path d="M6 58 22 42M22 42l6-6 14 14-6 6zM34 30l18-18a4 4 0 0 1 6 6L40 36"/>',
    "робот": '<rect x="14" y="20" width="36" height="28" rx="6"/><circle cx="25" cy="33" r="4"/>'
             '<circle cx="39" cy="33" r="4"/><path d="M32 20v-8M28 12h8M8 30v8M56 30v8M24 54h16"/>',
}


def write_icons(folder: Path) -> dict[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    result = {}
    for name, body in ICONS.items():
        path = folder / f"{name}.svg"
        path.write_text(SVG.format(body), encoding="utf-8")
        result[name] = path
    return result


# --- Фони ------------------------------------------------------------------------

def background_dots(path: Path) -> None:
    """Світлий фон із сіткою крапок угорі праворуч (як на прикладі з конденсатором)."""
    img = Image.new("RGB", (1000, 1000), (243, 246, 251))
    d = ImageDraw.Draw(img)
    for y in range(20, 640, 22):
        for x in range(420, 1000, 22):
            fade = max(0.0, 1 - math.hypot(x - 880, y - 140) / 520)
            if fade <= 0:
                continue
            c = round(243 - 70 * fade)
            d.ellipse((x - 2.4, y - 2.4, x + 2.4, y + 2.4), fill=(c, c + 4, min(255, c + 16)))
    rnd = random.Random(3)
    for _ in range(7):  # кілька тонких «доріжок»
        y = rnd.randint(40, 300)
        x = rnd.randint(700, 860)
        d.line([(1000, y), (x + 60, y), (x, y + 50), (x - 80, y + 50)], fill=(200, 214, 236), width=3)
        d.ellipse((x - 86, y + 44, x - 74, y + 56), outline=(200, 214, 236), width=3, fill=(243, 246, 251))
    img.save(path)


def background_tech(path: Path) -> None:
    """Темний техно-фон: сітка, сяйво праворуч, світлі доріжки."""
    w = h = 1000
    img = Image.new("RGB", (w, h), (9, 14, 30))
    glow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(glow).ellipse((470, 100, 1050, 700), fill=170)
    glow = glow.filter(ImageFilter.GaussianBlur(140))
    img.paste(Image.new("RGB", (w, h), (20, 70, 120)), mask=glow)
    d = ImageDraw.Draw(img)
    for i in range(0, w, 50):
        d.line([(i, 0), (i, h)], fill=(18, 28, 55), width=1)
        d.line([(0, i), (w, i)], fill=(18, 28, 55), width=1)
    rnd = random.Random(11)
    for _ in range(12):
        x, y = rnd.randrange(500, 1000, 50), rnd.randrange(0, 1000, 50)
        length = rnd.randint(2, 5) * 50
        d.line([(x, y), (x + length, y)], fill=(34, 211, 238), width=2)
        d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(34, 211, 238))
    img.save(path)


def background_energy(path: Path) -> None:
    """Помаранчевий градієнт із променями — для акумуляторів і енергії."""
    w = h = 1000
    top, bottom = (255, 153, 0), (255, 72, 0)
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            t = (x + y) / (w + h)
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
    rays = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(rays)
    cx, cy = 760, 380
    for k in range(18):
        a = math.radians(k * 20)
        b = math.radians(k * 20 + 8)
        d.polygon([(cx, cy), (cx + 1500 * math.cos(a), cy + 1500 * math.sin(a)),
                   (cx + 1500 * math.cos(b), cy + 1500 * math.sin(b))], fill=40)
    rays = rays.filter(ImageFilter.GaussianBlur(6))
    img.paste(Image.new("RGB", (w, h), (255, 230, 160)), mask=rays)
    img.save(path)


# --- Зразки фото товарів (прозорий фон) ---------------------------------------------

S = 2  # малюємо вдвічі більше й зменшуємо — гладкі краї


def _finish(img: Image.Image, path: Path, size: tuple[int, int]) -> None:
    img.resize(size, Image.LANCZOS).save(path)


def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("arialbd.ttf", size)
    except OSError:
        return ImageFont.load_default()


def sample_capacitor(path: Path) -> None:
    w, h = 700 * S, 600 * S
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # тінь
    shadow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(shadow).ellipse((140 * S, 470 * S, 600 * S, 540 * S), fill=110)
    img.paste((40, 50, 70, 255), mask=shadow.filter(ImageFilter.GaussianBlur(25 * S)))
    # корпус: верх, бік, торці
    body_top = [(150, 230), (430, 150), (590, 260), (310, 340)]
    body_side = [(150, 230), (310, 340), (310, 470), (150, 360)]
    body_front = [(310, 340), (590, 260), (590, 390), (310, 470)]
    d.polygon([(x * S, y * S) for x, y in body_top], fill=(214, 186, 145))
    d.polygon([(x * S, y * S) for x, y in body_side], fill=(170, 140, 100))
    d.polygon([(x * S, y * S) for x, y in body_front], fill=(196, 166, 124))
    for (x0, x1) in ((150, 210), (530, 590)):  # металеві торці
        k0 = (x0 - 150) / 440
        k1 = (x1 - 150) / 440
        def pt(k, top):
            # точка на передньому ребрі між лівим і правим краєм
            fx = 310 + (590 - 310) * k
            fy = (340 + (260 - 340) * k) if top else (470 + (390 - 470) * k)
            return fx * S, fy * S
        d.polygon([pt(k0, True), pt(k1, True), pt(k1, False), pt(k0, False)], fill=(200, 204, 210))
        tx = lambda k: (150 + (430 - 150) * k, 230 + (150 - 230) * k)  # noqa: E731
        a, b = tx(k0), tx(k1)
        d.polygon([(a[0] * S, a[1] * S), (b[0] * S, b[1] * S), pt(k1, True), pt(k0, True)], fill=(226, 229, 234))
    _finish(img, path, (700, 600))


def sample_board(path: Path, color=(22, 120, 80)) -> None:
    w, h = 760 * S, 560 * S
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(shadow).rounded_rectangle((70 * S, 90 * S, 720 * S, 520 * S), 30 * S, fill=120)
    img.paste((20, 30, 40, 255), mask=shadow.filter(ImageFilter.GaussianBlur(22 * S)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((50 * S, 60 * S, 700 * S, 490 * S), 26 * S, fill=color)
    for x, y in ((80, 90), (670, 90), (80, 460), (670, 460)):
        d.ellipse(((x - 14) * S, (y - 14) * S, (x + 14) * S, (y + 14) * S), fill=(230, 200, 120))
        d.ellipse(((x - 7) * S, (y - 7) * S, (x + 7) * S, (y + 7) * S), fill=(0, 0, 0, 0))
    d.rounded_rectangle((300 * S, 190 * S, 470 * S, 360 * S), 10 * S, fill=(30, 30, 34))  # мікроконтролер
    for i in range(8):
        for side in (0, 1):
            y = (205 + i * 20) * S
            x = (290 if side == 0 else 470) * S
            d.rectangle((x, y, x + 10 * S, y + 8 * S), fill=(200, 200, 205))
    d.rounded_rectangle((110 * S, 120 * S, 240 * S, 210 * S), 8 * S, fill=(210, 212, 218))  # роз'єм USB
    d.rectangle((120 * S, 135 * S, 230 * S, 195 * S), fill=(150, 152, 160))
    for i in range(14):  # штирьова лінійка
        x = (130 + i * 36) * S
        d.rectangle((x, 420 * S, x + 22 * S, 452 * S), fill=(25, 25, 28))
        d.rectangle((x + 7 * S, 428 * S, x + 15 * S, 444 * S), fill=(220, 190, 90))
    for x, y in ((540, 150), (600, 150), (540, 230), (560, 320), (620, 320)):  # дрібні компоненти
        d.rectangle((x * S, y * S, (x + 34) * S, (y + 18) * S), fill=(240, 236, 220))
    d.ellipse((560 * S, 380 * S, 600 * S, 420 * S), fill=(30, 200, 255))  # світлодіод
    _finish(img, path, (760, 560))


def sample_battery(path: Path) -> None:
    w, h = 760 * S, 640 * S
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(shadow).rounded_rectangle((90 * S, 160 * S, 640 * S, 560 * S), 40 * S, fill=130)
    img.paste((30, 20, 10, 255), mask=shadow.filter(ImageFilter.GaussianBlur(26 * S)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((70 * S, 120 * S, 610 * S, 520 * S), 40 * S, fill=(28, 32, 44))
    d.rounded_rectangle((110 * S, 170 * S, 570 * S, 470 * S), 22 * S, fill=(40, 120, 255))
    font = _font(64 * S)
    d.text((140 * S, 210 * S), "5000mAh", font=font, fill=(255, 255, 255))
    d.text((140 * S, 300 * S), "4S 14.8V", font=_font(48 * S), fill=(220, 236, 255))
    d.text((140 * S, 380 * S), "100C LiPo", font=_font(40 * S), fill=(255, 210, 60))
    for i, color in enumerate(((220, 30, 30), (20, 20, 20))):  # дроти
        y = (250 + i * 40) * S
        d.line([(610 * S, y), (680 * S, y), (700 * S, y + 140 * S)], fill=color, width=22 * S, joint="curve")
    d.rounded_rectangle((660 * S, 400 * S, 740 * S, 470 * S), 10 * S, fill=(250, 200, 20))  # XT60
    _finish(img, path, (760, 640))


def _shadow(img: Image.Image, box, blur=24, alpha=120, color=(20, 30, 40)) -> None:
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse([v * S for v in box], fill=alpha)
    img.paste(color + (255,), mask=mask.filter(ImageFilter.GaussianBlur(blur * S)))


def sample_sensor(path: Path) -> None:
    """Ультразвуковий датчик: синя плата з двома «очима»."""
    w, h = 760 * S, 560 * S
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    _shadow(img, (80, 430, 700, 520))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((60 * S, 120 * S, 700 * S, 440 * S), 18 * S, fill=(24, 92, 190))
    for cx in (210, 550):
        d.ellipse(((cx - 125) * S, 155 * S, (cx + 125) * S, 405 * S), fill=(190, 196, 206))
        d.ellipse(((cx - 105) * S, 175 * S, (cx + 105) * S, 385 * S), fill=(120, 126, 138))
        for r in range(90, 10, -14):
            d.ellipse(((cx - r) * S, (280 - r) * S, (cx + r) * S, (280 + r) * S), outline=(70, 74, 84), width=4 * S)
    d.rounded_rectangle((330 * S, 150 * S, 430 * S, 200 * S), 6 * S, fill=(30, 30, 34))
    for i in range(4):
        x = (300 + i * 50) * S
        d.rectangle((x, 440 * S, x + 22 * S, 500 * S), fill=(220, 190, 90))
    _finish(img, path, (760, 560))


def sample_led(path: Path) -> None:
    """Три світлодіоди 5 мм з ніжками."""
    w, h = 700 * S, 640 * S
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    _shadow(img, (120, 560, 600, 620), alpha=90)
    d = ImageDraw.Draw(img)
    for i, (cx, color) in enumerate(((210, (255, 60, 60)), (350, (60, 220, 90)), (490, (60, 140, 255)))):
        top = 110 + (i % 2) * 40
        glow = Image.new("L", (w, h), 0)
        ImageDraw.Draw(glow).ellipse(((cx - 110) * S, (top - 40) * S, (cx + 110) * S, (top + 200) * S), fill=120)
        img.paste(color + (255,), mask=glow.filter(ImageFilter.GaussianBlur(40 * S)))
        d = ImageDraw.Draw(img)
        d.line([((cx - 22) * S, (top + 230) * S), ((cx - 22) * S, 600 * S)], fill=(190, 194, 200), width=8 * S)
        d.line([((cx + 22) * S, (top + 230) * S), ((cx + 22) * S, 560 * S)], fill=(190, 194, 200), width=8 * S)
        body = tuple(min(255, c + 60) for c in color) + (235,)
        d.rounded_rectangle(((cx - 62) * S, (top + 40) * S, (cx + 62) * S, (top + 220) * S), 10 * S, fill=body)
        d.ellipse(((cx - 62) * S, (top - 20) * S, (cx + 62) * S, (top + 100) * S), fill=body)
        d.rectangle(((cx - 72) * S, (top + 210) * S, (cx + 72) * S, (top + 232) * S), fill=body)
        d.ellipse(((cx - 26) * S, (top + 10) * S, (cx - 4) * S, (top + 60) * S), fill=(255, 255, 255, 170))
    _finish(img, path, (700, 640))


def sample_motor(path: Path) -> None:
    """Жовтий мотор-редуктор з білим валом."""
    w, h = 780 * S, 560 * S
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    _shadow(img, (70, 440, 720, 520))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((70 * S, 140 * S, 470 * S, 440 * S), 30 * S, fill=(250, 200, 30))  # редуктор
    d.rounded_rectangle((90 * S, 160 * S, 450 * S, 200 * S), 12 * S, fill=(255, 222, 90))
    for x, y in ((120, 380), (420, 380), (120, 250), (420, 250)):
        d.ellipse(((x - 14) * S, (y - 14) * S, (x + 14) * S, (y + 14) * S), fill=(180, 140, 10))
    d.rounded_rectangle((440 * S, 200 * S, 720 * S, 380 * S), 60 * S, fill=(196, 200, 208))  # двигун
    d.rectangle((440 * S, 200 * S, 520 * S, 380 * S), fill=(176, 180, 188))
    d.ellipse((680 * S, 270 * S, 740 * S, 310 * S), fill=(150, 154, 162))
    d.rounded_rectangle((250 * S, 30 * S, 300 * S, 160 * S), 8 * S, fill=(245, 245, 245))  # вал
    d.rectangle((262 * S, 30 * S, 288 * S, 160 * S), fill=(225, 225, 225))
    for i, color in enumerate(((220, 30, 30), (20, 20, 20))):
        y = (235 + i * 90) * S
        d.line([(720 * S, y), (760 * S, y + 30 * S)], fill=color, width=12 * S)
    _finish(img, path, (780, 560))


def sample_connector(path: Path) -> None:
    """Пара жовтих силових роз'ємів (тато/мама)."""
    w, h = 760 * S, 560 * S
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    _shadow(img, (80, 450, 690, 520))
    d = ImageDraw.Draw(img)
    for i, x0 in enumerate((80, 410)):
        y0 = 150 + i * 40
        d.polygon([((x0 + 30) * S, y0 * S), ((x0 + 270) * S, y0 * S), ((x0 + 270) * S, (y0 + 260) * S),
                   (x0 * S, (y0 + 260) * S), (x0 * S, (y0 + 40) * S)], fill=(250, 196, 20))
        d.polygon([((x0 + 40) * S, (y0 + 20) * S), ((x0 + 250) * S, (y0 + 20) * S), ((x0 + 250) * S, (y0 + 70) * S),
                   ((x0 + 20) * S, (y0 + 70) * S)], fill=(255, 222, 90))
        for cx in (x0 + 85, x0 + 185):
            d.ellipse(((cx - 38) * S, (y0 + 110) * S, (cx + 38) * S, (y0 + 186) * S), fill=(120, 90, 10))
            d.ellipse(((cx - 24) * S, (y0 + 124) * S, (cx + 24) * S, (y0 + 172) * S), fill=(214, 176, 90))
        d.text(((x0 + 100) * S, (y0 + 200) * S), "+  −", font=_font(34 * S), fill=(130, 95, 10))
    _finish(img, path, (760, 560))


def background_rays(path: Path, top: tuple, bottom: tuple, ray: tuple) -> None:
    """Градієнт із м'якими променями — для «яскравої» картки."""
    w = h = 1000
    grad = Image.linear_gradient("L").rotate(45, expand=False).resize((w, h))
    img = Image.composite(Image.new("RGB", (w, h), bottom), Image.new("RGB", (w, h), top), grad)
    rays = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(rays)
    cx, cy = 760, 380
    for k in range(18):
        a, b = math.radians(k * 20), math.radians(k * 20 + 8)
        d.polygon([(cx, cy), (cx + 1500 * math.cos(a), cy + 1500 * math.sin(a)),
                   (cx + 1500 * math.cos(b), cy + 1500 * math.sin(b))], fill=40)
    img.paste(Image.new("RGB", (w, h), ray), mask=rays.filter(ImageFilter.GaussianBlur(6)))
    img.save(path)


def background_dark(path: Path, base: tuple, accent: tuple) -> None:
    """Темний фон із сіткою й сяйвом у кольорі акценту."""
    w = h = 1000
    img = Image.new("RGB", (w, h), base)
    glow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(glow).ellipse((470, 100, 1050, 700), fill=150)
    img.paste(Image.new("RGB", (w, h), tuple(round(c * 0.45) for c in accent)),
              mask=glow.filter(ImageFilter.GaussianBlur(140)))
    d = ImageDraw.Draw(img)
    line = tuple(min(255, c + 10) for c in base)
    for i in range(0, w, 50):
        d.line([(i, 0), (i, h)], fill=line, width=1)
        d.line([(0, i), (w, i)], fill=line, width=1)
    rnd = random.Random(sum(accent))
    for _ in range(12):
        x, y = rnd.randrange(500, 1000, 50), rnd.randrange(0, 1000, 50)
        d.line([(x, y), (x + rnd.randint(2, 5) * 50, y)], fill=accent, width=2)
        d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=accent)
    img.save(path)


def background_dots_tinted(path: Path, base: tuple, dot: tuple) -> None:
    img = Image.new("RGB", (1000, 1000), base)
    d = ImageDraw.Draw(img)
    for y in range(20, 640, 22):
        for x in range(420, 1000, 22):
            fade = max(0.0, 1 - math.hypot(x - 880, y - 140) / 520)
            if fade > 0:
                c = tuple(round(b + (t - b) * fade) for b, t in zip(base, dot))
                d.ellipse((x - 2.4, y - 2.4, x + 2.4, y + 2.4), fill=c)
    img.save(path)


SERIES_SAMPLES = {"sensor": sample_sensor, "led": sample_led, "motor": sample_motor, "connector": sample_connector}


def build_series_assets(folder: Path, palettes: dict[str, dict]) -> dict[str, Path]:
    """Зразки фото й фони для серії: palettes = {ключ товару: {"base", "accent", "dark", "light", "rays"…}}."""
    folder.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    for key, draw in SERIES_SAMPLES.items():
        out[key] = folder / f"зразок-{key}.png"
        draw(out[key])
    for key, p in palettes.items():
        out[f"{key}_dots"] = folder / f"фон-{key}-крапки.png"
        background_dots_tinted(out[f"{key}_dots"], p["light_rgb"], p["dot_rgb"])
        out[f"{key}_dark"] = folder / f"фон-{key}-темний.png"
        background_dark(out[f"{key}_dark"], p["dark_rgb"], p["accent_rgb"])
        out[f"{key}_rays"] = folder / f"фон-{key}-промені.png"
        background_rays(out[f"{key}_rays"], p["rays_top"], p["rays_bottom"], p["rays_light"])
    return out


def build_assets(folder: Path) -> dict[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    out = {
        "bg_dots": folder / "фон-крапки-світлий.png",
        "bg_tech": folder / "фон-техно-темний.png",
        "bg_energy": folder / "фон-енергія.png",
        "capacitor": folder / "зразок-конденсатор.png",
        "board": folder / "зразок-модуль.png",
        "battery": folder / "зразок-акумулятор.png",
    }
    background_dots(out["bg_dots"])
    background_tech(out["bg_tech"])
    background_energy(out["bg_energy"])
    sample_capacitor(out["capacitor"])
    sample_board(out["board"])
    sample_battery(out["battery"])
    return out
