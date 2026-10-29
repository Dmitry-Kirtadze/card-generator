"""Етап 8: експорт у JPEG — імена за маскою, обмеження майданчиків, відповідність перегляду."""
import io

import pytest
from PIL import Image
from PySide6.QtGui import QColor, QImage

from cardgen.data.dataset import DataSet, images_dir, save_dataset
from cardgen.data.fields import KEY_COLUMN
from cardgen.export import PRESETS, encode_jpeg, export_cards, export_scale, file_stem, unique_path
from cardgen.generate import save_overrides
from cardgen.model import FieldBinding, PhotoElement, ShapeElement, Paint, Template, TextElement, TextStyle
from cardgen.model import serialization as ser
from cardgen.products import Products
from cardgen.ui.export_dialog import ExportDialog
from imaging import difference
from test_app import FakeDialogs

pytestmark = pytest.mark.usefixtures("qapp")


def make_template(name: str, number: int, size: int = 1000) -> Template:
    t = Template(name=name, width=size, height=size, elements=[
        ShapeElement(id="band", x=0, y=0, width=size, height=size * 0.15, fill=Paint(color="#1E5BFF")),
        TextElement(id="title", x=size * 0.05, y=size * 0.2, width=size * 0.9, height=size * 0.15,
                    style=TextStyle(font_family="Arial", font_size=size * 0.06, bold=True),
                    binding=FieldBinding(enabled=True, column="Назва", required=True)),
        PhotoElement(id="photo", x=size * 0.25, y=size * 0.4, width=size * 0.5, height=size * 0.5),
    ])
    t.export.number = number
    return t


@pytest.fixture
def category(workspace):
    c = workspace.create_category("Кабель AWG")
    cover = make_template("Обкладинка", 1)
    specs = make_template("Характеристики", 2, size=1500)
    for t in (cover, specs):
        workspace.save_template(c.id, t)
        tables = workspace.tables_dir(c.id, t.id)
        rows = []
        for i in range(10):
            Image.new("RGB", (60, 60), (25 * i, 80, 160)).save(images_dir(tables) / f"p{i}.png")
            rows.append({KEY_COLUMN: f"AWG-{10 + 2 * i}", "Назва": f"Кабель {10 + 2 * i} AWG",
                         "Фото": f"p{i}.png"})
        save_dataset(tables, DataSet(columns=list(rows[0]), rows=rows))
    return c, cover, specs


# --- Імена файлів --------------------------------------------------------------------

def test_file_stem_mask(workspace, category):
    c, cover, _ = category
    products = Products(workspace, c.id, cover.id)
    assert file_stem("{Артикул}_{№}", products, 0) == "AWG-10_1"
    assert file_stem("{назва} – {шаблон}", products, 1) == "Кабель 12 AWG – Обкладинка"
    assert file_stem("{n}-{Нема такого}", products, 2) == "3"  # «висячий» дефіс прибрано
    products.dataset.rows[0][KEY_COLUMN] = 'A/B:"C"?'
    assert file_stem("{Артикул}", products, 0) == "A_B_C_"
    products.dataset.rows[0][KEY_COLUMN] = ""
    assert file_stem("{Артикул}", products, 0) == "картка-1"


def test_unique_path(tmp_path):
    taken = set()
    assert unique_path(tmp_path, "AWG-10_1", taken).name == "AWG-10_1.jpg"
    assert unique_path(tmp_path, "awg-10_1", taken).name == "awg-10_1 (2).jpg"


def test_old_templates_get_new_mask():
    t = ser.template_from_dict({"schema_version": 1, "export": {"filename_mask": "{Артикул}"}})
    assert t.export.filename_mask == "{Артикул}_{№}"
    t = ser.template_from_dict({"schema_version": 1, "export": {"filename_mask": "{Назва}"}})
    assert t.export.filename_mask == "{Назва}"


# --- JPEG ------------------------------------------------------------------------------

