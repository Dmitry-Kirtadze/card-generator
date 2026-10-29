"""Збирання картки товару: шаблон + дані рядка + ручні правки цього товару.

Ручні правки зберігаються як різниця з картою «шаблон + дані»: для кожного
блоку — шляхи полів і нові значення, наприклад {"x": 120, "style.font_size": 40,
"cells.2.1.text": "…"}. Тому:
- правки товару переживають повторне завантаження таблиці (ключ — артикул);
- зміни шаблону, яких правки не торкаються, потрапляють і в товари з правками;
- якщо блок зі шаблону видалили — його правки просто ігноруються.

Файл правок: <папка шаблону>/tables/overrides.json
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .data.dataset import DataSet
from .model import PhotoElement, TableElement, Template, TextElement
from .model.serialization import template_from_dict, template_to_dict
from .model.walk import iter_elements
from .storage import StorageError, read_json, write_json_atomic

OVERRIDES_FILE = "overrides.json"
DATA_PREFIX = "data:"  # посилання на фото з таблиці даних шаблону

Overrides = dict[str, dict[str, Any]]  # id блоку -> {шлях поля: значення}


# --- Підстановка даних -------------------------------------------------------------

def fill_text(value: str, binding) -> str:
    """Префікс + значення + суфікс; порожнє значення — порожній текст (без «Довжина:  м»)."""
    value = value.strip()
    return f"{binding.prefix}{value}{binding.suffix}" if value else ""


def apply_data(template: Template, dataset: DataSet, row: dict[str, str]) -> Template:
    """Копія шаблону з підставленими значеннями. Заповнювані поля стають звичайними."""
    result = copy.deepcopy(template)
    for element in iter_elements(result.elements):
        if isinstance(element, TextElement) and element.binding.enabled:
            element.text = fill_text(dataset.value(row, element.binding.column), element.binding)
            element.binding.enabled = False
        elif isinstance(element, PhotoElement) and element.binding.enabled:
            value = dataset.value(row, element.binding.column).strip()
            element.placeholder = f"{DATA_PREFIX}{value}" if value else ""
            element.binding.enabled = False
        elif isinstance(element, TableElement):
            for cells in element.cells:
                for cell in cells:
                    if cell.binding.enabled:
                        cell.text = fill_text(dataset.value(row, cell.binding.column), cell.binding)
                        cell.binding.enabled = False
    return result


# --- Різниця та накладання правок -------------------------------------------------------

def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, sub in value.items():
            out.update(_flatten(sub, f"{prefix}{key}."))
        return out
    if isinstance(value, list) and value and isinstance(value[0], (dict, list)):
        out = {}
        for i, sub in enumerate(value):
            out.update(_flatten(sub, f"{prefix}{i}."))
        return out
    return {prefix[:-1]: value}


def _element_dicts(template_dict: dict) -> dict[str, dict]:
    result = {}

    def walk(elements: list[dict]) -> None:
        for e in elements:
            result[e["id"]] = e
            if e.get("type") == "group":
                walk(e.get("children", []))

    walk(template_dict.get("elements", []))
    return result


def _element_flat(e: dict) -> dict[str, Any]:
    plain = {k: v for k, v in e.items() if k not in ("id", "type", "children")}
    return _flatten(plain)


def diff(base: Template, edited: Template) -> Overrides:
    """Що змінено в edited порівняно з base (лише існуючі поля існуючих блоків)."""
    base_elements = _element_dicts(template_to_dict(base))
    edited_elements = _element_dicts(template_to_dict(edited))
    result: Overrides = {}
    for element_id, e in edited_elements.items():
        if element_id not in base_elements:
            continue
        before = _element_flat(base_elements[element_id])
        after = _element_flat(e)
        changed = {path: value for path, value in after.items()
                   if path in before and before[path] != value}
        if changed:
            result[element_id] = changed
    return result


def _set_path(target: dict, path: str, value: Any) -> bool:
    parts = path.split(".")
    node: Any = target
    for part in parts[:-1]:
        if isinstance(node, list):
            if not part.isdigit() or int(part) >= len(node):
                return False
            node = node[int(part)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return False
    last = parts[-1]
    if isinstance(node, list):
        if not last.isdigit() or int(last) >= len(node):
            return False
        key: Any = int(last)
    elif isinstance(node, dict) and last in node:
        key = last
    else:
        return False
    old = node[key]
    # список іншої довжини (напр. ширини стовпців після зміни таблиці) — правка застаріла
    if isinstance(old, list) and (not isinstance(value, list) or len(old) != len(value)):
        return False
    node[key] = value
    return True


def apply_overrides(template: Template, overrides: Overrides) -> Template:
    """Копія шаблону з правками; правки до неіснуючих блоків/полів пропускаються."""
    if not overrides:
        return copy.deepcopy(template)
    data = template_to_dict(template)
    elements = _element_dicts(data)
    for element_id, changes in overrides.items():
        element = elements.get(element_id)
        if element is None:
            continue
        for path, value in changes.items():
            _set_path(element, path, value)
    return template_from_dict(data)


def compose(template: Template, dataset: DataSet, row: dict[str, str],
            overrides: Overrides | None = None) -> Template:
    """Готова картка товару."""
    return apply_overrides(apply_data(template, dataset, row), overrides or {})


# --- Перенесення правок у шаблон -------------------------------------------------------

def data_paths(template: Template) -> set[tuple[str, str]]:
    """(id блоку, шлях) полів, які заповнюються з таблиці — їх не можна переносити в шаблон."""
    result = set()
    for element in iter_elements(template.elements):
        if isinstance(element, TextElement) and element.binding.enabled:
            result.add((element.id, "text"))
        elif isinstance(element, PhotoElement) and element.binding.enabled:
            result.add((element.id, "placeholder"))
        elif isinstance(element, TableElement):
            for r, cells in enumerate(element.cells):
                for c, cell in enumerate(cells):
                    if cell.binding.enabled:
                        result.add((element.id, f"cells.{r}.{c}.text"))
    return result


def split_for_template(template: Template, changes: Overrides) -> tuple[Overrides, Overrides]:
    """Правки -> (що можна внести в шаблон, що лишається правкою товару — дані)."""
    protected = data_paths(template)
    to_template: Overrides = {}
    keep: Overrides = {}
    for element_id, fields in changes.items():
        for path, value in fields.items():
            bucket = keep if (element_id, path) in protected or path.startswith("binding.") \
                or ".binding." in path else to_template
            bucket.setdefault(element_id, {})[path] = value
    return to_template, keep


# --- Зберігання ----------------------------------------------------------------------

def load_overrides(tables_dir: Path) -> dict[str, Overrides]:
    """Артикул -> правки цього товару."""
    path = tables_dir / OVERRIDES_FILE
    if not path.is_file():
        return {}
    data = read_json(path)
    products = data.get("products", {})
    if not isinstance(products, dict):
        raise StorageError(f"Правки {path} пошкоджено")
    return {str(k): v for k, v in products.items() if isinstance(v, dict)}


def save_overrides(tables_dir: Path, overrides: dict[str, Overrides]) -> None:
    clean = {article: o for article, o in overrides.items() if o}
    write_json_atomic(tables_dir / OVERRIDES_FILE, {"format": 1, "products": clean})
