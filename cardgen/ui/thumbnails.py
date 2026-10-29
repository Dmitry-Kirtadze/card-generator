"""Мініатюри шаблонів — зменшене відмальовування тим самим рушієм, що й експорт.

Якщо в шаблону є дані товарів, мініатюра показує картку першого товару
(з його фото й текстами) — так одразу видно, як виглядатимуть картки.

Відмальовування повільне (фото, прибирання білого фону), тому мініатюри кешуються
в пам'яті й на диску (workspace/cache/thumbs) і перемальовуються лише тоді, коли
змінився шаблон або його дані. Відсутні в кеші малюються по одній у черзі
(ThumbnailLoader), щоб сторінка відкривалась одразу.
"""
from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QListWidget

from ..data.dataset import images_dir, load_dataset
from ..generate import compose, load_overrides
from ..model import Template
from ..render import RenderContext, render_template
from ..storage import StorageError, Workspace

log = logging.getLogger(__name__)

PLACEHOLDER = "#E9ECF2"


def _first_card(template: Template, workspace: Workspace, category_id: str) -> tuple[Template, RenderContext]:
    ctx = RenderContext(workspace, category_id)
    try:
        tables = workspace.tables_dir(category_id, template.id)
        dataset = load_dataset(tables)
    except StorageError:
        return template, ctx
    if not dataset.rows:
        return template, ctx
    row = dataset.rows[0]
    try:
        overrides = load_overrides(tables).get(dataset.key_of(row))
    except StorageError:
        overrides = None
    ctx.data_images = images_dir(tables)
    return compose(template, dataset, row, overrides), ctx


def placeholder(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(PLACEHOLDER))
    return pixmap


def render_thumbnail(template: Template, size: int, workspace: Workspace,
                     category_id: str) -> QPixmap:
    pixmap = placeholder(size)
    scale = size / max(template.width, template.height)
    card, ctx = _first_card(template, workspace, category_id)
    image = render_template(card, ctx, scale)
    p = QPainter(pixmap)
    x = (size - image.width()) / 2
    y = (size - image.height()) / 2
    p.drawImage(QRectF(x, y, image.width(), image.height()), image)
    p.end()
    return pixmap


# --- Кеш ----------------------------------------------------------------------------

_memory: dict[tuple, tuple[str, QPixmap]] = {}


def _signature(workspace: Workspace, category_id: str, template_id: str) -> str:
    """Відбиток файлів, від яких залежить мініатюра: шаблон, дані товарів, ручні правки."""
    folder = workspace.template_dir(category_id, template_id)
    parts = []
    for path in (folder / "template.json", folder / "tables" / "data.json", folder / "tables" / "overrides.json"):
        try:
            st = path.stat()
            parts.append(f"{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append("-")
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def _disk_dir(workspace: Workspace) -> Path:
    return workspace.root / "cache" / "thumbs"


def cached_thumbnail(template: Template, size: int, workspace: Workspace, category_id: str) -> QPixmap | None:
    key = (str(workspace.root), category_id, template.id, size)
    signature = _signature(workspace, category_id, template.id)
    hit = _memory.get(key)
    if hit and hit[0] == signature:
        return hit[1]
    path = _disk_dir(workspace) / f"{template.id}-{size}-{signature}.png"
    if path.is_file():
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            _memory[key] = (signature, pixmap)
            return pixmap
    return None


def thumbnail(template: Template, size: int, workspace: Workspace, category_id: str) -> QPixmap:
    """Мініатюра з кешу або щойно намальована (і збережена в кеш)."""
    pixmap = cached_thumbnail(template, size, workspace, category_id)
    if pixmap is not None:
        return pixmap
    pixmap = render_thumbnail(template, size, workspace, category_id)
    signature = _signature(workspace, category_id, template.id)
    _memory[(str(workspace.root), category_id, template.id, size)] = (signature, pixmap)
    folder = _disk_dir(workspace)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob(f"{template.id}-{size}-*.png"):
            old.unlink(missing_ok=True)
        pixmap.save(str(folder / f"{template.id}-{size}-{signature}.png"), "PNG")
    except OSError as e:
        log.warning("Мініатюру не збережено в кеш: %s", e)
    return pixmap


class ThumbnailLoader(QObject):
    """Ставить мініатюри елементам списку: з кешу — одразу, решту малює по одній за такт."""

    def __init__(self, grid: QListWidget, workspace: Workspace, size: int):
        super().__init__(grid)
        self.grid = grid
        self.workspace = workspace
        self.size = size
        self.queue: list[tuple[str, Template, str]] = []  # (id елемента, шаблон, категорія)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(0)
        self.timer.timeout.connect(self._next)
        self.on_done: Callable[[], None] | None = None

    def reset(self) -> None:
        """Перед перебудовою списку: незавершені мініатюри старих елементів більше не потрібні."""
        self.queue.clear()
        self.timer.stop()

    def icon_for(self, item_id: str, template: Template | None, category_id: str) -> QIcon:
        """Іконка для нового елемента; якщо мініатюри ще немає — сіра заглушка й черга."""
        if template is None:
            return QIcon(placeholder(self.size))
        pixmap = cached_thumbnail(template, self.size, self.workspace, category_id)
        if pixmap is not None:
            return QIcon(pixmap)
        self.queue.append((item_id, template, category_id))
        self.timer.start()
        return QIcon(placeholder(self.size))

    def busy(self) -> bool:
        return bool(self.queue)

    def finish(self) -> None:
        """Домалювати все одразу (для тестів)."""
        while self.queue:
            self._next()

    def _next(self) -> None:
        if not self.queue:
            return
        item_id, template, category_id = self.queue.pop(0)
        try:
            pixmap = thumbnail(template, self.size, self.workspace, category_id)
        except Exception:  # одна пошкоджена мініатюра не повинна зупиняти інші
            log.exception("Не вдалося намалювати мініатюру %s", template.name)
            pixmap = None
        if pixmap is not None:
            for row in range(self.grid.count()):
                item = self.grid.item(row)
                if item.data(Qt.ItemDataRole.UserRole) == item_id:
                    item.setIcon(QIcon(pixmap))
                    break
        if self.queue:
            self.timer.start()
        elif self.on_done:
            self.on_done()
