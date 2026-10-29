"""Фото товарів: збереження в tables/images з одного з трьох джерел.

1. Картинка, вставлена в клітинку Excel (див. xlsx_images).
2. Ім'я файлу (або повний шлях) + папка з фото.
3. Посилання http(s) — файл завантажується.
"""
from __future__ import annotations

import hashlib
import io
import re
import urllib.request
from collections.abc import Callable
from pathlib import Path

from PIL import Image, UnidentifiedImageError

MAX_DOWNLOAD = 25 * 1024 * 1024
DOWNLOAD_TIMEOUT = 20
FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif", "BMP": ".bmp"}

Downloader = Callable[[str], bytes]


class PhotoError(Exception):
    pass


def is_url(value: str) -> bool:
    return value.strip().lower().startswith(("http://", "https://"))


def safe_name(text: str) -> str:
    """Частина імені файлу без заборонених у Windows символів."""
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", text.strip())
    return text.strip(" .")[:80] or "photo"


def image_extension(data: bytes) -> str:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
            fmt = image.format
    except (UnidentifiedImageError, OSError, SyntaxError) as e:
        raise PhotoError("Файл не є зображенням") from e
    if fmt not in FORMATS:
        raise PhotoError(f"Непідтримуваний формат зображення: {fmt}")
    return FORMATS[fmt]


def store_image(data: bytes, images: Path, article: str, column: str) -> str:
    """Зберігає фото як «<артикул>_<стовпець>.<розширення>». Повертає ім'я файлу.

    Якщо такий самий файл (байт у байт) уже є — новий не створюється, повертається наявний:
    одне фото на кілька товарів зберігається один раз.
    """
    ext = image_extension(data)
    images.mkdir(parents=True, exist_ok=True)
    same = find_same(images, data)
    if same is not None:
        return same.name
    base = f"{safe_name(article)}_{safe_name(column)}"
    target = images / f"{base}{ext}"
    n = 2
    while target.exists():  # ім'я зайняте іншим фото (може бути потрібне іншим товарам)
        target = images / f"{base} ({n}){ext}"
        n += 1
    target.write_bytes(data)
    return target.name


def find_same(images: Path, data: bytes) -> Path | None:
    """Файл з точно таким самим вмістом (спершу порівнюється розмір — це швидко)."""
    digest = None
    for path in images.iterdir():
        if not path.is_file() or path.stat().st_size != len(data):
            continue
        digest = digest or hashlib.sha256(data).digest()
        if hashlib.sha256(path.read_bytes()).digest() == digest:
            return path
    return None


def cleanup_unused(images: Path, used: set[str]) -> int:
    """Видаляє з папки фото шаблону файли, на які вже не посилається жоден товар."""
    removed = 0
    if not images.is_dir():
        return removed
    for path in images.iterdir():
        if path.is_file() and path.name not in used:
            path.unlink()
            removed += 1
    return removed


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 CardGen"})
    try:
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
            data = response.read(MAX_DOWNLOAD + 1)
    except OSError as e:
        raise PhotoError(f"Не вдалося завантажити {url}: {e}") from e
    if len(data) > MAX_DOWNLOAD:
        raise PhotoError(f"Файл за посиланням більший за {MAX_DOWNLOAD // 1024 // 1024} МБ")
    return data


def find_file(value: str, search_dirs: list[Path]) -> Path | None:
    """Повний шлях або ім'я файлу в одній із папок (без урахування регістру)."""
    candidate = Path(value.strip().strip('"'))
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None
    for folder in search_dirs:
        direct = folder / candidate
        if direct.is_file():
            return direct
        if folder.is_dir():
            wanted = candidate.name.casefold()
            for path in folder.iterdir():
                if path.is_file() and path.name.casefold() == wanted:
                    return path
    return None


def fetch_photo(value: str, search_dirs: list[Path], downloader: Downloader = download) -> bytes:
    """Байти фото за значенням клітинки (ім'я файлу, шлях або посилання)."""
    value = value.strip()
    if is_url(value):
        return downloader(value)
    path = find_file(value, search_dirs)
    if path is None:
        raise PhotoError(f"Фото «{value}» не знайдено")
    return path.read_bytes()
