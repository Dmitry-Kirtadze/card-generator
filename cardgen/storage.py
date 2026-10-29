"""Зберігання категорій, шаблонів і спільної бібліотеки на диску.

Структура робочої папки:

    <workspace>/
        library/                 спільна бібліотека для всіх категорій
            fonts/  icons/  backgrounds/
        categories/
            <id категорії>/
                category.json
                assets/          ресурси лише цієї категорії
                templates/
                    <id шаблону>/
                        template.json
                        tables/  завантажені таблиці даних
        trash/                   видалене (можна відновити вручну)

Папки названі за id, а назви зберігаються в JSON — так перейменування
не чіпає файлову систему, і кирилиця в назвах не створює проблем.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path, PurePosixPath

from PIL import ImageFont

from .model import Category, Template, new_id
from .model.serialization import (
    SchemaError,
    category_from_dict,
    category_to_dict,
    template_from_dict,
    template_to_dict,
)

log = logging.getLogger(__name__)

LIBRARY_SECTIONS = ("fonts", "icons", "backgrounds")

# Посилання на ресурс у шаблоні: "library:icons/rocket.png" або "category:assets/photo.png"
LIBRARY_PREFIX = "library:"
CATEGORY_PREFIX = "category:"


LIBRARY_EXTENSIONS = {
    "fonts": (".ttf", ".otf"),
    "icons": (".png", ".svg", ".jpg", ".jpeg", ".webp"),
    "backgrounds": (".png", ".jpg", ".jpeg", ".webp"),
}
TABLE_EXTENSIONS = (".xlsx", ".csv")
RECENT_COLORS_LIMIT = 16


class StorageError(Exception):
    pass


def library_ref(section: str, filename: str) -> str:
    return f"{LIBRARY_PREFIX}{section}/{filename}"


def font_family(path: Path) -> str:
    """Назва сімейства шрифту з файлу (як її бачить редактор)."""
    try:
        family, _style = ImageFont.truetype(str(path), 12).getname()
    except OSError as e:
        raise StorageError(f"Файл {Path(path).name} не є шрифтом: {e}") from e
    if not family:
        raise StorageError(f"У шрифті {Path(path).name} немає назви сімейства")
    return family


def write_json_atomic(path: Path, data: dict) -> None:
    """Пише JSON так, щоб збій посеред запису не зіпсував старий файл."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise StorageError(f"Не вдалося прочитати {path}: {e}") from e
    if not isinstance(data, dict):
        raise StorageError(f"Некоректний вміст {path}")
    return data


