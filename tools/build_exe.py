"""Збірка CardGen.exe (PyInstaller), установника (Inno Setup) і встановлення.

    .venv\\Scripts\\python tools\\build_exe.py            — програма в dist\\CardGen і установник
        dist\\Встановити Генератор карток <версія>.exe — його можна надіслати іншій людині
    .venv\\Scripts\\python tools\\build_exe.py --install  — те саме й встановити на цей комп'ютер

У збірці: Python, бібліотеки (PySide6, Pillow, openpyxl) і копія коду в папці app/
(див. launcher.py). Код оновлюється з GitHub без перезбирання; нова збірка потрібна,
лише коли збільшено cardgen.RUNTIME (нові бібліотеки).
"""
from __future__ import annotations

import argparse
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
    # Номер коміту вбудованого коду: з ним оновлювач порівнює останню версію на GitHub.
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
    (target / ".commit").write_text(head.stdout.strip() + "\n", encoding="utf-8")
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


ISS = """; Згенеровано tools/build_exe.py
[Setup]
AppId={{{{48EC309C-C11B-4838-8FF4-0E8B696904A8}}
AppName={title}
AppVersion={version}
AppVerName={title} {version}
AppPublisher=robostore.com.ua
DefaultDirName={{localappdata}}\\Programs\\{name}
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={dist}
OutputBaseFilename={setup_name}
SetupIconFile={icon}
UninstallDisplayIcon={{app}}\\{name}.exe
UninstallDisplayName={title}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "uk"; MessagesFile: "compiler:Languages\\Ukrainian.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"

[InstallDelete]
; бібліотеки попередньої збірки — щоб не лишились старі файли
Type: filesandordirs; Name: "{{app}}\\_internal"

[Files]
Source: "{built}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{autoprograms}}\\{title}"; Filename: "{{app}}\\{name}.exe"
Name: "{{autodesktop}}\\{title}"; Filename: "{{app}}\\{name}.exe"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{name}.exe"; Description: "{{cm:LaunchProgram,{title}}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; завантажений оновлений код і журнал; дані користувача (Документи) не чіпаємо
Type: filesandordirs; Name: "{{localappdata}}\\{name}\\app"
Type: files; Name: "{{localappdata}}\\{name}\\cardgen.log"
"""


def iscc() -> Path:
    places = [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
              Path(os.environ.get("ProgramFiles(x86)", "")), Path(os.environ.get("ProgramFiles", ""))]
    for place in places:
        path = place / "Inno Setup 6" / "ISCC.exe"
        if path.exists():
            return path
    sys.exit("Не знайдено Inno Setup 6. Встановіть: winget install JRSoftware.InnoSetup")


def make_setup(built: Path) -> Path:
    """Установник: один .exe, який можна надіслати іншій людині."""
    sys.path.insert(0, str(ROOT))
    from cardgen import __version__
    setup_name = f"Встановити {TITLE} {__version__}"
    script = BUILD / f"{NAME}.iss"
    # Inno Setup читає кирилицю лише з UTF-8 з BOM
    script.write_text(ISS.format(title=TITLE, version=__version__, name=NAME, dist=DIST, built=built,
                                 icon=BUILD / "cardgen.ico", setup_name=setup_name), encoding="utf-8-sig")
    subprocess.run([str(iscc()), "/Q", str(script)], check=True)
    return DIST / f"{setup_name}.exe"


def install(setup: Path) -> None:
    """Тихо встановлює на цей комп'ютер через той самий установник."""
    subprocess.run([str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/TASKS=desktopicon"], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="встановити на цей комп'ютер після збірки")
    args = parser.parse_args()
    built = build()
    print(f"Зібрано: {built}")
    setup = make_setup(built)
    print(f"Установник: {setup}")
    if args.install:
        install(setup)
        print(f"Встановлено: {Path(os.environ['LOCALAPPDATA']) / 'Programs' / NAME}")


if __name__ == "__main__":
    main()
