"""Мініатюри шаблонів — зменшене відмальовування тим самим рушієм, що й експорт.

Якщо в шаблону є дані товарів, мініатюра показує картку першого товару
(з його фото й текстами) — так одразу видно, як виглядатимуть картки.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPixmap

from ..data.dataset import images_dir, load_dataset
from ..generate import compose, load_overrides
from ..model import Template
from ..render import RenderContext, render_template
from ..storage import StorageError, Workspace


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


def render_thumbnail(template: Template, size: int, workspace: Workspace,
                     category_id: str) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor("#E9ECF2"))
    scale = size / max(template.width, template.height)
    card, ctx = _first_card(template, workspace, category_id)
    image = render_template(card, ctx, scale)
    p = QPainter(pixmap)
    x = (size - image.width()) / 2
    y = (size - image.height()) / 2
    p.drawImage(QRectF(x, y, image.width(), image.height()), image)
    p.end()
    return pixmap
