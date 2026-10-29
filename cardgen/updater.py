"""Оновлення програми з git-репозиторію.

Програма запускається з робочої копії git (папка з main.py). Перевірка:
`git fetch` і порівняння поточного коміту з гілкою на сервері (origin).
Встановлення: `git pull --ff-only`; якщо змінився requirements.txt —
`pip install -r requirements.txt`. Після цього програму треба перезапустити.

Дані користувача (workspace/) у git не входять і оновленням не зачіпаються.
"""
from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

GIT_TIMEOUT = 60
PIP_TIMEOUT = 900
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # без чорних вікон консолі на Windows

Runner = Callable[[list[str], Path, int], subprocess.CompletedProcess]


class UpdateError(Exception):
    pass


@dataclass
class UpdateInfo:
    available: bool
    behind: int = 0
    changes: list[str] = field(default_factory=list)  # описи нових комітів
    current: str = ""
    latest: str = ""
    branch: str = ""


def _run(cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=NO_WINDOW)


class Updater:
    def __init__(self, app_dir: Path, runner: Runner = _run, python: str = sys.executable):
        self.app_dir = Path(app_dir)
        self.runner = runner
        self.python = python

    # --- git -------------------------------------------------------------------------

    def git(self, *args: str, timeout: int = GIT_TIMEOUT) -> str:
        try:
            result = self.runner(["git", *args], self.app_dir, timeout)
        except FileNotFoundError as e:
            raise UpdateError("Git не встановлено. Завантажте його з git-scm.com") from e
        except subprocess.TimeoutExpired as e:
            raise UpdateError("Сервер оновлень не відповідає. Перевірте інтернет") from e
        if result.returncode != 0:
            message = (result.stderr or result.stdout).strip().splitlines()
            raise UpdateError(message[-1] if message else f"git {' '.join(args)}: помилка {result.returncode}")
        return result.stdout.strip()

    def supported(self) -> tuple[bool, str]:
        """Чи можна оновлюватись: робоча копія git із налаштованим сервером."""
        if not (self.app_dir / ".git").exists():
            return False, "Програма запущена не з git-репозиторію"
        try:
            if not self.git("remote"):
                return False, "Не налаштовано сервер оновлень (git remote origin)"
        except UpdateError as e:
            return False, str(e)
        return True, ""

    def branch(self) -> str:
        return self.git("rev-parse", "--abbrev-ref", "HEAD")

    # --- Перевірка й встановлення ------------------------------------------------------

    def check(self) -> UpdateInfo:
        ok, reason = self.supported()
        if not ok:
            raise UpdateError(reason)
        branch = self.branch()
        self.git("fetch", "--quiet", "origin", branch)
        upstream = f"origin/{branch}"
        behind = int(self.git("rev-list", "--count", f"HEAD..{upstream}") or 0)
        changes = self.git("log", "--format=%s", f"HEAD..{upstream}").splitlines() if behind else []
        return UpdateInfo(available=behind > 0, behind=behind, changes=changes,
                          current=self.git("rev-parse", "--short", "HEAD"),
                          latest=self.git("rev-parse", "--short", upstream), branch=branch)

    def local_changes(self) -> list[str]:
        """Змінені файли програми (не враховуючи нові файли, що не в git)."""
        output = self.git("status", "--porcelain", "--untracked-files=no")
        return [line[3:] for line in output.splitlines() if line.strip()]

    def apply(self, progress: Callable[[str], None] | None = None) -> list[str]:
        """Встановлює оновлення. Повертає описи встановлених змін."""
        say = progress or (lambda _text: None)
        info = self.check()
        if not info.available:
            return []
        changed = self.local_changes()
        if changed:
            raise UpdateError("У файлах програми є локальні зміни — оновлення зупинено, щоб їх не втратити: "
                              + ", ".join(changed[:5]))
        before = self.git("rev-parse", "HEAD")
        say("Завантаження змін…")
        self.git("pull", "--ff-only", "--quiet", "origin", info.branch)
        changed_files = self.git("diff", "--name-only", before, "HEAD").splitlines()
        if "requirements.txt" in changed_files:
            say("Оновлення бібліотек…")
            result = self.runner([self.python, "-m", "pip", "install", "--quiet", "-r", "requirements.txt"],
                                 self.app_dir, PIP_TIMEOUT)
            if result.returncode != 0:
                raise UpdateError("Програму оновлено, але бібліотеки не встановились: "
                                  + (result.stderr or result.stdout).strip()[-300:])
        return info.changes
