"""Експорт готових карток у JPEG.

Вимоги майданчиків (офіційні довідки, перевірено 28.10.2026):
- Prom.ua: JPG/GIF/PNG, файл до 10 МБ, найбільша сторона до 1280 px (більші стискаються),
  рекомендовано квадрат 1280×1280.
- Rozetka: JPEG/GIF/PNG/WebP, від 400×400 до 4000×4000 px, оптимально 1000×1000,
  файл до 10 МБ, RGB/sRGB.
Спільний профіль «Пром і Розетка»: JPEG, RGB, сторона 400…1280 px, файл до 10 МБ.
"""
from __future__ import annotations

import io
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image
from PySide6.QtGui import QImage

from .data.photos import safe_name
from .model import Template
from .products import Products
from .storage import Workspace


@dataclass(frozen=True)
class Preset:
    title: str
    max_side: int
    min_side: int
    max_bytes: int


PRESETS = {
    "prom_rozetka": Preset("Пром і Розетка", max_side=1280, min_side=400, max_bytes=10 * 1024 * 1024),
}
MIN_QUALITY = 60
PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


@dataclass
class ExportReport:
    files: list[Path] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # пропущені картки з причиною
    warnings: list[str] = field(default_factory=list)
    cancelled: bool = False


# --- Ім'я файлу ------------------------------------------------------------------------

def file_stem(mask: str, products: Products, index: int) -> str:
    """Ім'я файлу (без розширення) за маскою шаблону."""
    template = products.template
    row = products.dataset.rows[index]

    def value(match: re.Match) -> str:
        key = match.group(1).strip()
        if key == "№":
            return str(template.export.number)
        if key.casefold() == "шаблон":
            return template.name
        if key.casefold() == "n":
            return str(index + 1)
        return products.dataset.value(row, key)

    text = PLACEHOLDER_RE.sub(value, mask or "{Артикул}_{№}").strip(" ._-")
    return safe_name(text) if text else f"картка-{index + 1}"


def unique_path(folder: Path, stem: str, taken: set[str]) -> Path:
    """Вільне ім'я в межах одного експорту (старі файли в папці перезаписуються)."""
    name = f"{stem}.jpg"
    n = 2
    while name.casefold() in taken:
        name = f"{stem} ({n}).jpg"
        n += 1
    taken.add(name.casefold())
    return folder / name


# --- JPEG --------------------------------------------------------------------------------

def to_pil(image: QImage) -> Image.Image:
    """QImage -> RGB (прозорість — на білому, як побачить майданчик)."""
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    pil = Image.frombuffer("RGBA", (image.width(), image.height()), bytes(image.constBits()),
                           "raw", "RGBA", image.bytesPerLine(), 1)
    background = Image.new("RGB", pil.size, (255, 255, 255))
    background.paste(pil, mask=pil.getchannel("A"))
    return background


def encode_jpeg(image: QImage, quality: int, max_bytes: int) -> tuple[bytes, int]:
    """JPEG не більший за max_bytes: якість знижується кроками до MIN_QUALITY."""
    pil = to_pil(image)
    quality = max(MIN_QUALITY, min(100, quality))
    while True:
        buffer = io.BytesIO()
        pil.save(buffer, "JPEG", quality=quality, optimize=True, progressive=True, subsampling=0
                 if quality >= 90 else 2)
        data = buffer.getvalue()
        if len(data) <= max_bytes or quality <= MIN_QUALITY:
            return data, quality
        quality -= 5


def export_scale(template: Template, preset: Preset) -> float:
    """Відмальовуємо одразу в потрібному розмірі (чіткіше, ніж стискати готову картинку)."""
    side = max(template.width, template.height)
    return min(1.0, preset.max_side / side)


# --- Експорт -----------------------------------------------------------------------------

def plan_count(workspace: Workspace, category_id: str, template_ids: list[str]) -> int:
    return sum(len(Products(workspace, category_id, tid)) for tid in template_ids)


def export_cards(workspace: Workspace, category_id: str, template_ids: list[str], folder: Path, *,
                 skip_errors: bool = False,
                 progress: Callable[[int, str], bool] | None = None) -> ExportReport:
    """Експортує всі товари вибраних шаблонів у папку.

    progress(зроблено, поточний файл) -> False, щоб зупинити.
    skip_errors — пропускати картки з помилками в даних.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    report = ExportReport()
    taken: set[str] = set()
    done = 0
    numbers: dict[int, str] = {}
    for template_id in template_ids:
        products = Products(workspace, category_id, template_id)
        template = products.template
        preset = PRESETS.get(template.export.preset, PRESETS["prom_rozetka"])
        other = numbers.setdefault(template.export.number, template.name)
        if other != template.name and "{№}" in template.export.filename_mask:
            report.warnings.append(f"Шаблони «{other}» і «{template.name}» мають однаковий номер "
                                   f"{template.export.number} — до імен файлів додано (2), (3)…")
        scale = export_scale(template, preset)
        side = round(max(template.width, template.height) * scale)
        if side < preset.min_side:
            report.warnings.append(f"Шаблон «{template.name}»: {side} px — менше за мінімум "
                                   f"{preset.min_side} px для {preset.title}")
        for index in range(len(products)):
            article = products.article(index)
            errors = [i.message for i in products.row_issues(index) if i.level == "error"]
            if errors and skip_errors:
                report.skipped.append(f"{template.name} · {article}: {'; '.join(errors)}")
            else:
                path = unique_path(folder, file_stem(template.export.filename_mask, products, index), taken)
                if progress is not None and not progress(done, path.name):
                    report.cancelled = True
                    return report
                rendered = products.render(index, scale)
                data, quality = encode_jpeg(rendered.image, template.export.jpeg_quality, preset.max_bytes)
                path.write_bytes(data)
                report.files.append(path)
                if quality < template.export.jpeg_quality:
                    report.warnings.append(f"{path.name}: якість знижено до {quality}, щоб файл був "
                                           f"до {preset.max_bytes // 1024 // 1024} МБ")
                if rendered.overflow:
                    report.warnings.append(f"{path.name}: текст не вміщується в деяких блоках")
                if errors:
                    report.warnings.append(f"{path.name}: помилки в даних — {'; '.join(errors)}")
            done += 1
    if progress is not None:
        progress(done, "")
    return report
