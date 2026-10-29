"""Маркет: вбудована категорія готових шаблонів, копіювання шаблонів між категоріями."""
from pathlib import Path

import pytest
from PIL import Image

from cardgen.data.dataset import DataSet, images_dir, load_dataset, save_dataset
from cardgen.data.fields import KEY_COLUMN
from cardgen.market import MARKET_ID, copy_template, ensure_market, seed_market
from cardgen.model import FieldBinding, PhotoElement, TextElement
from cardgen.storage import StorageError
from cardgen.transfer import export_category
from cardgen.ui.main_window import MainWindow
from test_app import FakeDialogs

REAL_PACKAGE = Path(__file__).resolve().parent.parent / "market" / "Кабель силіконовий.cardgen.zip"


@pytest.fixture
def source(workspace, tmp_path):
    """Категорія з шаблоном: фото-зразок у ресурсах категорії, дані з одним товаром."""
    c = workspace.create_category("Кабель")
    t = workspace.create_template(c.id, "Обкладинка")
    sample = tmp_path / "зразок.png"
    Image.new("RGB", (30, 30), (200, 0, 0)).save(sample)
    t.elements = [TextElement(binding=FieldBinding(enabled=True, column="Назва")),
                  PhotoElement(placeholder=workspace.add_category_asset(c.id, sample))]
    workspace.save_template(c.id, t)
    tables = workspace.tables_dir(c.id, t.id)
    Image.new("RGB", (20, 20), (0, 0, 200)).save(images_dir(tables) / "A1_Фото.png")
    save_dataset(tables, DataSet(columns=[KEY_COLUMN, "Назва", "Фото"],
                                 rows=[{KEY_COLUMN: "A1", "Назва": "Кабель", "Фото": "A1_Фото.png"}]))
    (tables / "історія.xlsx").write_bytes(b"PK")
    return c, t


# --- Маркет ----------------------------------------------------------------------

def test_market_is_protected_and_first(workspace):
    workspace.create_category("Кабель")
    market = ensure_market(workspace)
    assert market.protected and market.name == "Маркет"
    assert workspace.list_categories()[0].id == MARKET_ID
    with pytest.raises(StorageError, match="не можна видалити"):
        workspace.delete_category(MARKET_ID)
    with pytest.raises(StorageError, match="не можна перейменувати"):
        workspace.rename_category(MARKET_ID, "Інше")
    assert ensure_market(workspace) == market  # повторний виклик нічого не ламає


def test_duplicate_of_market_is_normal_category(workspace):
    ensure_market(workspace)
    copy = workspace.duplicate_category(MARKET_ID)
    assert not copy.protected
    workspace.delete_category(copy.id)


def test_seed_market_once(workspace, source, tmp_path):
    c, _ = source
    packages = tmp_path / "market"
    export_category(workspace, c.id, packages / "Кабель.cardgen.zip")
    assert seed_market(workspace, packages) == ["Обкладинка"]
    templates = workspace.list_templates(MARKET_ID)
    assert [t.name for t in templates] == ["Обкладинка"]
    assert len(workspace.list_categories()) == 2  # тимчасова категорія імпорту прибрана
    assert seed_market(workspace, packages) == []  # другий запуск — без повторів
    workspace.delete_template(MARKET_ID, templates[0].id)
    assert seed_market(workspace, packages) == []  # видалений шаблон сам не повертається


def test_seed_skips_broken_package(workspace, tmp_path):
    packages = tmp_path / "market"
    packages.mkdir()
    (packages / "зламаний.cardgen.zip").write_bytes(b"not a zip")
    assert seed_market(workspace, packages) == []
    assert workspace.list_templates(MARKET_ID) == []


