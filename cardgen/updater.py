"""Оновлення програми з git-репозиторію.

Програма запускається з робочої копії git (папка з main.py). Перевірка:
`git fetch` і порівняння поточного коміту з гілкою на сервері (origin).
Встановлення: `git pull --ff-only`; якщо змінився requirements.txt —
`pip install -r requirements.txt`. Після цього програму треба перезапустити.

Зібрана програма (CardGen.exe) не має pip: вона оновлює лише код у копії репозиторію
(config.code_dir), а якщо нова версія потребує інших бібліотек (cardgen.RUNTIME більший
за вбудований у .exe), просить встановити нову збірку. Якщо копії ще немає — перше
встановлення робить `git clone`.

Дані користувача (workspace/) у git не входять і оновленням не зачіпаються.
"""
from __future__ import annotations

import os
import re
import shutil
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
    # Без консолі git не може спитати пароль у терміналі — нехай одразу повертає помилку
    # (вікно входу Git Credential Manager при цьому працює).
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=NO_WINDOW, env=env)


def read_runtime(app_dir: Path) -> int:
    """cardgen.RUNTIME з коду в app_dir без імпорту (0, якщо не знайдено)."""
    try:
        text = (Path(app_dir) / "cardgen" / "__init__.py").read_text(encoding="utf-8")
    except OSError:
        return 0
    match = re.search(r"^RUNTIME\s*=\s*(\d+)", text, re.MULTILINE)
    return int(match.group(1)) if match else 0


class Updater:
    """app_dir — копія репозиторію, яку оновлюємо.

    python — інтерпретатор для pip (None у зібраній програмі: бібліотеки вбудовані в .exe);
    repo_url — звідки зробити перше встановлення, якщо app_dir ще не копія git;
    runtime — версія бібліотек .exe: код, що потребує новішої, вимагає нову збірку.
    """

    def __init__(self, app_dir: Path, runner: Runner = _run, python: str | None = sys.executable,
                 repo_url: str = "", runtime: int | None = None):
        self.app_dir = Path(app_dir)
        self.runner = runner
        self.python = python
        self.repo_url = repo_url
        self.runtime = runtime

    # --- git -------------------------------------------------------------------------

    def git(self, *args: str, timeout: int = GIT_TIMEOUT, cwd: Path | None = None) -> str:
        try:
            result = self.runner(["git", *args], cwd or self.app_dir, timeout)
        except FileNotFoundError as e:
            raise UpdateError("Git не встановлено. Завантажте його з git-scm.com") from e
        except subprocess.TimeoutExpired as e:
            raise UpdateError("Сервер оновлень не відповідає. Перевірте інтернет") from e
        if result.returncode != 0:
            message = (result.stderr or result.stdout).strip().splitlines()
            raise UpdateError(message[-1] if message else f"git {' '.join(args)}: помилка {result.returncode}")
        return result.stdout.strip()

    def installed(self) -> bool:
        return (self.app_dir / ".git").exists()

    def supported(self) -> tuple[bool, str]:
        """Чи можна оновлюватись: робоча копія git із налаштованим сервером (або адреса для клонування)."""
        if not self.installed():
            if self.repo_url:
                return True, ""
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
        if not self.installed():
            return self._check_remote()
        branch = self.branch()
        self.git("fetch", "--quiet", "origin", branch)
        upstream = f"origin/{branch}"
        behind = int(self.git("rev-list", "--count", f"HEAD..{upstream}") or 0)
        changes = self.git("log", "--format=%s", f"HEAD..{upstream}").splitlines() if behind else []
        return UpdateInfo(available=behind > 0, behind=behind, changes=changes,
                          current=self.git("rev-parse", "--short", "HEAD"),
                          latest=self.git("rev-parse", "--short", upstream), branch=branch)

    def _check_remote(self) -> UpdateInfo:
        """Копії ще немає: перевіряємо, що сервер доступний, і пропонуємо перше встановлення."""
        output = self.git("ls-remote", "--symref", self.repo_url, "HEAD", cwd=Path.home())
        branch, latest = "", ""
        for line in output.splitlines():
            if line.startswith("ref:"):
                branch = line.split()[1].removeprefix("refs/heads/")
            elif line.endswith("HEAD"):
                latest = line.split()[0][:7]
        if not latest:
            raise UpdateError("Репозиторій оновлень порожній")
        return UpdateInfo(available=True, behind=1, changes=["Підключення оновлень з GitHub"],
                          latest=latest, branch=branch)

    def _clone(self) -> list[str]:
        parent = self.app_dir.parent
        parent.mkdir(parents=True, exist_ok=True)
        temp = parent / (self.app_dir.name + ".new")
        shutil.rmtree(temp, ignore_errors=True)
        self.git("clone", "--quiet", self.repo_url, str(temp), cwd=parent, timeout=PIP_TIMEOUT)
        shutil.rmtree(self.app_dir, ignore_errors=True)
        temp.rename(self.app_dir)
        self._check_runtime()
        return ["Підключення оновлень з GitHub"]

    def _check_runtime(self) -> None:
        if self.runtime is not None and read_runtime(self.app_dir) > self.runtime:
            raise UpdateError("Нова версія потребує оновлених бібліотек — встановіть нову збірку CardGen.exe. "
                              "До того працює поточна версія.")

    def local_changes(self) -> list[str]:
        """Змінені файли програми (не враховуючи нові файли, що не в git)."""
        output = self.git("status", "--porcelain", "--untracked-files=no")
        return [line[3:] for line in output.splitlines() if line.strip()]

    def apply(self, progress: Callable[[str], None] | None = None) -> list[str]:
        """Встановлює оновлення. Повертає описи встановлених змін."""
        say = progress or (lambda _text: None)
        if not self.installed() and self.repo_url:
            say("Завантаження програми…")
            return self._clone()
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
        if "requirements.txt" in changed_files and self.python:
            say("Оновлення бібліотек…")
            result = self.runner([self.python, "-m", "pip", "install", "--quiet", "-r", "requirements.txt"],
                                 self.app_dir, PIP_TIMEOUT)
            if result.returncode != 0:
                raise UpdateError("Програму оновлено, але бібліотеки не встановились: "
                                  + (result.stderr or result.stdout).strip()[-300:])
        self._check_runtime()
        return info.changes


def app_updater() -> Updater:
    """Оновлювач для поточного способу запуску (див. config)."""
    from . import RUNTIME, config
    if config.frozen():
        return Updater(config.code_dir(), python=None, repo_url=config.REPO_URL, runtime=RUNTIME)
    return Updater(config.app_dir())
