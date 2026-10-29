"""Налаштування запуску.

Два способи запуску:
- з робочої копії git (розробка): `python main.py`, усе поруч із main.py;
- зібрана програма CardGen.exe (див. launcher.py): .exe містить Python і бібліотеки,
  а код програми береться з user_dir()/app (завантажується з GitHub під час оновлення)
  або, поки його немає, з копії, вкладеної в .exe.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_ID = "CardGen"
GITHUB_REPO = "Dmitry-Kirtadze/card-generator"  # публічний: оновлення без входу й без git
WORKSPACE_FOLDER = "Генератор карток"


def frozen() -> bool:
    """Запущено зібрану програму (.exe)."""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Папка з кодом програми (main.py, cardgen/, market/): та, з якої імпортовано cardgen."""
    return Path(__file__).resolve().parent.parent


def user_dir() -> Path:
    """Службова папка користувача: налаштування запуску, код для оновлень, журнал."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_ID


def code_dir() -> Path:
    """Копія git-репозиторію, з якої зібрана програма бере оновлений код."""
    return user_dir() / "app"


def settings_path() -> Path:
    return user_dir() / "settings.json"


def load_settings() -> dict:
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(**values) -> None:
    data = load_settings()
    data.update(values)
    settings_path().parent.mkdir(parents=True, exist_ok=True)
    settings_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def market_packages() -> Path:
    """Готові шаблони для Маркету (*.cardgen.zip), що постачаються з програмою."""
    return app_dir() / "market"


def default_workspace() -> Path:
    """Робоча папка з категоріями й бібліотекою.

    Порядок: змінна CARDGEN_WORKSPACE → "workspace" у settings.json →
    Документи/Генератор карток (зібрана програма) або workspace/ поруч із main.py (розробка).
    """
    env = os.environ.get("CARDGEN_WORKSPACE")
    if env:
        return Path(env)
    configured = load_settings().get("workspace")
    if configured:
        return Path(configured)
    if frozen():
        return Path.home() / "Documents" / WORKSPACE_FOLDER
    return app_dir() / "workspace"
