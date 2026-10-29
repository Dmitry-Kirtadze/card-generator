"""Маркет — вбудована категорія готових шаблонів.

Маркет не можна видалити чи перейменувати. Шаблони з нього копіюються в будь-яку
категорію, а свої вдалі шаблони можна додати в Маркет.

Готові шаблони постачаються як файли *.cardgen.zip у папці market поруч із програмою.
Під час запуску нові пакети автоматично додаються в Маркет (кожен — один раз:
якщо шаблон із Маркету видалили, він не повернеться сам).
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from .data.dataset import DATA_FILE, IMAGES_DIR
from .model import Category, Template, new_id
from .model.walk import asset_refs, replace_asset_refs
from .storage import CATEGORY_PREFIX, StorageError, Workspace, unique_name
from .transfer import import_category

log = logging.getLogger(__name__)

MARKET_ID = "market"
MARKET_NAME = "Маркет"


def is_market(category_id: str) -> bool:
    return category_id == MARKET_ID


def ensure_market(workspace: Workspace) -> Category:
    """Створює Маркет, якщо його ще немає."""
    folder = workspace.categories_dir / MARKET_ID
    if (folder / "category.json").is_file():
        category = workspace.get_category(MARKET_ID)
        if not category.protected:
            category.protected = True
            workspace.save_category(category)
        return category
    (folder / "assets").mkdir(parents=True, exist_ok=True)
    (folder / "templates").mkdir(exist_ok=True)
    category = Category(id=MARKET_ID, name=MARKET_NAME, protected=True)
    workspace.save_category(category)
    return category


def copy_template(workspace: Workspace, source_category: str, template_id: str, target_category: str,
                  *, with_data: bool = True) -> Template:
    """Копія шаблону в іншу категорію: новий id, вільна назва, наступний номер картинки.

    Ресурси категорії (фото-зразки тощо) копіюються в цільову категорію; бібліотека спільна.
    with_data — разом із прикладом даних товарів (без історії таблиць і ручних правок).
    """
    template = workspace.load_template(source_category, template_id)
    source_dir = workspace.category_dir(source_category)

    mapping: dict[str, str] = {}
    for ref in asset_refs(template):
        if ref.startswith(CATEGORY_PREFIX) and source_category != target_category:
            path = workspace.resolve_asset(ref, source_category)
            if path.is_file():
                mapping[ref] = workspace.add_category_asset(target_category, path)
    replace_asset_refs(template, mapping)

    existing = workspace.list_templates(target_category)
    taken = {t.name.casefold() for t in existing}
    if template.name.casefold() in taken:
        template.name = unique_name(template.name, taken)
    template.export.number = max((t.export.number for t in existing), default=0) + 1
    template.id = new_id()
    workspace.save_template(target_category, template)

    if with_data:
        src_tables = source_dir / "templates" / template_id / "tables"
        dst_tables = workspace.tables_dir(target_category, template.id)
        if (src_tables / DATA_FILE).is_file():
            shutil.copy2(src_tables / DATA_FILE, dst_tables / DATA_FILE)
        if (src_tables / IMAGES_DIR).is_dir():
            shutil.copytree(src_tables / IMAGES_DIR, dst_tables / IMAGES_DIR, dirs_exist_ok=True)
    return template


def seed_market(workspace: Workspace, packages: Path) -> list[str]:
    """Додає в Маркет шаблони з нових пакетів *.cardgen.zip. Повертає назви доданих шаблонів."""
    market = ensure_market(workspace)
    added: list[str] = []
    if not packages.is_dir():
        return added
    for package in sorted(packages.glob("*.cardgen.zip")):
        if package.name in market.seeded:
            continue
        try:
            temp = import_category(workspace, package)
        except (StorageError, OSError) as e:
            log.warning("Пакет Маркету %s не завантажено: %s", package.name, e)
            continue
        try:
            for template in workspace.list_templates(temp.id):
                copied = copy_template(workspace, temp.id, template.id, MARKET_ID)
                added.append(copied.name)
        finally:
            shutil.rmtree(workspace.category_dir(temp.id), ignore_errors=True)  # тимчасова категорія
        market.seeded.append(package.name)
        workspace.save_category(market)
    return added
