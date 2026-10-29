"""Підключення шрифтів бібліотеки до Qt, щоб вони були доступні в редакторі."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QFontDatabase

from ..storage import Workspace

log = logging.getLogger(__name__)

_registered: dict[Path, int] = {}


def register_library_fonts(workspace: Workspace) -> list[str]:
    """Реєструє нові файли шрифтів. Повертає сімейства всіх зареєстрованих шрифтів бібліотеки."""
    families: set[str] = set()
    for path in workspace.list_library("fonts"):
        font_id = _registered.get(path)
        if font_id is None:
            font_id = QFontDatabase.addApplicationFont(str(path))
            if font_id < 0:
                log.warning("Qt не зміг завантажити шрифт %s", path)
                continue
            _registered[path] = font_id
        families.update(QFontDatabase.applicationFontFamilies(font_id))
    return sorted(families)


def forget_font(path: Path) -> None:
    font_id = _registered.pop(path, None)
    if font_id is not None:
        QFontDatabase.removeApplicationFont(font_id)
