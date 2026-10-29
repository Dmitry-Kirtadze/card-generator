import zipfile
from pathlib import Path

import pytest

from cardgen.model import IconElement, TextElement, TextStyle
from cardgen.storage import StorageError, Workspace
from cardgen.transfer import export_category, import_category

SYSTEM_FONT = Path(r"C:\Windows\Fonts\arial.ttf")


@pytest.fixture
def source(workspace, full_template, tmp_path):
    """Категорія з шаблоном, ресурсами категорії, таблицею та файлами бібліотеки."""
    c = workspace.create_category("Кабель AWG")
    icon = tmp_path / "rocket.svg"
    icon.write_text("<svg>1</svg>", encoding="utf-8")
    bg = tmp_path / "circuit.png"
    bg.write_bytes(b"\x89PNG bg")
    unused = tmp_path / "unused.png"
    unused.write_bytes(b"\x89PNG unused")
    workspace.add_to_library("icons", icon)
    workspace.add_to_library("backgrounds", bg)
    workspace.add_to_library("icons", unused)

    workspace.save_template(c.id, full_template)
    workspace.create_template(c.id, "Характеристики")
    (workspace.category_dir(c.id) / "assets" / "logo.png").write_bytes(b"logo")
    (workspace.tables_dir(c.id, full_template.id) / "кабелі.xlsx").write_bytes(b"PK table")
    return c


def snapshot(workspace: Workspace, category_id: str) -> dict[str, bytes]:
    """Усі файли категорії, крім category.json (там новий id і дата)."""
    folder = workspace.category_dir(category_id)
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in folder.rglob("*") if p.is_file() and p.name != "category.json"
    }


def test_export_import_roundtrip_in_other_workspace(workspace, source, full_template, tmp_path):
    archive = export_category(workspace, source.id, tmp_path / "кабель.cardgen.zip")

    other = Workspace(tmp_path / "other_pc")
    imported = import_category(other, archive)

    assert imported.name == "Кабель AWG"
    assert snapshot(other, imported.id) == snapshot(workspace, source.id)
    assert other.load_template(imported.id, full_template.id) == full_template
    # використані ресурси бібліотеки переїхали, невикористані — ні
    assert other.resolve_asset("library:icons/rocket.svg").read_text(encoding="utf-8") == "<svg>1</svg>"
    assert other.resolve_asset("library:backgrounds/circuit.png").is_file()
    assert not other.resolve_asset("library:icons/unused.png").exists()


def test_import_into_same_workspace_gets_new_id_and_name(workspace, source, tmp_path):
    archive = export_category(workspace, source.id, tmp_path / "a.cardgen.zip")
    imported = import_category(workspace, archive)
    assert imported.id != source.id
    assert imported.name == "Кабель AWG (імпорт)"
    assert snapshot(workspace, imported.id) == snapshot(workspace, source.id)
    # однакові файли бібліотеки не продубльовано
    assert [p.name for p in workspace.list_library("icons")] == ["rocket.svg", "unused.png"]


def test_library_conflict_renamed_and_refs_rewritten(workspace, source, full_template, tmp_path):
    archive = export_category(workspace, source.id, tmp_path / "a.cardgen.zip")

    other = Workspace(tmp_path / "other_pc")
    other_icon = tmp_path / "x" / "rocket.svg"
    other_icon.parent.mkdir()
    other_icon.write_text("<svg>інша</svg>", encoding="utf-8")
    other.add_to_library("icons", other_icon)

    imported = import_category(other, archive)
    template = other.load_template(imported.id, full_template.id)
    icon = next(e for e in template.elements if isinstance(e, IconElement))
    assert icon.asset == "library:icons/rocket (2).svg"
    assert other.resolve_asset(icon.asset).read_text(encoding="utf-8") == "<svg>1</svg>"
    # чужий файл не зачеплено
    assert other.resolve_asset("library:icons/rocket.svg").read_text(encoding="utf-8") == "<svg>інша</svg>"


@pytest.mark.skipif(not SYSTEM_FONT.is_file(), reason="немає системного шрифту")
def test_used_fonts_exported(workspace, tmp_path):
    workspace.add_to_library("fonts", SYSTEM_FONT)
    c = workspace.create_category("Кабель")
    t = workspace.create_template(c.id, "Обкладинка")
    t.elements.append(TextElement(style=TextStyle(font_family="Arial")))
    workspace.save_template(c.id, t)

    archive = export_category(workspace, c.id, tmp_path / "a.cardgen.zip")
    other = Workspace(tmp_path / "other_pc")
    import_category(other, archive)
    assert "Arial" in other.library_fonts()


def test_duplicate_keeps_resources_working(workspace, source, full_template):
    copy = workspace.duplicate_category(source.id)
    template = workspace.load_template(copy.id, full_template.id)
    for ref in ("category:assets/logo.png",):
        assert workspace.resolve_asset(ref, copy.id).is_file()
    icon = next(e for e in template.elements if isinstance(e, IconElement))
    assert workspace.resolve_asset(icon.asset).is_file()


# --- Захист від чужих і зламаних архівів ---------------------------------

def make_zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


MANIFEST = b'{"format": "cardgen-category", "schema_version": 1}'


@pytest.mark.parametrize("bad_name", [
    "category/../../evil.txt",
    "../evil.txt",
    "/abs/evil.txt",
    "C:/evil.txt",
    "other/evil.txt",
    "library/icons/../../evil.txt",
    "library/scripts/evil.py",
])
def test_zip_slip_rejected(workspace, tmp_path, bad_name):
    archive = make_zip(tmp_path / "bad.zip", {
        "manifest.json": MANIFEST,
        "category/category.json": b'{"name": "X"}',
        bad_name: b"evil",
    })
    with pytest.raises(StorageError, match="Підозрілий"):
        import_category(workspace, archive)
    assert workspace.list_categories() == []
    assert not list(tmp_path.rglob("evil*"))


def test_foreign_zip_rejected(workspace, tmp_path):
    archive = make_zip(tmp_path / "photos.zip", {"photo.jpg": b"x"})
    with pytest.raises(StorageError, match="не створено"):
        import_category(workspace, archive)


def test_not_a_zip_rejected(workspace, tmp_path):
    path = tmp_path / "a.cardgen.zip"
    path.write_text("hello")
    with pytest.raises(StorageError, match="не є архівом"):
        import_category(workspace, path)


def test_newer_format_rejected(workspace, tmp_path):
    archive = make_zip(tmp_path / "new.zip", {
        "manifest.json": b'{"format": "cardgen-category", "schema_version": 99}',
    })
    with pytest.raises(StorageError, match="новішою"):
        import_category(workspace, archive)


def test_failed_import_leaves_no_temp(workspace, tmp_path):
    archive = make_zip(tmp_path / "bad.zip", {"manifest.json": MANIFEST})
    with pytest.raises(StorageError):
        import_category(workspace, archive)
    assert not [p for p in workspace.root.iterdir() if p.name.startswith(".import-")]