def test_encode_jpeg_and_size_limit():
    image = QImage(800, 800, QImage.Format.Format_ARGB32)
    for y in range(0, 800, 4):  # шум, щоб JPEG був великим
        for x in range(0, 800, 4):
            image.setPixelColor(x, y, QColor((x * 7) % 255, (y * 13) % 255, (x * y) % 255))
    data, quality = encode_jpeg(image, 95, max_bytes=10 * 1024 * 1024)
    assert quality == 95
    pil = Image.open(io.BytesIO(data))
    assert pil.format == "JPEG" and pil.mode == "RGB" and pil.size == (800, 800)
    small, low = encode_jpeg(image, 95, max_bytes=len(data) // 2)
    assert low < 95 and len(small) < len(data)


def test_transparent_becomes_white():
    image = QImage(10, 10, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    data, _ = encode_jpeg(image, 92, 10 * 1024 * 1024)
    assert Image.open(io.BytesIO(data)).getpixel((5, 5)) == (255, 255, 255)


def test_export_scale():
    preset = PRESETS["prom_rozetka"]
    assert export_scale(Template(width=1000, height=1000), preset) == 1.0
    assert export_scale(Template(width=1500, height=1000), preset) == pytest.approx(1280 / 1500)


# --- Експорт --------------------------------------------------------------------------------

def test_export_all_cards(workspace, category, tmp_path):
    c, cover, specs = category
    progress = []
    report = export_cards(workspace, c.id, [cover.id, specs.id], tmp_path / "out",
                          progress=lambda done, name: progress.append((done, name)) or True)
    names = sorted(p.name for p in report.files)
    assert len(names) == 20
    assert names[:3] == ["AWG-10_1.jpg", "AWG-10_2.jpg", "AWG-12_1.jpg"]
    assert progress[-1] == (20, "")
    for path in report.files:
        with Image.open(path) as img:
            assert img.format == "JPEG" and img.mode == "RGB"
            side = max(img.size)
            assert PRESETS["prom_rozetka"].min_side <= side <= PRESETS["prom_rozetka"].max_side
        assert path.stat().st_size <= PRESETS["prom_rozetka"].max_bytes
    with Image.open(tmp_path / "out" / "AWG-10_2.jpg") as img:
        assert img.size == (1280, 1280)  # 1500 px зменшено під Пром
    assert report.warnings == [] and report.skipped == []


def test_exported_matches_preview(workspace, category, tmp_path):
    c, cover, _ = category
    products = Products(workspace, c.id, cover.id)
    save_overrides(products.tables, {"AWG-12": {"title": {"style.color": "#FF0000"}}})
    report = export_cards(workspace, c.id, [cover.id], tmp_path)
    products.reload()
    for index in (0, 1):
        preview = products.render(index).image
        exported = QImage(str(tmp_path / f"{products.article(index)}_1.jpg"))
        mean, strong = difference(preview, exported)
        assert mean < 2.0 and strong < 0.01, (index, mean, strong)  # лише втрати JPEG
    assert len(report.files) == 10


def test_errors_exported_with_warning_or_skipped(workspace, category, tmp_path):
    c, cover, _ = category
    tables = workspace.tables_dir(c.id, cover.id)
    products = Products(workspace, c.id, cover.id)
    products.dataset.rows[3]["Назва"] = ""
    save_dataset(tables, products.dataset)
    report = export_cards(workspace, c.id, [cover.id], tmp_path / "a")
    assert len(report.files) == 10
    assert any("AWG-16_1.jpg: помилки" in w for w in report.warnings)
    report = export_cards(workspace, c.id, [cover.id], tmp_path / "b", skip_errors=True)
    assert len(report.files) == 9
    assert report.skipped and "AWG-16" in report.skipped[0]


def test_same_numbers_do_not_overwrite(workspace, category, tmp_path):
    c, cover, specs = category
    specs.export.number = 1
    workspace.save_template(c.id, specs)
    report = export_cards(workspace, c.id, [cover.id, specs.id], tmp_path)
    assert len({p.name for p in report.files}) == 20
    assert (tmp_path / "AWG-10_1 (2).jpg").is_file()
    assert any("однаковий номер" in w for w in report.warnings)


def test_small_template_warning_and_cancel(workspace, category, tmp_path):
    c, cover, _ = category
    cover.width = cover.height = 300
    workspace.save_template(c.id, cover)
    report = export_cards(workspace, c.id, [cover.id], tmp_path, progress=lambda done, name: done < 3)
    assert report.cancelled and len(report.files) == 3
    assert any("менше за мінімум" in w for w in report.warnings)


# --- Діалог ----------------------------------------------------------------------------------

def test_export_dialog(qtbot, monkeypatch, workspace, category, tmp_path):
    c, cover, specs = category
    fake = FakeDialogs(monkeypatch)
    fake.confirm_answer = False  # не відкривати папку
    dialog = ExportDialog(workspace, c.id, [cover.id])
    qtbot.addWidget(dialog)
    assert dialog.chosen() == [cover.id]
    assert dialog.total.text() == "Усього карток: 10"
    fake.dir_path = tmp_path / "картки"
    report = dialog.run_export()  # папки ще немає — діалог спитає
    assert len(report.files) == 10
    assert "Збережено карток: 10" in fake.infos[-1]
    assert workspace.editor_settings()["export_folder"] == str(tmp_path / "картки")
    again = ExportDialog(workspace, c.id)
    qtbot.addWidget(again)
    assert again.folder.text() == str(tmp_path / "картки")  # папку запам'ятовано
    assert set(again.chosen()) == {cover.id, specs.id}
