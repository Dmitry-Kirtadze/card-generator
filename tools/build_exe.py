"""Збірка CardGen.exe (PyInstaller) і встановлення на цей комп'ютер.

    .venv\\Scripts\\python tools\\build_exe.py            — зібрати в dist\\CardGen
    .venv\\Scripts\\python tools\\build_exe.py --install  — зібрати й встановити в
        %LOCALAPPDATA%\\Programs\\CardGen, ярлики на Робочому столі й у меню «Пуск»

У збірці: Python, бібліотеки (PySide6, Pillow, openpyxl) і копія коду в папці app/
(див. launcher.py). Код оновлюється через git без перезбирання; нова збірка потрібна,
лише коли збільшено cardgen.RUNTIME (нові бібліотеки).
"""
from __future__ import annotations

import argparse
import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"
NAME = "CardGen"
TITLE = "Генератор карток"

# Модулі, яких поточний код може й не імпортувати, але оновлений через git — може.
EXTRA_IMPORTS = [
    "PySide6.QtSvg", "PySide6.QtNetwork", "PySide6.QtPrintSupport",
    "csv", "zipfile", "urllib.request", "xml.etree.ElementTree", "json", "uuid", "hashlib",
    "concurrent.futures", "tempfile", "difflib", "colorsys", "statistics", "webbrowser",
]
EXCLUDES = ["tkinter", "pytest", "pytestqt", "PyInstaller", "unittest", "pydoc_data"]


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [f for f in out.decode("utf-8").split("\0") if f]


def copy_code(target: Path) -> list[str]:
    """Вбудована копія коду: те, що потрібно для запуску (без тестів, інструментів, прикладів)."""
    shutil.rmtree(target, ignore_errors=True)
    keep = ("cardgen/", "market/")
    files = [f for f in tracked_files() if f.startswith(keep) or f in ("main.py", "requirements.txt")]
    for name in files:
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target / name)
    return [f[:-3].replace("/", ".").removesuffix(".__init__") for f in files
            if f.startswith("cardgen/") and f.endswith(".py")]


def make_icon(path: Path) -> None:
    from PIL import Image, ImageDraw

    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((16, 16, 240, 240), 44, fill="#2563EB")
    d.rounded_rectangle((52, 44, 204, 212), 18, fill="white")
    d.rounded_rectangle((70, 62, 186, 130), 10, fill="#93C5FD")
    d.polygon([(78, 124), (112, 88), (136, 112), (152, 98), (180, 124)], fill="#1D4ED8")
    for y, w in ((148, 116), (168, 90), (188, 64)):
        d.rounded_rectangle((70, y, 70 + w, y + 10), 5, fill="#1E3A8A")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])


SPEC = '''# Згенеровано tools/build_exe.py
a = Analysis(
    [{launcher!r}],
    pathex=[{root!r}],
    hiddenimports={hidden!r},
    excludes={excludes!r},
    datas=[({code!r}, "app")],
    noarchive=False,
)
# Код програми не вшиваємо в архів: він лежить у app/ як звичайні файли, щоб його
# можна було замінити оновленою копією з git (launcher.py обирає, яку взяти).
a.pure = [m for m in a.pure if not (m[0] == "cardgen" or m[0].startswith("cardgen."))]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name={name!r}, icon={icon!r},
          console=False, upx=False, version=None)
coll = COLLECT(exe, a.binaries, a.datas, name={name!r}, upx=False)
'''


def build() -> Path:
    code = BUILD / "app"
    modules = copy_code(code)
    icon = BUILD / "cardgen.ico"
    make_icon(icon)
    spec = BUILD / f"{NAME}.spec"
    spec.write_text(SPEC.format(launcher=str(ROOT / "launcher.py"), root=str(ROOT), code=str(code),
                                hidden=modules + EXTRA_IMPORTS, excludes=EXCLUDES, name=NAME,
                                icon=str(icon)), encoding="utf-8")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--log-level", "WARN",
                    "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller"), str(spec)],
                   cwd=ROOT, check=True)
    return DIST / NAME


def install_dir() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "Programs" / NAME


def install(built: Path) -> Path:
    target = install_dir()
    if target.exists():
        try:
            shutil.rmtree(target)
        except PermissionError:
            sys.exit(f"Закрийте програму «{TITLE}» і повторіть встановлення ({target} зайнято).")
    shutil.copytree(built, target)
    exe = target / f"{NAME}.exe"
    script = (
        "$s = New-Object -ComObject WScript.Shell;"
        "foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {"
        # WScript.Shell не зберігає файл з кирилицею в назві — зберігаємо латиницею й перейменовуємо
        f"  $tmp = Join-Path $dir '{NAME}.lnk'; $final = Join-Path $dir '{TITLE}.lnk';"
        "  $l = $s.CreateShortcut($tmp);"
        f"  $l.TargetPath = '{exe}'; $l.WorkingDirectory = '{target}'; $l.IconLocation = '{exe},0';"
        "  $l.Save(); Move-Item -Force -LiteralPath $tmp -Destination $final }"
    )
    # -EncodedCommand (UTF-16), щоб кирилиця в команді дійшла без змін
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", encoded], check=True)
    return exe


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="встановити після збірки")
    args = parser.parse_args()
    built = build()
    print(f"Зібрано: {built}")
    if args.install:
        print(f"Встановлено: {install(built)}")


if __name__ == "__main__":
    main()
