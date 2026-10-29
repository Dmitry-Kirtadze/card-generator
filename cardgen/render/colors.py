"""Кольори моделі ("#RRGGBB" / "#RRGGBBAA") <-> QColor."""
from __future__ import annotations

import re

from PySide6.QtGui import QColor

HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def is_valid(value: str) -> bool:
    return bool(HEX_RE.match(value or ""))


def normalize(value: str) -> str:
    """'#1e5bff' -> '#1E5BFF'; прозорість FF відкидається."""
    value = value.strip().upper()
    if not value.startswith("#"):
        value = "#" + value
    if not is_valid(value):
        raise ValueError(f"Некоректний колір: {value}")
    if len(value) == 9 and value.endswith("FF"):
        value = value[:7]
    return value


def qcolor(value: str, fallback: str = "#000000") -> QColor:
    if not is_valid(value):
        value = fallback
    color = QColor(value[:7])
    if len(value) == 9:
        color.setAlpha(int(value[7:9], 16))
    return color


def to_hex(color: QColor) -> str:
    base = "#{:02X}{:02X}{:02X}".format(color.red(), color.green(), color.blue())
    return base if color.alpha() == 255 else base + f"{color.alpha():02X}"
