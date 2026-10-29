"""Експорт та імпорт категорії одним файлом для перенесення між комп'ютерами.

Вміст архіву (.cardgen.zip):

    manifest.json        формат, версія, назва категорії
    category/...         папка категорії повністю (шаблони, ресурси, таблиці)
    library/<розділ>/... файли спільної бібліотеки, які використовують шаблони

При імпорті категорія отримує новий id. Файли бібліотеки, яких ще немає,
додаються; однакові за вмістом не дублюються; різні з тим самим ім'ям
зберігаються під новим ім'ям, і посилання в шаблонах переписуються.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from . import __version__
from .model import Category
from .model.serialization import SCHEMA_VERSION, category_from_dict
from .model.walk import asset_refs, font_families, replace_asset_refs
from .storage import (
    LIBRARY_PREFIX,
    LIBRARY_SECTIONS,
    StorageError,
    Workspace,
    library_ref,
    read_json,
    unique_file,
    unique_name,
)

FORMAT = "cardgen-category"
EXTENSION = ".cardgen.zip"


def export_category(workspace: Workspace, category_id: str, target: Path) -> Path:
    category = workspace.get_category(category_id)
    category_dir = workspace.category_dir(category_id)
    templates = workspace.list_templates(category_id)

    library_files: set[Path] = set()
    for template in templates:
        for ref in asset_refs(template):
            if ref.startswith(LIBRARY_PREFIX):
                path = workspace.resolve_asset(ref)
                if path.is_file():
                    library_files.add(path)
    fonts = workspace.library_fonts()
    for template in templates:
        for family in font_families(template):
            library_files.update(fonts.get(family, []))

    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "format": FORMAT,
        "schema_version": SCHEMA_VERSION,
        "app_version": __version__,
        "name": category.name,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
    }
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for path in sorted(category_dir.rglob("*")):
            if path.is_file() and not path.name.endswith(".tmp"):
                zf.write(path, "category/" + path.relative_to(category_dir).as_posix())
        for path in sorted(library_files):
            zf.write(path, "library/" + path.relative_to(workspace.library_dir).as_posix())
    return target


def import_category(workspace: Workspace, source: Path) -> Category:
    source = Path(source)
    try:
        zf = zipfile.ZipFile(source)
    except (OSError, zipfile.BadZipFile) as e:
        raise StorageError(f"Файл {source.name} не є архівом категорії: {e}") from e

    with zf, tempfile.TemporaryDirectory(dir=workspace.root, prefix=".import-") as tmp:
        tmp_dir = Path(tmp)
        _check_manifest(zf)
        _safe_extract(zf, tmp_dir)

        extracted_category = tmp_dir / "category"
        if not (extracted_category / "category.json").is_file():
            raise StorageError("В архіві немає категорії")
        mapping = _merge_library(workspace, tmp_dir / "library")

        category = category_from_dict(read_json(extracted_category / "category.json"))
        taken = {c.name.casefold() for c in workspace.list_categories()}
        imported = Category(
            name=category.name if category.name.casefold() not in taken
            else unique_name(category.name, taken, "імпорт"),
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
        target_dir = workspace.categories_dir / imported.id
        shutil.move(str(extracted_category), str(target_dir))
        workspace.save_category(imported)

        if mapping:
            for template in workspace.list_templates(imported.id):
                if replace_asset_refs(template, mapping):
                    workspace.save_template(imported.id, template)
    return imported


def _check_manifest(zf: zipfile.ZipFile) -> None:
    try:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    except (KeyError, ValueError) as e:
        raise StorageError("Архів не створено цією програмою (немає manifest.json)") from e
    if manifest.get("format") != FORMAT:
        raise StorageError("Архів не створено цією програмою")
    if manifest.get("schema_version", 1) > SCHEMA_VERSION:
        raise StorageError("Категорію експортовано новішою версією програми. Оновіть програму.")


def _safe_extract(zf: zipfile.ZipFile, target: Path) -> None:
    """Розпаковує лише очікувані шляхи, не дозволяючи вийти за межі папки."""
    for info in zf.infolist():
        name = info.filename
        parts = PurePosixPath(name).parts
        if (name.startswith(("/", "\\")) or ":" in name or "\\" in name or ".." in parts
                or not parts or parts[0] not in ("manifest.json", "category", "library")):
            raise StorageError(f"Підозрілий шлях в архіві: {name}")
        if parts[0] == "library" and (len(parts) != 3 or parts[1] not in LIBRARY_SECTIONS):
            raise StorageError(f"Підозрілий шлях в архіві: {name}")
        if info.is_dir():
            continue
        dest = target.joinpath(*parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)


def _merge_library(workspace: Workspace, extracted: Path) -> dict[str, str]:
    """Додає файли бібліотеки з архіву. Повертає заміни посилань для перейменованих."""
    mapping: dict[str, str] = {}
    if not extracted.is_dir():
        return mapping
    for section_dir in extracted.iterdir():
        section = section_dir.name
        dest_dir = workspace.library_dir / section
        dest_dir.mkdir(parents=True, exist_ok=True)
        for path in section_dir.iterdir():
            existing = dest_dir / path.name
            if existing.is_file():
                if existing.read_bytes() == path.read_bytes():
                    continue
                new_path = unique_file(dest_dir, path.name)
                mapping[library_ref(section, path.name)] = library_ref(section, new_path.name)
                shutil.copy2(path, new_path)
            else:
                shutil.copy2(path, existing)
    return mapping
