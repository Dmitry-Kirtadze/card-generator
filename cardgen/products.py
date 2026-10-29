"""Товари шаблону: збирання, відмальовування та ручні правки карток.

Спільне для попереднього перегляду (етап 7) та експорту (етап 8).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QImage

from .data.dataset import DataSet, images_dir, load_dataset
from .data.fields import Schema, build_schema
from .data.validate import Issue, validate
from .generate import (
    Overrides,
    apply_data,
    apply_overrides,
    compose,
    diff,
    load_overrides,
    save_overrides,
    split_for_template,
)

__all__ = ["Products", "Rendered"]
from .model import Template
from .render import RenderContext, render_template
from .storage import Workspace


@dataclass
class Rendered:
    image: QImage
    overflow: set[str]  # id блоків/клітинок, де текст не вмістився


class Products:
    def __init__(self, workspace: Workspace, category_id: str, template_id: str):
        self.workspace = workspace
        self.category_id = category_id
        self.template_id = template_id
        self.reload()

    def reload(self) -> None:
        self.template: Template = self.workspace.load_template(self.category_id, self.template_id)
        self.tables: Path = self.workspace.tables_dir(self.category_id, self.template_id)
        self.images: Path = images_dir(self.tables)
        self.schema: Schema = build_schema(self.template)
        self.dataset: DataSet = load_dataset(self.tables)
        self.overrides: dict[str, Overrides] = load_overrides(self.tables)
        self.issues: list[Issue] = validate(self.dataset, self.schema, self.images)

    # --- Доступ -------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.dataset.rows)

    def article(self, index: int) -> str:
        return self.dataset.key_of(self.dataset.rows[index]) or f"рядок-{index + 1}"

    def row_issues(self, index: int) -> list[Issue]:
        return [i for i in self.issues if i.row == index]

    def has_override(self, index: int) -> bool:
        return bool(self.overrides.get(self.article(index)))

    def context(self) -> RenderContext:
        return RenderContext(self.workspace, self.category_id, data_images=self.images,
                             placeholders=False)

    # --- Збирання ------------------------------------------------------------------

    def base(self, index: int) -> Template:
        """Шаблон + дані, без ручних правок."""
        return apply_data(self.template, self.dataset, self.dataset.rows[index])

    def card(self, index: int) -> Template:
        """Готова картка: шаблон + дані + правки товару."""
        return compose(self.template, self.dataset, self.dataset.rows[index],
                       self.overrides.get(self.article(index)))

    def render(self, index: int, scale: float = 1.0) -> Rendered:
        ctx = self.context()
        image = render_template(self.card(index), ctx, scale)
        return Rendered(image, set(ctx.overflow))

    # --- Ручні правки ------------------------------------------------------------------

    def save_for_product(self, index: int, edited: Template) -> None:
        changes = diff(self.base(index), edited)
        article = self.article(index)
        if changes:
            self.overrides[article] = changes
        else:
            self.overrides.pop(article, None)
        save_overrides(self.tables, self.overrides)

    def save_for_template(self, index: int, edited: Template) -> Overrides:
        """Зміни картки -> у шаблон (для всіх товарів). Підставлені дані лишаються правкою товару.

        У шаблон іде лише те, що змінено зараз (порівняно з карткою до редагування):
        старі правки саме цього товару лишаються правками товару.
        Повертає правки, що лишились у товару.
        """
        session = diff(self.card(index), edited)
        to_template, _data_changes = split_for_template(self.template, session)
        if to_template:
            self.template = apply_overrides(self.template, to_template)
            self.workspace.save_template(self.category_id, self.template)
        article = self.article(index)
        keep = diff(self.base(index), edited)  # база вже з оновленим шаблоном
        if keep:
            self.overrides[article] = keep
        else:
            self.overrides.pop(article, None)
        save_overrides(self.tables, self.overrides)
        return keep

    def reset(self, index: int) -> None:
        if self.overrides.pop(self.article(index), None) is not None:
            save_overrides(self.tables, self.overrides)