def _clean_name(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise StorageError("Назва не може бути порожньою")
    return name


def unique_name(name: str, taken: set[str], label: str = "копія") -> str:
    """«Назва (копія)», «Назва (копія 2)»… — перша вільна. taken — у casefold."""
    candidate = f"{name} ({label})"
    n = 2
    while candidate.casefold() in taken:
        candidate = f"{name} ({label} {n})"
        n += 1
    return candidate


def unique_file(folder: Path, filename: str) -> Path:
    """Вільне ім'я файлу в папці: logo.png, logo (2).png, logo (3).png…"""
    target = folder / filename
    stem, suffix = target.stem, target.suffix
    n = 2
    while target.exists():
        target = folder / f"{stem} ({n}){suffix}"
        n += 1
    return target


class Workspace:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.library_dir = self.root / "library"
        self.categories_dir = self.root / "categories"
        self.trash_dir = self.root / "trash"
        for section in LIBRARY_SECTIONS:
            (self.library_dir / section).mkdir(parents=True, exist_ok=True)
        self.categories_dir.mkdir(parents=True, exist_ok=True)

    # --- Категорії --------------------------------------------------------

    def category_dir(self, category_id: str) -> Path:
        path = self.categories_dir / category_id
        if not (path / "category.json").is_file():
            raise StorageError(f"Категорію {category_id} не знайдено")
        return path

    def list_categories(self) -> list[Category]:
        result = []
        for folder in self.categories_dir.iterdir():
            meta = folder / "category.json"
            if not meta.is_file():
                continue
            try:
                result.append(category_from_dict(read_json(meta)))
            except (StorageError, SchemaError) as e:
                log.warning("Пропущено пошкоджену категорію %s: %s", folder, e)
        # вбудовані (Маркет) — першими
        result.sort(key=lambda c: (not c.protected, c.created_at, c.name.casefold()))
        return result

    def get_category(self, category_id: str) -> Category:
        return category_from_dict(read_json(self.category_dir(category_id) / "category.json"))

    def create_category(self, name: str) -> Category:
        name = _clean_name(name)
        self._ensure_unique_category_name(name)
        category = Category(name=name, created_at=datetime.now().isoformat(timespec="seconds"))
        folder = self.categories_dir / category.id
        (folder / "assets").mkdir(parents=True)
        (folder / "templates").mkdir()
        self.save_category(category)
        return category

    def rename_category(self, category_id: str, new_name: str) -> Category:
        new_name = _clean_name(new_name)
        category = self.get_category(category_id)
        if category.protected:
            raise StorageError(f"Категорію «{category.name}» не можна перейменувати")
        if new_name.casefold() != category.name.casefold():
            self._ensure_unique_category_name(new_name)
        category.name = new_name
        self.save_category(category)
        return category

    def delete_category(self, category_id: str) -> Path:
        category = self.get_category(category_id)
        if category.protected:
            raise StorageError(f"Категорію «{category.name}» не можна видалити")
        return self._move_to_trash(self.category_dir(category_id))

    def duplicate_category(self, category_id: str, new_name: str | None = None) -> Category:
        source = self.get_category(category_id)
        taken = {c.name.casefold() for c in self.list_categories()}
        name = _clean_name(new_name) if new_name else unique_name(source.name, taken)
        if name.casefold() in taken:
            raise StorageError(f"Категорія «{name}» вже існує")
        copy = Category(name=name, created_at=datetime.now().isoformat(timespec="seconds"))
        shutil.copytree(self.category_dir(category_id), self.categories_dir / copy.id)
        self.save_category(copy)
        return copy

    def save_category(self, category: Category) -> None:
        write_json_atomic(
            self.categories_dir / category.id / "category.json", category_to_dict(category)
        )

    def _ensure_unique_category_name(self, name: str) -> None:
        if any(c.name.casefold() == name.casefold() for c in self.list_categories()):
            raise StorageError(f"Категорія «{name}» вже існує")

    # --- Шаблони ----------------------------------------------------------

    def template_dir(self, category_id: str, template_id: str) -> Path:
        path = self.category_dir(category_id) / "templates" / template_id
        if not (path / "template.json").is_file():
            raise StorageError(f"Шаблон {template_id} не знайдено")
        return path

    def list_templates(self, category_id: str) -> list[Template]:
        result = []
        for folder in sorted((self.category_dir(category_id) / "templates").iterdir()):
            meta = folder / "template.json"
            if not meta.is_file():
                continue
            try:
                result.append(template_from_dict(read_json(meta)))
            except (StorageError, SchemaError) as e:
                log.warning("Пропущено пошкоджений шаблон %s: %s", folder, e)
        result.sort(key=lambda t: t.name.casefold())
        return result

    def load_template(self, category_id: str, template_id: str) -> Template:
        path = self.template_dir(category_id, template_id) / "template.json"
        try:
            return template_from_dict(read_json(path))
        except SchemaError as e:
            raise StorageError(f"Шаблон {path} пошкоджено: {e}") from e

    def create_template(self, category_id: str, name: str, width: int = 1000,
                        height: int = 1000) -> Template:
        name = _clean_name(name)
        self._ensure_unique_template_name(category_id, name)
        template = Template(name=name, width=width, height=height)
        # номер картинки у назві файлу: наступний за найбільшим у категорії
        template.export.number = max((t.export.number for t in self.list_templates(category_id)), default=0) + 1
        self.save_template(category_id, template)
        return template

    def save_template(self, category_id: str, template: Template) -> None:
        folder = self.category_dir(category_id) / "templates" / template.id
        (folder / "tables").mkdir(parents=True, exist_ok=True)
        write_json_atomic(folder / "template.json", template_to_dict(template))

    def rename_template(self, category_id: str, template_id: str, new_name: str) -> Template:
        new_name = _clean_name(new_name)
        template = self.load_template(category_id, template_id)
        if new_name.casefold() != template.name.casefold():
            self._ensure_unique_template_name(category_id, new_name)
        template.name = new_name
        self.save_template(category_id, template)
        return template

    def delete_template(self, category_id: str, template_id: str) -> Path:
        return self._move_to_trash(self.template_dir(category_id, template_id))

    def duplicate_template(self, category_id: str, template_id: str) -> Template:
        source_dir = self.template_dir(category_id, template_id)
        template = self.load_template(category_id, template_id)
        taken = {t.name.casefold() for t in self.list_templates(category_id)}
        template.name = unique_name(template.name, taken)
        template.id = new_id()
        target_dir = self.category_dir(category_id) / "templates" / template.id
        shutil.copytree(source_dir, target_dir)
        self.save_template(category_id, template)
        return template

    def _ensure_unique_template_name(self, category_id: str, name: str) -> None:
        if any(t.name.casefold() == name.casefold() for t in self.list_templates(category_id)):
            raise StorageError(f"Шаблон «{name}» вже існує в цій категорії")

    # --- Таблиці даних шаблону -------------------------------------------

    def tables_dir(self, category_id: str, template_id: str) -> Path:
        path = self.template_dir(category_id, template_id) / "tables"
        path.mkdir(exist_ok=True)
        return path

    def list_tables(self, category_id: str, template_id: str) -> list[Path]:
        folder = self.tables_dir(category_id, template_id)
        files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in TABLE_EXTENSIONS]
        return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

    def add_table(self, category_id: str, template_id: str, source: Path) -> Path:
        source = Path(source)
        if source.suffix.lower() not in TABLE_EXTENSIONS:
            raise StorageError(f"Таблиця має бути у форматі {', '.join(TABLE_EXTENSIONS)}")
        target = unique_file(self.tables_dir(category_id, template_id), source.name)
        shutil.copy2(source, target)
        return target

    def delete_table(self, category_id: str, template_id: str, filename: str) -> Path:
        path = self.tables_dir(category_id, template_id) / Path(filename).name
        if not path.is_file():
            raise StorageError(f"Таблицю {filename} не знайдено")
        return self._move_to_trash(path)

    # --- Спільна бібліотека ----------------------------------------------

    def list_library(self, section: str) -> list[Path]:
        folder = self._library_section(section)
        allowed = LIBRARY_EXTENSIONS[section]
        files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in allowed]
        return sorted(files, key=lambda p: p.name.casefold())

    def add_to_library(self, section: str, source: Path) -> str:
        """Копіює файл у бібліотеку. Повертає посилання на нього для шаблону."""
        source = Path(source)
        folder = self._library_section(section)
        if source.suffix.lower() not in LIBRARY_EXTENSIONS[section]:
            raise StorageError(
                f"Непідтримуваний файл {source.name}. Дозволено: "
                f"{', '.join(LIBRARY_EXTENSIONS[section])}"
            )
        if section == "fonts":
            font_family(source)  # перевірка, що файл справді шрифт
        same = self._find_same_file(folder, source)
        target = same or unique_file(folder, source.name)
        if same is None:
            shutil.copy2(source, target)
        return library_ref(section, target.name)

    def remove_from_library(self, section: str, filename: str) -> Path:
        path = self._library_section(section) / Path(filename).name
        if not path.is_file():
            raise StorageError(f"Файл {filename} не знайдено в бібліотеці")
        return self._move_to_trash(path)

    def library_fonts(self) -> dict[str, list[Path]]:
        """Сімейство шрифту -> файли (звичайний, жирний…)."""
        result: dict[str, list[Path]] = {}
        for path in self.list_library("fonts"):
            try:
                result.setdefault(font_family(path), []).append(path)
            except StorageError as e:
                log.warning("%s", e)
        return result

    # --- Налаштування бібліотеки (останні кольори) -----------------------

    def _settings(self) -> dict:
        path = self.library_dir / "settings.json"
        if not path.is_file():
            return {}
        try:
            return read_json(path)
        except StorageError as e:
            log.warning("%s", e)
            return {}

    def recent_colors(self) -> list[str]:
        colors = self._settings().get("recent_colors", [])
        return [c for c in colors if isinstance(c, str)][:RECENT_COLORS_LIMIT]

    def add_recent_color(self, color: str) -> list[str]:
        """Колір стає першим у списку останніх; повтори прибираються."""
        color = color.upper()
        colors = [color] + [c for c in self.recent_colors() if c.upper() != color]
        colors = colors[:RECENT_COLORS_LIMIT]
        settings = self._settings()
        settings["recent_colors"] = colors
        write_json_atomic(self.library_dir / "settings.json", settings)
        return colors

    def editor_settings(self) -> dict:
        """Налаштування редактора (сітка, прилипання), спільні для всіх шаблонів."""
        settings = self._settings().get("editor", {})
        return settings if isinstance(settings, dict) else {}

    def save_editor_settings(self, **values) -> None:
        settings = self._settings()
        editor = settings.get("editor", {}) if isinstance(settings.get("editor"), dict) else {}
        editor.update(values)
        settings["editor"] = editor
        write_json_atomic(self.library_dir / "settings.json", settings)

    def _library_section(self, section: str) -> Path:
        if section not in LIBRARY_SECTIONS:
            raise StorageError(f"Невідомий розділ бібліотеки: {section}")
        folder = self.library_dir / section
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    @staticmethod
    def _find_same_file(folder: Path, source: Path) -> Path | None:
        """Такий самий файл (за вмістом) уже є в папці — повертаємо його, щоб не дублювати."""
        data = source.read_bytes()
        for path in folder.iterdir():
            if path.is_file() and path.stat().st_size == len(data) and path.read_bytes() == data:
                return path
        return None

    # --- Ресурси ----------------------------------------------------------

    def add_category_asset(self, category_id: str, source: Path) -> str:
        """Копіює зображення в ресурси категорії. Повертає посилання для шаблону."""
        source = Path(source)
        if source.suffix.lower() not in LIBRARY_EXTENSIONS["icons"]:
            raise StorageError(f"Непідтримуваний файл {source.name}")
        folder = self.category_dir(category_id) / "assets"
        folder.mkdir(exist_ok=True)
        same = self._find_same_file(folder, source)
        target = same or unique_file(folder, source.name)
        if same is None:
            shutil.copy2(source, target)
        return f"{CATEGORY_PREFIX}assets/{target.name}"

    def resolve_asset(self, ref: str, category_id: str | None = None) -> Path:
        """Перетворює посилання на ресурс у шлях до файлу.

        Шлях не може вийти за межі бібліотеки чи категорії.
        """
        if ref.startswith(LIBRARY_PREFIX):
            base, rel = self.library_dir, ref[len(LIBRARY_PREFIX):]
        elif ref.startswith(CATEGORY_PREFIX):
            if category_id is None:
                raise StorageError("Для ресурсу категорії потрібно вказати категорію")
            base, rel = self.category_dir(category_id), ref[len(CATEGORY_PREFIX):]
        else:
            raise StorageError(f"Невідоме посилання на ресурс: {ref!r}")
        parts = PurePosixPath(rel.replace("\\", "/")).parts
        if not parts or any(p in ("..", "") for p in parts) or PurePosixPath(rel).is_absolute() \
                or ":" in rel:
            raise StorageError(f"Некоректний шлях ресурсу: {ref!r}")
        return base.joinpath(*parts)

    # --- Кошик ------------------------------------------------------------

    def _move_to_trash(self, path: Path) -> Path:
        self.trash_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = self.trash_dir / f"{stamp}_{path.name}"
        shutil.move(str(path), str(target))
        return target
