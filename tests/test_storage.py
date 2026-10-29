import pytest

from cardgen.storage import StorageError, Workspace


# --- Категорії -----------------------------------------------------------

def test_workspace_creates_structure(workspace):
    for section in ("fonts", "icons", "backgrounds"):
        assert (workspace.library_dir / section).is_dir()
    assert workspace.categories_dir.is_dir()


def test_create_and_list_categories(workspace):
    a = workspace.create_category("Кабель AWG")
    b = workspace.create_category("Конденсатор")
    names = [c.name for c in workspace.list_categories()]
    assert names == ["Кабель AWG", "Конденсатор"]
    assert (workspace.categories_dir / a.id / "templates").is_dir()
    assert (workspace.categories_dir / b.id / "assets").is_dir()


def test_category_survives_reopen(workspace):
    created = workspace.create_category("Кабель AWG")
    reopened = Workspace(workspace.root)
    assert reopened.get_category(created.id) == created


def test_category_name_trimmed_and_required(workspace):
    assert workspace.create_category("  Кабель   AWG ").name == "Кабель AWG"
    with pytest.raises(StorageError):
        workspace.create_category("   ")


def test_duplicate_category_name_rejected(workspace):
    workspace.create_category("Кабель")
    with pytest.raises(StorageError, match="вже існує"):
        workspace.create_category("кабель")


def test_rename_category(workspace):
    c = workspace.create_category("Кабель")
    workspace.rename_category(c.id, "Кабель AWG")
    assert workspace.get_category(c.id).name == "Кабель AWG"
    # зміна лише регістру своєї ж назви дозволена
    workspace.rename_category(c.id, "КАБЕЛЬ AWG")


def test_rename_category_to_taken_name_rejected(workspace):
    workspace.create_category("Кабель")
    c = workspace.create_category("Дріт")
    with pytest.raises(StorageError):
        workspace.rename_category(c.id, "Кабель")


def test_delete_category_moves_to_trash(workspace):
    c = workspace.create_category("Кабель")
    workspace.create_template(c.id, "Обкладинка")
    trashed = workspace.delete_category(c.id)
    assert workspace.list_categories() == []
    assert (trashed / "category.json").is_file()
    with pytest.raises(StorageError):
        workspace.get_category(c.id)


def test_duplicate_category_is_independent(workspace, full_template):
    c = workspace.create_category("Кабель")
    workspace.save_template(c.id, full_template)
    (workspace.category_dir(c.id) / "assets" / "logo.png").write_bytes(b"png")

    copy = workspace.duplicate_category(c.id)
    assert copy.name == "Кабель (копія)"
    assert copy.id != c.id
    assert (workspace.category_dir(copy.id) / "assets" / "logo.png").read_bytes() == b"png"
    assert workspace.load_template(copy.id, full_template.id) == full_template

    workspace.rename_template(copy.id, full_template.id, "Змінено в копії")
    assert workspace.load_template(c.id, full_template.id).name == full_template.name

    assert workspace.duplicate_category(c.id).name == "Кабель (копія 2)"


def test_broken_category_skipped(workspace):
    workspace.create_category("Добра")
    broken = workspace.categories_dir / "broken"
    broken.mkdir()
    (broken / "category.json").write_text("{не json", encoding="utf-8")
    assert [c.name for c in workspace.list_categories()] == ["Добра"]


# --- Шаблони -------------------------------------------------------------

def test_create_save_load_template(workspace, full_template):
    c = workspace.create_category("Кабель")
    created = workspace.create_template(c.id, "Характеристики", width=1200, height=1200)
    assert workspace.load_template(c.id, created.id).width == 1200
    assert (workspace.template_dir(c.id, created.id) / "tables").is_dir()

    workspace.save_template(c.id, full_template)
    assert workspace.load_template(c.id, full_template.id) == full_template
    assert [t.name for t in workspace.list_templates(c.id)] == ["Обкладинка", "Характеристики"]


def test_template_names_unique_within_category_only(workspace):
    a = workspace.create_category("Кабель")
    b = workspace.create_category("Конденсатор")
    workspace.create_template(a.id, "Обкладинка")
    workspace.create_template(b.id, "Обкладинка")
    with pytest.raises(StorageError):
        workspace.create_template(a.id, "обкладинка")


def test_rename_and_delete_template(workspace):
    c = workspace.create_category("Кабель")
    t = workspace.create_template(c.id, "Обкладинка")
    workspace.rename_template(c.id, t.id, "Головна")
    assert workspace.load_template(c.id, t.id).name == "Головна"
    workspace.delete_template(c.id, t.id)
    assert workspace.list_templates(c.id) == []


def test_duplicate_template(workspace, full_template):
    c = workspace.create_category("Кабель")
    workspace.save_template(c.id, full_template)
    copy = workspace.duplicate_template(c.id, full_template.id)
    assert copy.id != full_template.id
    assert copy.name == "Обкладинка (копія)"
    assert copy.elements == full_template.elements
    assert len(workspace.list_templates(c.id)) == 2


def test_save_leaves_no_temp_files(workspace, full_template):
    c = workspace.create_category("Кабель")
    workspace.save_template(c.id, full_template)
    workspace.save_template(c.id, full_template)
    assert not list(workspace.root.rglob("*.tmp"))


def test_corrupt_template_reports_error(workspace):
    c = workspace.create_category("Кабель")
    t = workspace.create_template(c.id, "Обкладинка")
    (workspace.template_dir(c.id, t.id) / "template.json").write_text(
        '{"elements": [{"type": "hologram"}]}', encoding="utf-8")
    with pytest.raises(StorageError, match="пошкоджено"):
        workspace.load_template(c.id, t.id)
    assert workspace.list_templates(c.id) == []


# --- Ресурси -------------------------------------------------------------

def test_resolve_asset(workspace):
    c = workspace.create_category("Кабель")
    assert workspace.resolve_asset("library:icons/rocket.svg") == \
        workspace.library_dir / "icons" / "rocket.svg"
    assert workspace.resolve_asset("category:assets/logo.png", c.id) == \
        workspace.category_dir(c.id) / "assets" / "logo.png"


@pytest.mark.parametrize("ref", [
    "library:../secret.txt",
    "library:icons/../../x",
    "library:C:/Windows/x",
    "library:/etc/passwd",
    "library:",
    "http://example.com/x.png",
])
def test_resolve_asset_rejects_bad_refs(workspace, ref):
    with pytest.raises(StorageError):
        workspace.resolve_asset(ref)
