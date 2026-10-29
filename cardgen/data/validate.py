"""Перевірка даних перед генерацією карток."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .dataset import DataSet
from .fields import KEY_COLUMN, Schema

NUMBER_RE = re.compile(r"^[+\-−]?\d+(?:[.,]\d+)?$")


@dataclass(frozen=True)
class Issue:
    row: int  # індекс рядка в DataSet.rows; -1 — проблема всієї таблиці
    column: str
    message: str
    level: str = "error"  # error — картку не згенерувати; warning — варто глянути


def validate(dataset: DataSet, schema: Schema, images: Path) -> list[Issue]:
    issues: list[Issue] = [Issue(-1, "", c, "error") for c in schema.conflicts]

    keys = Counter(dataset.key_of(r) for r in dataset.rows if dataset.key_of(r))
    for i, row in enumerate(dataset.rows):
        key = dataset.key_of(row)
        if not key:
            issues.append(Issue(i, KEY_COLUMN, "Порожній артикул"))
        elif keys[key] > 1:
            issues.append(Issue(i, KEY_COLUMN, f"Артикул «{key}» повторюється"))
        for spec in schema.fields:
            if spec.column == KEY_COLUMN:
                continue
            value = dataset.value(row, spec.column).strip()
            if not value:
                if spec.required:
                    issues.append(Issue(i, spec.column, "Обов'язкове поле порожнє"))
                continue
            if spec.field_type == "number" and not NUMBER_RE.match(value.replace(" ", "")):
                issues.append(Issue(i, spec.column, f"«{value}» — не число"))
            elif spec.field_type == "list" and spec.options and value not in spec.options:
                issues.append(Issue(i, spec.column, f"«{value}» немає у списку варіантів", "warning"))
            elif spec.is_image and not (images / value).is_file():
                issues.append(Issue(i, spec.column, f"Фото «{value}» не знайдено"))
    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.level == "error" for i in issues)
