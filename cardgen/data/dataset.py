"""Дані товарів шаблону: рядки «стовпець -> значення».

Зберігаються в папці шаблону: tables/data.json, фото — tables/images/.
Значення завжди рядки; для фото — ім'я файлу в tables/images.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..storage import StorageError, read_json, write_json_atomic
from .fields import KEY_COLUMN, normalize_column

DATA_FILE = "data.json"
IMAGES_DIR = "images"
FORMAT_VERSION = 1


@dataclass
class DataSet:
    columns: list[str] = field(default_factory=lambda: [KEY_COLUMN])
    rows: list[dict[str, str]] = field(default_factory=list)
    source: str = ""  # з якого файлу імпортовано
    updated_at: str = ""

    def value(self, row: dict[str, str], column: str) -> str:
        """Значення без урахування регістру й зайвих пробілів у назві стовпця."""
        if column in row:
            return row[column]
        key = normalize_column(column)
        return next((v for k, v in row.items() if normalize_column(k) == key), "")

    def key_of(self, row: dict[str, str]) -> str:
        return self.value(row, KEY_COLUMN).strip()

    def find(self, article: str) -> dict[str, str] | None:
        return next((r for r in self.rows if self.key_of(r) == article.strip()), None)

    def ensure_columns(self, columns: list[str]) -> None:
        known = {normalize_column(c) for c in self.columns}
        for column in columns:
            if normalize_column(column) not in known:
                self.columns.append(column)
                known.add(normalize_column(column))

    def to_dict(self) -> dict:
        return {"format": FORMAT_VERSION, "columns": self.columns, "rows": self.rows,
                "source": self.source, "updated_at": self.updated_at}

    @classmethod
    def from_dict(cls, data: dict) -> DataSet:
        columns = [str(c) for c in data.get("columns", [KEY_COLUMN])]
        rows = [{str(k): "" if v is None else str(v) for k, v in row.items()}
                for row in data.get("rows", []) if isinstance(row, dict)]
        return cls(columns or [KEY_COLUMN], rows, str(data.get("source", "")),
                   str(data.get("updated_at", "")))


def images_dir(tables_dir: Path) -> Path:
    path = tables_dir / IMAGES_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_dataset(tables_dir: Path) -> DataSet:
    path = tables_dir / DATA_FILE
    if not path.is_file():
        return DataSet()
    try:
        return DataSet.from_dict(read_json(path))
    except StorageError:
        raise
    except Exception as e:  # noqa: BLE001 — будь-яка помилка структури файлу
        raise StorageError(f"Дані {path} пошкоджено: {e}") from e


def save_dataset(tables_dir: Path, dataset: DataSet) -> None:
    dataset.updated_at = datetime.now().isoformat(timespec="seconds")
    write_json_atomic(tables_dir / DATA_FILE, dataset.to_dict())
