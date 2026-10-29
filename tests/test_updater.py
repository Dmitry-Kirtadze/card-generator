"""Оновлення програми з git: тимчасовий «сервер» (bare-репозиторій) і дві робочі копії."""
import shutil
import subprocess
from pathlib import Path

import pytest

from cardgen.ui.update_ui import UpdateDialog, changes_text
from cardgen.updater import UpdateError, UpdateInfo, Updater, _run, read_runtime

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


# --- Зібрана програма: перше встановлення й версія бібліотек ------------------------

def set_runtime(dev: Path, runtime: int) -> None:
    (dev / "cardgen").mkdir(exist_ok=True)
    commit(dev, "cardgen/__init__.py", f'__version__ = "x"\nRUNTIME = {runtime}\n', f"Бібліотеки {runtime}")
    git(dev, "push", "-q", "origin", "main")


def test_first_install_clones(repos, tmp_path):
    server, _, dev = repos
    set_runtime(dev, 1)
    target = tmp_path / "user" / "app"
    updater = Updater(target, python=None, repo_url=str(server), runtime=1)
    assert updater.supported() == (True, "")
    info = updater.check()
    assert info.available and info.branch == "main"
    updater.apply()
    assert (target / ".git").exists() and read_runtime(target) == 1
    assert not updater.check().available


def test_newer_runtime_needs_new_build(repos, tmp_path):
    server, _, dev = repos
    target = tmp_path / "app"
    updater = Updater(target, python=None, repo_url=str(server), runtime=1)
    updater.apply()
    set_runtime(dev, 2)
    with pytest.raises(UpdateError, match="нову збірку"):
        updater.apply()


def test_frozen_does_not_run_pip(repos, tmp_path):
    server, _, dev = repos
    target = tmp_path / "app"
    calls = []

    def runner(cmd, cwd, timeout):
        calls.append(cmd[0])
        return _run(cmd, cwd, timeout)

    updater = Updater(target, runner=runner, python=None, repo_url=str(server))
    updater.apply()
    commit(dev, "requirements.txt", "PySide6\nopenpyxl\n", "Нова бібліотека")
    git(dev, "push", "-q", "origin", "main")
    updater.apply()
    assert set(calls) == {"git"}


def test_launcher_picks_code(tmp_path, monkeypatch):
    import launcher
    bundled = tmp_path / "bundle" / "app"
    updated = tmp_path / "local" / "CardGen" / "app"
    for code, runtime in ((bundled, 2), (updated, 2)):
        (code / "cardgen").mkdir(parents=True)
        (code / "cardgen" / "__init__.py").write_text(f"RUNTIME = {runtime}\n", encoding="utf-8")
    monkeypatch.setattr(launcher, "bundled_code", lambda: bundled)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert launcher.candidates() == [bundled]  # ще не копія git
    (updated / ".git").mkdir()
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
