"""Точка входу зібраної програми CardGen.exe (див. tools/build_exe.py).

.exe містить Python, бібліотеки й початкову копію коду (папка app/ всередині збірки).
Під час запуску обирає, звідки взяти код програми:
- копія git-репозиторію в %LOCALAPPDATA%/CardGen/app — її оновлює кнопка «Оновлення…»;
- вбудована копія — якщо оновленої ще немає, вона потребує новіших бібліотек (RUNTIME)
  або не запускається.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import traceback
from pathlib import Path


def user_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "CardGen"


def runtime_of(code: Path) -> int:
    try:
        text = (code / "cardgen" / "__init__.py").read_text(encoding="utf-8")
    except OSError:
        return 0
    match = re.search(r"^RUNTIME\s*=\s*(\d+)", text, re.MULTILINE)
    return int(match.group(1)) if match else 0


def bundled_code() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "app"


def candidates() -> list[Path]:
    bundled = bundled_code()
    updated = user_dir() / "app"
    ok = (updated / ".git").exists() and 0 < runtime_of(updated) <= runtime_of(bundled)
    return [updated, bundled] if ok else [bundled]


def forget_cardgen() -> None:
    for name in [n for n in sys.modules if n == "cardgen" or n.startswith("cardgen.")]:
        del sys.modules[name]


def load(code: Path):
    """Імпортує cardgen.app з папки code; повертає функцію run."""
    sys.path.insert(0, str(code))
    try:
        from cardgen.app import run
        return run
    except Exception:
        sys.path.remove(str(code))
        forget_cardgen()
        raise


def setup_logging() -> None:
    user_dir().mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=user_dir() / "cardgen.log", level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def show_error(text: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "Генератор карток", 0x10)
    except Exception:
        pass


def main() -> int:
    setup_logging()
    log = logging.getLogger("launcher")
    errors = []
    for code in candidates():
        try:
            run = load(code)
        except Exception:
            errors.append(traceback.format_exc())
            log.exception("Не вдалося завантажити код з %s", code)
            continue
        log.info("Запуск коду з %s", code)
        try:
            return run()
        except Exception:
            log.exception("Програма завершилась з помилкою")
            show_error("Програма завершилась з помилкою:\n\n" + traceback.format_exc()[-1500:])
            return 1
    show_error("Не вдалося запустити програму:\n\n" + "\n".join(errors)[-1500:])
    return 1


if __name__ == "__main__":
    sys.exit(main())
