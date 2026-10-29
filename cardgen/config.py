"""Налаштування запуску."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def app_dir() -> Path:
    """Папка програми: поруч із .exe після збірки або корінь проєкту під час розробки."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def market_packages() -> Path:
    """Готові шаблони для Маркету (*.cardgen.zip), що постачаються з програмою."""
    return app_dir() / "market"


def default_workspace() -> Path:
    """Робоча папка з категоріями й бібліотекою. Можна змінити змінною CARDGEN_WORKSPACE."""
    env = os.environ.get("CARDGEN_WORKSPACE")
    return Path(env) if env else app_dir() / "workspace"
