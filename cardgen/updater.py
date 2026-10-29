"""Оновлення програми з GitHub.

Два оновлювачі з однаковим інтерфейсом (supported / check / apply / app_dir):

- Updater — запуск з робочої копії git (розробка): `git fetch`, `git pull --ff-only`,
  а якщо змінився requirements.txt — `pip install -r requirements.txt`.
- ArchiveUpdater — зібрана програма (CardGen.exe), git не потрібен: останній коміт
  дізнаємось через GitHub API, код завантажуємо zip-архівом у config.code_dir()
  (поруч кладемо файл .commit з його номером). Якщо нова версія потребує новіших
  бібліотек (cardgen.RUNTIME більший за вбудований у .exe), її не встановлюємо,
  а просимо встановити нову збірку.

Після встановлення програму треба перезапустити. Дані користувача в код не входять
і оновленням не зачіпаються.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

GIT_TIMEOUT = 60
PIP_TIMEOUT = 900
HTTP_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 300
COMMIT_FILE = ".commit"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # без чорних вікон консолі на Windows

Runner = Callable[[list[str], Path, int], subprocess.CompletedProcess]
Fetch = Callable[[str, int], bytes]


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
    # Без консолі git не може спитати пароль у терміналі — нехай одразу повертає помилку.
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


def read_commit(app_dir: Path) -> str:
    try:
        return (Path(app_dir) / COMMIT_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


class Updater:
    """Оновлення робочої копії git (app_dir); python — інтерпретатор для pip."""

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


# --- Зібрана програма: архів з GitHub ------------------------------------------------

def _fetch(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "CardGen", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as e:
        raise UpdateError(f"Сервер оновлень відповів помилкою {e.code}") from e
    except (urllib.error.URLError, OSError) as e:
        raise UpdateError("Сервер оновлень не відповідає. Перевірте інтернет") from e


class ArchiveUpdater:
    """Оновлення зібраної програми.

    app_dir — куди встановлювати код (config.code_dir()); running_dir — код, що працює зараз
    (з нього беремо поточний коміт); repo — "власник/назва" на GitHub;
    runtime — версія бібліотек .exe.
    """

    def __init__(self, app_dir: Path, running_dir: Path, repo: str, branch: str = "main",
                 runtime: int = 0, fetch: Fetch = _fetch):
        self.app_dir = Path(app_dir)
        self.running_dir = Path(running_dir)
        self.repo = repo
        self.branch = branch
        self.runtime = runtime
        self.fetch = fetch
        self.latest_sha = ""

    def _api(self, path: str):
        data = self.fetch(f"https://api.github.com/repos/{self.repo}/{path}", HTTP_TIMEOUT)
        try:
            return json.loads(data)
        except ValueError as e:
            raise UpdateError("Сервер оновлень повернув незрозумілу відповідь") from e

    def supported(self) -> tuple[bool, str]:
        return True, ""

    def check(self) -> UpdateInfo:
        latest = self.latest_sha = self._api(f"commits/{self.branch}")["sha"]
        current = read_commit(self.running_dir)
        info = UpdateInfo(available=latest != current, current=current[:7], latest=latest[:7], branch=self.branch)
        if not info.available:
            return info
        if current:
            try:
                compare = self._api(f"compare/{current}...{latest}")
                info.behind = int(compare.get("ahead_by", 0)) or 1
                info.changes = [c["commit"]["message"].splitlines()[0] for c in reversed(compare.get("commits", []))]
            except (UpdateError, KeyError, IndexError, TypeError):
                info.behind = 1  # невідомий поточний коміт — просто ставимо останню версію
        else:
            info.behind = 1
        if not info.changes:
            info.changes = ["Остання версія програми"]
        return info

    def apply(self, progress: Callable[[str], None] | None = None) -> list[str]:
        say = progress or (lambda _text: None)
        info = self.check()
        if not info.available:
            return []
        say("Завантаження оновлення…")
        latest = self.latest_sha
        archive = self.fetch(f"https://codeload.github.com/{self.repo}/zip/{latest}", DOWNLOAD_TIMEOUT)
        parent = self.app_dir.parent
        parent.mkdir(parents=True, exist_ok=True)
        new = parent / (self.app_dir.name + ".new")
        old = parent / (self.app_dir.name + ".old")
        for leftover in (new, old):
            shutil.rmtree(leftover, ignore_errors=True)
        try:
            _extract(archive, new)
            if read_runtime(new) > self.runtime:
                raise UpdateError("Нова версія потребує оновлених бібліотек — встановіть нову збірку програми. "
                                  "До того працює поточна версія.")
            (new / COMMIT_FILE).write_text(latest + "\n", encoding="utf-8")
            if self.app_dir.exists():
                self.app_dir.rename(old)
            new.rename(self.app_dir)
        except Exception:
            shutil.rmtree(new, ignore_errors=True)
            if old.exists() and not self.app_dir.exists():
                old.rename(self.app_dir)
            raise
        shutil.rmtree(old, ignore_errors=True)
        return info.changes


def _extract(archive: bytes, target: Path) -> None:
    """Розпаковує zip з GitHub (усі файли лежать у папці «репозиторій-коміт/») у target."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile as e:
        raise UpdateError("Завантажений архів пошкоджено") from e
    with zf:
        for member in zf.infolist():
            parts = Path(member.filename).parts[1:]
            if not parts or member.is_dir():
                continue
            if any(p in ("..", "") for p in parts) or Path(member.filename).is_absolute():
                raise UpdateError("Архів оновлення містить недопустимі шляхи")
            path = target.joinpath(*parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(zf.read(member))
    if not (target / "cardgen" / "__init__.py").exists():
        raise UpdateError("В архіві оновлення немає коду програми")


def app_updater() -> Updater | ArchiveUpdater:
    """Оновлювач для поточного способу запуску (див. config)."""
    from . import RUNTIME, config
    if config.frozen():
        return ArchiveUpdater(config.code_dir(), config.app_dir(), config.GITHUB_REPO, runtime=RUNTIME)
    return Updater(config.app_dir())
