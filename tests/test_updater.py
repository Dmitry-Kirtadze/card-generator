"""Оновлення програми з git: тимчасовий «сервер» (bare-репозиторій) і дві робочі копії."""
import io
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from cardgen.ui.update_ui import UpdateDialog, changes_text
from cardgen.updater import ArchiveUpdater, UpdateError, UpdateInfo, Updater, _extract, _run, read_commit

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="немає git")


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def commit(repo: Path, name: str, content: str, message: str) -> None:
    (repo / name).write_text(content, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repos(tmp_path):
    """server — сервер, app — копія користувача, dev — копія розробника."""
    server = tmp_path / "server.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(server))
    dev = tmp_path / "dev"
    git(tmp_path, "clone", "-q", str(server), str(dev))
    for repo in (dev,):
        git(repo, "config", "user.email", "test@example.com")
        git(repo, "config", "user.name", "Test")
    git(dev, "checkout", "-q", "-b", "main")
    commit(dev, "main.py", "print('v1')\n", "Перша версія")
    commit(dev, "requirements.txt", "PySide6\n", "Залежності")
    git(dev, "push", "-q", "origin", "main")
    app = tmp_path / "app"
    git(tmp_path, "clone", "-q", str(server), str(app))
    return server, app, dev


def test_up_to_date(repos):
    _, app, _ = repos
    info = Updater(app).check()
    assert not info.available and info.behind == 0 and info.branch == "main"


def test_check_and_apply_update(repos):
    _, app, dev = repos
    commit(dev, "main.py", "print('v2')\n", "Нова функція")
    commit(dev, "README.md", "docs\n", "Документація")
    git(dev, "push", "-q", "origin", "main")
    updater = Updater(app)
    info = updater.check()
    assert info.available and info.behind == 2
    assert info.changes == ["Документація", "Нова функція"]
    applied = updater.apply()
    assert applied == ["Документація", "Нова функція"]
    assert (app / "main.py").read_text(encoding="utf-8") == "print('v2')\n"
    assert not updater.check().available


def test_requirements_change_installs_libraries(repos):
    _, app, dev = repos
    commit(dev, "requirements.txt", "PySide6\nopenpyxl\n", "Нова бібліотека")
    git(dev, "push", "-q", "origin", "main")
    pip_calls = []

    def runner(cmd, cwd, timeout):
        if cmd[0] != "git":
            pip_calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return _run(cmd, cwd, timeout)

    Updater(app, runner=runner, python="python").apply()
    assert pip_calls == [["python", "-m", "pip", "install", "--quiet", "-r", "requirements.txt"]]


def test_local_changes_block_update(repos):
    _, app, dev = repos
    commit(dev, "main.py", "print('v2')\n", "Нова версія")
    git(dev, "push", "-q", "origin", "main")
    (app / "main.py").write_text("print('мої правки')\n", encoding="utf-8")
    with pytest.raises(UpdateError, match="локальні зміни"):
        Updater(app).apply()
    assert (app / "main.py").read_text(encoding="utf-8") == "print('мої правки')\n"


def test_user_data_not_touched(repos):
    _, app, dev = repos
    (app / "workspace").mkdir()  # дані користувача (у справжньому проєкті — в .gitignore)
    (app / "workspace" / "data.json").write_text("{}", encoding="utf-8")
    commit(dev, "main.py", "print('v2')\n", "Нова версія")
    git(dev, "push", "-q", "origin", "main")
    Updater(app).apply()
    assert (app / "workspace" / "data.json").read_text(encoding="utf-8") == "{}"


def test_not_supported_without_git_or_remote(tmp_path):
    assert Updater(tmp_path).supported()[0] is False
    git(tmp_path, "init", "-q")
    ok, reason = Updater(tmp_path).supported()
    assert not ok and "remote" in reason
    with pytest.raises(UpdateError):
        Updater(tmp_path).check()


def test_server_unreachable(repos, tmp_path):
    _, app, _ = repos
    git(app, "remote", "set-url", "origin", str(tmp_path / "немає.git"))
    with pytest.raises(UpdateError):
        Updater(app).check()


# --- Зібрана програма: оновлення архівом з GitHub ------------------------------------

class FakeGitHub:
    """Відповіді GitHub API й архіви codeload для ArchiveUpdater."""

    def __init__(self):
        self.commits: list[tuple[str, str, int]] = []  # (sha, опис, RUNTIME)
        self.offline = False

    def push(self, message: str, runtime: int = 1) -> str:
        sha = f"{len(self.commits) + 1:040x}"
        self.commits.append((sha, message, runtime))
        return sha

    def archive(self, sha: str) -> bytes:
        runtime = next(r for s, _, r in self.commits if s == sha)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr(f"card-generator-{sha}/cardgen/__init__.py", f"RUNTIME = {runtime}\n")
            zf.writestr(f"card-generator-{sha}/main.py", f"# {sha}\n")
        return buffer.getvalue()

    def __call__(self, url: str, timeout: int) -> bytes:
        if self.offline:
            raise UpdateError("Сервер оновлень не відповідає. Перевірте інтернет")
        shas = [c[0] for c in self.commits]
        if url.endswith("/commits/main"):
            return json.dumps({"sha": shas[-1]}).encode()
        if "/compare/" in url:
            base, head = url.rsplit("/", 1)[1].split("...")
            if base not in shas:
                raise UpdateError("Сервер оновлень відповів помилкою 404")
            new = self.commits[shas.index(base) + 1: shas.index(head) + 1]
            return json.dumps({"ahead_by": len(new), "commits": [
                {"commit": {"message": m + "\n\nдеталі"}} for _, m, _ in new]}).encode()  # від старих до нових
        if "codeload.github.com" in url:
            return self.archive(url.rsplit("/", 1)[1])
        raise AssertionError(url)


def bundled(tmp_path: Path, sha: str) -> Path:
    code = tmp_path / "bundle" / "app"
    (code / "cardgen").mkdir(parents=True)
    (code / "cardgen" / "__init__.py").write_text("RUNTIME = 1\n", encoding="utf-8")
    (code / ".commit").write_text(sha + "\n", encoding="utf-8")
    return code


def test_archive_update_cycle(tmp_path):
    hub = FakeGitHub()
    first = hub.push("Перша версія")
    running = bundled(tmp_path, first)
    target = tmp_path / "user" / "app"
    updater = ArchiveUpdater(target, running, "me/card-generator", runtime=1, fetch=hub)
    assert updater.supported() == (True, "")
    assert not updater.check().available

    hub.push("Нова функція")
    last = hub.push("Виправлення")
    info = updater.check()
    assert info.available and info.behind == 2
    assert info.changes == ["Виправлення", "Нова функція"]
    assert updater.apply() == ["Виправлення", "Нова функція"]
    assert read_commit(target) == last and (target / "main.py").read_text(encoding="utf-8") == f"# {last}\n"

    # Після перезапуску працює вже завантажений код — оновлень немає.
    assert not ArchiveUpdater(target, target, "me/card-generator", runtime=1, fetch=hub).check().available
    assert not list(target.parent.glob("app.*"))  # тимчасові папки прибрано


def test_archive_update_unknown_current(tmp_path):
    hub = FakeGitHub()
    hub.push("Остання")
    running = bundled(tmp_path, "f" * 40)  # збірка з коміту, якого немає на сервері
    updater = ArchiveUpdater(tmp_path / "app", running, "me/r", runtime=1, fetch=hub)
    info = updater.check()
    assert info.available and info.changes == ["Остання версія програми"]
    updater.apply()
    assert (tmp_path / "app" / ".commit").exists()


def test_archive_newer_runtime_not_installed(tmp_path):
    hub = FakeGitHub()
    first = hub.push("v1")
    target = tmp_path / "app"
    ArchiveUpdater(target, bundled(tmp_path, "0" * 40), "me/r", runtime=1, fetch=hub).apply()
    hub.push("Нові бібліотеки", runtime=2)
    with pytest.raises(UpdateError, match="нову збірку"):
        ArchiveUpdater(target, target, "me/r", runtime=1, fetch=hub).apply()
    assert read_commit(target) == first  # робочий код не зачеплено
    assert not list(tmp_path.glob("app.*"))


def test_archive_offline(tmp_path):
    hub = FakeGitHub()
    hub.push("v1")
    hub.offline = True
    with pytest.raises(UpdateError, match="інтернет"):
        ArchiveUpdater(tmp_path / "app", bundled(tmp_path, "0" * 40), "me/r", fetch=hub).check()


def test_archive_rejects_bad_paths(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("repo-x/../../evil.txt", "x")
    with pytest.raises(UpdateError):
        _extract(buffer.getvalue(), tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()


def test_launcher_picks_code(tmp_path, monkeypatch):
    import launcher
    bundled = tmp_path / "bundle" / "app"
    updated = tmp_path / "local" / "CardGen" / "app"
    for code, runtime in ((bundled, 2), (updated, 2)):
        (code / "cardgen").mkdir(parents=True)
        (code / "cardgen" / "__init__.py").write_text(f"RUNTIME = {runtime}\n", encoding="utf-8")
    monkeypatch.setattr(launcher, "bundled_code", lambda: bundled)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert launcher.candidates() == [bundled]  # ще нічого не завантажено
    (updated / ".commit").write_text("x", encoding="utf-8")
    assert launcher.candidates() == [updated, bundled]
    (updated / "cardgen" / "__init__.py").write_text("RUNTIME = 3\n", encoding="utf-8")
    assert launcher.candidates() == [bundled]  # потрібні новіші бібліотеки


# --- Вікно оновлення -----------------------------------------------------------------

def test_update_dialog_states(qtbot, workspace, repos):
    _, app, _ = repos
    dialog = UpdateDialog(Updater(app), workspace)
    qtbot.addWidget(dialog)
    dialog.show_result(UpdateInfo(available=True, behind=2, changes=["А", "Б"], current="aaa", latest="bbb"), False)
    assert dialog.install_button.isEnabled() and "2 змін" in dialog.status.text()
    dialog.show_result(UpdateInfo(available=False, current="aaa"), False)
    assert "остання версія" in dialog.status.text()
    dialog.show_result(UpdateError("немає інтернету"), False)
    assert "немає інтернету" in dialog.status.text()
    dialog.show_result(UpdateInfo(available=True, changes=["А"]), True)
    assert dialog.restart_button.isVisibleTo(dialog)
    dialog.auto.setChecked(False)
    assert workspace.editor_settings()["auto_update"] is False


def test_dialog_real_check_in_background(qtbot, workspace, repos):
    _, app, dev = repos
    commit(dev, "main.py", "print('v2')\n", "Нова версія")
    git(dev, "push", "-q", "origin", "main")
    dialog = UpdateDialog(Updater(app), workspace)
    qtbot.addWidget(dialog)
    dialog.check()
    qtbot.waitUntil(lambda: dialog.install_button.isEnabled(), timeout=20000)
    dialog.install()
    qtbot.waitUntil(lambda: dialog.installed, timeout=20000)
    assert (app / "main.py").read_text(encoding="utf-8") == "print('v2')\n"


def test_changes_text_limit():
    text = changes_text([str(i) for i in range(20)], limit=3)
    assert text.splitlines() == ["• 0", "• 1", "• 2", "… і ще 17"]
