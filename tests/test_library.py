from pathlib import Path

import pytest

from cardgen.storage import StorageError, font_family

SYSTEM_FONT = Path(r"C:\Windows\Fonts\arial.ttf")
needs_font = pytest.mark.skipif(not SYSTEM_FONT.is_file(), reason="немає системного шрифту")


@pytest.fixture
def png(tmp_path) -> Path:
    path = tmp_path / "rocket.png"
    path.write_bytes(b"\x89PNG fake 1")
    return path


def test_add_icon_returns_ref(workspace, png):
    ref = workspace.add_to_library("icons", png)
    assert ref == "library:icons/rocket.png"
    assert workspace.resolve_asset(ref).read_bytes() == png.read_bytes()
    assert [p.name for p in workspace.list_library("icons")] == ["rocket.png"]


def test_same_file_not_duplicated(workspace, png):
    assert workspace.add_to_library("icons", png) == workspace.add_to_library("icons", png)
    assert len(workspace.list_library("icons")) == 1


def test_different_file_same_name_gets_new_name(workspace, png, tmp_path):
    workspace.add_to_library("icons", png)
    other = tmp_path / "other" / "rocket.png"
    other.parent.mkdir()
    other.write_bytes(b"\x89PNG fake 2")
    assert workspace.add_to_library("icons", other) == "library:icons/rocket (2).png"


def test_wrong_extension_rejected(workspace, tmp_path):
    bad = tmp_path / "virus.exe"
    bad.write_bytes(b"MZ")
    with pytest.raises(StorageError, match="Непідтримуваний"):
        workspace.add_to_library("icons", bad)
    with pytest.raises(StorageError):
        workspace.add_to_library("secrets", bad)


def test_fake_font_rejected(workspace, tmp_path):
    fake = tmp_path / "fake.ttf"
    fake.write_bytes(b"not a font")
    with pytest.raises(StorageError, match="не є шрифтом"):
        workspace.add_to_library("fonts", fake)
    assert workspace.list_library("fonts") == []


@needs_font
def test_font_family_index(workspace):
    workspace.add_to_library("fonts", SYSTEM_FONT)
    assert workspace.library_fonts() == {"Arial": [workspace.library_dir / "fonts" / "arial.ttf"]}
    assert font_family(SYSTEM_FONT) == "Arial"


def test_remove_from_library(workspace, png):
    workspace.add_to_library("icons", png)
    workspace.remove_from_library("icons", "rocket.png")
    assert workspace.list_library("icons") == []
    with pytest.raises(StorageError):
        workspace.remove_from_library("icons", "rocket.png")


# --- Таблиці даних шаблону -----------------------------------------------

def test_tables_add_list_delete(workspace, tmp_path):
    c = workspace.create_category("Кабель")
    t = workspace.create_template(c.id, "Обкладинка")
    xlsx = tmp_path / "кабелі.xlsx"
    xlsx.write_bytes(b"PK fake")

    first = workspace.add_table(c.id, t.id, xlsx)
    second = workspace.add_table(c.id, t.id, xlsx)
    assert first.name == "кабелі.xlsx" and second.name == "кабелі (2).xlsx"
    assert {p.name for p in workspace.list_tables(c.id, t.id)} == {first.name, second.name}

    workspace.delete_table(c.id, t.id, first.name)
    assert [p.name for p in workspace.list_tables(c.id, t.id)] == [second.name]


def test_table_wrong_format_rejected(workspace, tmp_path):
    c = workspace.create_category("Кабель")
    t = workspace.create_template(c.id, "Обкладинка")
    doc = tmp_path / "дані.docx"
    doc.write_bytes(b"x")
    with pytest.raises(StorageError):
        workspace.add_table(c.id, t.id, doc)