@pytest.mark.skipif(not REAL_PACKAGE.is_file(), reason="немає пакетів Маркету")
def test_real_market_packages(workspace):
    """Усі шаблони, що постачаються з програмою: завантажуються, без помилок у прикладі даних,
    текст вміщується."""
    from cardgen.products import Products

    added = seed_market(workspace, REAL_PACKAGE.parent)
    packages = list(REAL_PACKAGE.parent.glob("*.cardgen.zip"))
    assert len(added) == len(packages) >= 11
    assert "Обкладинка" in added and "Акція — знижка" in added
    for template in workspace.list_templates(MARKET_ID):
        products = Products(workspace, MARKET_ID, template.id)
        assert len(products) == 1, template.name
        assert [i.message for i in products.issues] == [], template.name
        assert products.render(0, 0.3).overflow == set(), template.name


# --- Копіювання шаблону -------------------------------------------------------------

def test_copy_template_with_assets_and_data(workspace, source):
    c, t = source
    target = workspace.create_category("Провід")
    workspace.create_template(target.id, "Обкладинка")  # назва вже зайнята
    copy = copy_template(workspace, c.id, t.id, target.id)
    assert copy.id != t.id
    assert copy.name == "Обкладинка (копія)"
    assert copy.export.number == 2
    photo = copy.elements[1]
    assert workspace.resolve_asset(photo.placeholder, target.id).is_file()  # ресурс скопійовано
    tables = workspace.tables_dir(target.id, copy.id)
    assert load_dataset(tables).rows[0]["Назва"] == "Кабель"
    assert (tables / "images" / "A1_Фото.png").is_file()
    assert not (tables / "історія.xlsx").exists()  # історію таблиць не копіюємо
    # оригінал не змінився
    assert workspace.load_template(c.id, t.id).name == "Обкладинка"


def test_copy_without_data(workspace, source):
    c, t = source
    target = workspace.create_category("Провід")
    copy = copy_template(workspace, c.id, t.id, target.id, with_data=False)
    assert load_dataset(workspace.tables_dir(target.id, copy.id)).rows == []


# --- Інтерфейс ------------------------------------------------------------------------

@pytest.fixture
def window(qtbot, workspace):
    ensure_market(workspace)
    w = MainWindow(workspace)
    qtbot.addWidget(w)
    w.show()
    return w


def test_market_cannot_be_deleted_in_ui(window, monkeypatch, workspace):
    fake = FakeDialogs(monkeypatch)
    page = window.categories_page
    page.refresh()
    page.grid.setCurrentRow(0)
    assert page.grid.item(0).text().startswith("Маркет · готові")
    assert not page.actions.buttons["delete"].isEnabled()
    assert not page.actions.buttons["rename"].isEnabled()
    page.delete_selected()  # навіть якщо викликати напряму
    assert fake.errors and "не можна видалити" in fake.errors[-1]
    assert workspace.get_category(MARKET_ID).protected


def test_copy_from_market_to_category_ui(window, monkeypatch, workspace, source):
    c, t = source
    copy_template(workspace, c.id, t.id, MARKET_ID)
    fake = FakeDialogs(monkeypatch)
    window.show_category(MARKET_ID)
    page = window.category_page
    assert page.market_hint.isVisibleTo(page) and not page.actions.buttons["to_market"].isVisibleTo(page)
    page.grid.setCurrentRow(0)

    fake.choices = ["Кабель"]
    page.copy_to_category()
    assert fake.offered[-1] == ["Кабель", "➕ Нова категорія…"]  # Маркету серед цілей немає
    assert [x.name for x in workspace.list_templates(c.id)] == ["Обкладинка", "Обкладинка (копія)"]

    fake.choices = ["➕ Нова категорія…"]
    fake.texts = ["Провід луджений"]
    page.copy_to_category()
    new = next(x for x in workspace.list_categories() if x.name == "Провід луджений")
    assert [x.name for x in workspace.list_templates(new.id)] == ["Обкладинка"]
    assert "скопійовано" in fake.infos[-1]


def test_add_to_market_ui(window, monkeypatch, workspace, source):
    c, t = source
    fake = FakeDialogs(monkeypatch)
    window.show_category(c.id)
    page = window.category_page
    assert not page.market_hint.isVisibleTo(page)
    page.grid.setCurrentRow(0)
    page.add_to_market()
    assert [x.name for x in workspace.list_templates(MARKET_ID)] == ["Обкладинка"]
    assert "Маркет" in fake.infos[-1]
