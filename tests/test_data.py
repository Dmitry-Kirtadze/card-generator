"""Етап 6: схема полів, дані, перевірка, фото, імпорт/експорт Excel і CSV."""
import io
import re
import shutil
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as XlImage
from PIL import Image

from cardgen.data.dataset import DataSet, images_dir, load_dataset, save_dataset
from cardgen.data.fields import KEY_COLUMN, build_schema
from cardgen.data.photos import PhotoError, cleanup_unused, fetch_photo, safe_name, store_image
from cardgen.data.table_io import TableImportError, cell_text, export_xlsx, import_table
from cardgen.data.validate import has_errors, validate
from cardgen.data.xlsx_images import embedded_images
from cardgen.model import FieldBinding, PhotoElement, TableElement, Template, TextElement


def png_bytes(color=(200, 30, 30), size=(40, 30), fmt="PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, fmt)
    return buffer.getvalue()


@pytest.fixture
def template():
    table = TableElement.create(2, 2, name="Характеристики")
    table.cells[0][1].binding = FieldBinding(enabled=True, column="Переріз", suffix=" AWG", required=True)
    table.cells[1][1].binding = FieldBinding(enabled=True, column="Колір", field_type="list",
                                             options=["червоний", "чорний"])
    return Template(elements=[
        TextElement(name="Заголовок", binding=FieldBinding(enabled=True, column="Назва", required=True)),
        TextElement(name="Довжина", binding=FieldBinding(enabled=True, column="Довжина, м",
                                                         field_type="number")),
        TextElement(name="Статичний"),
        PhotoElement(name="Фото товару"),
        table,
        TextElement(name="Повтор назви", binding=FieldBinding(enabled=True, column="  назва ")),
    ])


@pytest.fixture
def schema(template):
    return build_schema(template)


# --- Схема ----------------------------------------------------------------------

def test_schema_columns_in_order(schema):
    assert schema.columns == [KEY_COLUMN, "Назва", "Довжина, м", "Фото", "Переріз", "Колір"]
    assert schema.get("назва").used_in == ["Заголовок", "Повтор назви"]  # один стовпець — два блоки
    assert schema.get("Фото").is_image
    assert schema.get("Колір").options == ["червоний", "чорний"]
    assert schema.get(KEY_COLUMN).required and schema.get("Переріз").required
    assert schema.conflicts == []


def test_schema_type_conflict(template):
    template.elements.append(TextElement(binding=FieldBinding(enabled=True, column="Фото")))
    assert "Фото" in build_schema(template).conflicts[0]


def test_disabled_and_empty_bindings_ignored():
    t = Template(elements=[TextElement(binding=FieldBinding(enabled=False, column="Назва")),
                           TextElement(binding=FieldBinding(enabled=True, column="  "))])
    assert build_schema(t).columns == [KEY_COLUMN]


# --- Дані -------------------------------------------------------------------------

def test_dataset_roundtrip(tmp_path):
    ds = DataSet(columns=[KEY_COLUMN, "Назва"], rows=[{KEY_COLUMN: "A-1", "Назва": "Кабель"}], source="x.xlsx")
    save_dataset(tmp_path, ds)
    loaded = load_dataset(tmp_path)
    assert loaded.rows == ds.rows and loaded.source == "x.xlsx" and loaded.updated_at
    assert loaded.find("A-1")["Назва"] == "Кабель"
    assert loaded.value(loaded.rows[0], " назва") == "Кабель"
    assert load_dataset(tmp_path / "немає").rows == []


# --- Перевірка ---------------------------------------------------------------------

def test_validation_catches_problems(schema, tmp_path):
    images = images_dir(tmp_path)
    (images / "ok.png").write_bytes(png_bytes())
    ds = DataSet(columns=schema.columns, rows=[
        {KEY_COLUMN: "A1", "Назва": "Кабель", "Довжина, м": "1,5", "Фото": "ok.png", "Переріз": "18", "Колір": "чорний"},
        {KEY_COLUMN: "A1", "Назва": "", "Довжина, м": "півтора", "Фото": "нема.png", "Переріз": "18", "Колір": "синій"},
        {KEY_COLUMN: "", "Назва": "Кабель", "Переріз": ""},
    ])
    issues = validate(ds, schema, images)
    found = {(i.row, i.column, i.level) for i in issues}
    assert (0, KEY_COLUMN, "error") in found and (1, KEY_COLUMN, "error") in found  # дубль
    assert (1, "Назва", "error") in found  # обов'язкове порожнє
    assert (1, "Довжина, м", "error") in found  # не число
    assert (1, "Фото", "error") in found  # нема файлу
    assert (1, "Колір", "warning") in found  # не зі списку
    assert (2, KEY_COLUMN, "error") in found and (2, "Переріз", "error") in found
    assert not any(i.row == 0 and i.column != KEY_COLUMN for i in issues)  # перший рядок у нормі
    assert has_errors(issues)


# --- Фото ---------------------------------------------------------------------------

def test_store_image_names(tmp_path):
    assert store_image(png_bytes(), tmp_path, "AWG/18", "Фото") == "AWG_18_Фото.png"
    assert store_image(png_bytes(fmt="JPEG"), tmp_path, "AWG/18", "Фото") == "AWG_18_Фото.jpg"
    # інше фото з тим самим ім'ям не перезаписує наявне (воно може належати іншим товарам)
    assert store_image(png_bytes((1, 2, 3)), tmp_path, "AWG/18", "Фото") == "AWG_18_Фото (2).png"
    with pytest.raises(PhotoError):
        store_image(b"not an image", tmp_path, "A", "Фото")
    assert safe_name('a<b>:c"?*') == "a_b_c_"


def test_same_photo_stored_once(tmp_path):
    data = png_bytes((5, 5, 5))
    names = {store_image(data, tmp_path, f"A{i}", "Фото") for i in range(5)}
    assert names == {"A0_Фото.png"}
    assert len(list(tmp_path.iterdir())) == 1
    assert store_image(png_bytes((6, 6, 6)), tmp_path, "A9", "Фото") == "A9_Фото.png"


def test_cleanup_unused(tmp_path):
    for name in ("a.png", "b.png", "c.png"):
        (tmp_path / name).write_bytes(b"x")
    assert cleanup_unused(tmp_path, {"b.png"}) == 2
    assert [p.name for p in tmp_path.iterdir()] == ["b.png"]


def test_fetch_photo_by_name_path_and_url(tmp_path):
    folder = tmp_path / "фото"
    folder.mkdir()
    (folder / "Cable-18.PNG").write_bytes(b"data1")
    assert fetch_photo("cable-18.png", [folder]) == b"data1"  # без урахування регістру
    assert fetch_photo(str(folder / "Cable-18.PNG"), []) == b"data1"
    assert fetch_photo("https://x.test/a.png", [], downloader=lambda url: b"from " + url.encode()) \
        == b"from https://x.test/a.png"
    with pytest.raises(PhotoError):
        fetch_photo("нема.png", [folder])


# --- Експорт / імпорт -------------------------------------------------------------------

def test_export_template_xlsx(schema, tmp_path):
    path = export_xlsx(schema, DataSet(), tmp_path / "шаблон.xlsx")
    wb = load_workbook(path)
    ws = wb["Товари"]
    assert [c.value for c in ws[1]] == schema.columns
    assert "Обов'язкове" in ws["A1"].comment.text
    lists = ws.data_validations.dataValidation
    assert any('"червоний,чорний"' in v.formula1 for v in lists)
    assert "Як заповнювати" in wb.sheetnames


def test_export_import_roundtrip_with_data(schema, tmp_path):
    images = images_dir(tmp_path / "tpl")
    (images / "A1_Фото.png").write_bytes(png_bytes())
    ds = DataSet(columns=schema.columns + ["Примітка"], rows=[
        {KEY_COLUMN: "A1", "Назва": "Кабель 18", "Довжина, м": "1,5", "Фото": "A1_Фото.png",
         "Переріз": "18", "Колір": "червоний", "Примітка": "склад 2"},
    ])
    path = export_xlsx(schema, ds, tmp_path / "дані.xlsx")
    result = import_table(path, schema, images)
    assert result.dataset.rows == ds.rows  # фото знайдено в папці images шаблону
    assert any("Примітка" in w for w in result.warnings)


def write_rows(path, rows):
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    wb.save(path)
    return wb, ws


def test_import_values_and_columns_matching(schema, tmp_path):
    path = tmp_path / "кабелі.xlsx"
    write_rows(path, [
        [],  # порожній рядок перед заголовком
        ["артикул ", "НАЗВА", "Довжина, м", "Переріз"],
        ["A1", "Кабель", 1.5, 18],
        [None, None, None, None],  # порожній рядок пропускається
        ["A2", "Кабель 2", 2.0, 20],
    ])
    result = import_table(path, schema, images_dir(tmp_path / "tpl"))
    rows = result.dataset.rows
    assert [(r[KEY_COLUMN], r["Назва"], r["Довжина, м"], r["Переріз"]) for r in rows] == \
        [("A1", "Кабель", "1,5", "18"), ("A2", "Кабель 2", "2", "20")]
    assert any("Колір" in w for w in result.warnings)  # відсутній стовпець


def test_import_requires_key_column(schema, tmp_path):
    path = tmp_path / "x.xlsx"
    write_rows(path, [["Назва"], ["Кабель"]])
    with pytest.raises(TableImportError, match=KEY_COLUMN):
        import_table(path, schema, images_dir(tmp_path / "tpl"))


def test_import_photos_by_filename_and_url(schema, tmp_path):
    photos = tmp_path / "фото"
    photos.mkdir()
    (photos / "a1.jpg").write_bytes(png_bytes(fmt="JPEG"))
    path = tmp_path / "кабелі.xlsx"
    write_rows(path, [
        [KEY_COLUMN, "Фото"],
        ["A1", "a1.jpg"],
        ["A2", "https://shop.test/a2.png"],
        ["A3", "нема.jpg"],
    ])
    images = images_dir(tmp_path / "tpl")
    result = import_table(path, schema, images, photos_folder=photos, downloader=lambda url: png_bytes())
    rows = result.dataset.rows
    assert rows[0]["Фото"] == "A1_Фото.jpg" and (images / "A1_Фото.jpg").is_file()
    assert rows[1]["Фото"] == "A2_Фото.png"
    assert rows[2]["Фото"] == "нема.jpg"  # лишилось як є — перевірка покаже помилку
    assert result.photos == 2
    assert any("нема.jpg" in w for w in result.warnings)


def test_import_floating_image(schema, tmp_path):
    src = tmp_path / "pic.png"
    src.write_bytes(png_bytes((10, 200, 10)))
    path = tmp_path / "з картинками.xlsx"
    wb, ws = write_rows(path, [[KEY_COLUMN, "Назва", "Фото"], ["A1", "Кабель", None]])
    image = XlImage(str(src))
    ws.add_image(image, "C2")
    wb.save(path)
    assert set(embedded_images(path)) == {(2, 3)}
    images = images_dir(tmp_path / "tpl")
    result = import_table(path, schema, images)
    assert result.dataset.rows[0]["Фото"] == "A1_Фото.png"
    assert Image.open(images / "A1_Фото.png").getpixel((0, 0)) == (10, 200, 10)


def add_in_cell_image(path: Path, cell: str, data: bytes) -> None:
    """Перетворює звичайний xlsx на такий, як зберігає Excel 365 з «Розмістити в клітинці»:
    клітинка з vm="1" + xl/metadata.xml + xl/richData/* + xl/media/."""
    with zipfile.ZipFile(path) as zf:
        parts = {name: zf.read(name) for name in zf.namelist()}
    sheet = parts["xl/worksheets/sheet1.xml"].decode()
    replacement = f'<c r="{cell}" t="e" vm="1"><v>#VALUE!</v></c>'
    sheet, count = re.subn(rf'<c r="{cell}"[^>]*?(?:/>|>.*?</c>)', replacement, sheet)
    if count != 1:
        raise AssertionError("клітинку не знайдено в XML")
    parts["xl/worksheets/sheet1.xml"] = sheet.encode()
    parts["xl/media/image_in_cell.png"] = data
    parts["xl/metadata.xml"] = b"""<?xml version="1.0" encoding="UTF-8"?>
<metadata xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:xlrd="http://schemas.microsoft.com/office/spreadsheetml/2017/richdata">
 <metadataTypes count="1"><metadataType name="XLRICHVALUE" minSupportedVersion="120000"/></metadataTypes>
 <futureMetadata name="XLRICHVALUE" count="1"><bk><extLst><ext uri="{3e2802c4-a4d2-4d8b-9148-e3be6c30e623}">
 <xlrd:rvb i="0"/></ext></extLst></bk></futureMetadata>
 <valueMetadata count="1"><bk><rc t="1" v="0"/></bk></valueMetadata></metadata>"""
    parts["xl/richData/rdrichvaluestructure.xml"] = b"""<?xml version="1.0" encoding="UTF-8"?>
<rvStructures xmlns="http://schemas.microsoft.com/office/spreadsheetml/2017/richdata" count="1">
 <s t="_localImage"><k n="_rvRel:LocalImageIdentifier" t="i"/><k n="CalcOrigin" t="i"/></s></rvStructures>"""
    parts["xl/richData/rdrichvalue.xml"] = b"""<?xml version="1.0" encoding="UTF-8"?>
<rvData xmlns="http://schemas.microsoft.com/office/spreadsheetml/2017/richdata" count="1">
 <rv s="0"><v>0</v><v>5</v></rv></rvData>"""
    parts["xl/richData/richValueRel.xml"] = b"""<?xml version="1.0" encoding="UTF-8"?>
<richValueRels xmlns="http://schemas.microsoft.com/office/spreadsheetml/2022/richvaluerel"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><rel r:id="rId1"/></richValueRels>"""
    parts["xl/richData/_rels/richValueRel.xml.rels"] = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
 Target="../media/image_in_cell.png"/></Relationships>"""
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in parts.items():
            zf.writestr(name, content)


def test_import_in_cell_image_excel365(schema, tmp_path):
    path = tmp_path / "excel365.xlsx"
    wb, ws = write_rows(path, [[KEY_COLUMN, "Фото"], ["A1", None]])
    ws["B2"] = ""  # клітинка має існувати в XML
    wb.save(path)
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("xl/worksheets/sheet1.xml").decode()
    if 'r="B2"' not in xml:  # openpyxl може не записати порожню клітинку — додаємо вручну
        pytest.skip("openpyxl не записав порожню клітинку")
    add_in_cell_image(path, "B2", png_bytes((0, 0, 255)))
    assert set(embedded_images(path)) == {(2, 2)}
    images = images_dir(tmp_path / "tpl")
    result = import_table(path, schema, images)
    assert result.dataset.rows[0]["Фото"] == "A1_Фото.png"
    assert Image.open(images / "A1_Фото.png").getpixel((1, 1)) == (0, 0, 255)


def test_import_csv_semicolon_cp1251(schema, tmp_path):
    path = tmp_path / "дані.csv"
    path.write_bytes(f"{KEY_COLUMN};Назва;Переріз\nA1;Кабель силіконовий;18\n".encode("cp1251"))
    result = import_table(path, schema, images_dir(tmp_path / "tpl"))
    assert result.dataset.rows[0]["Назва"] == "Кабель силіконовий"


def test_cell_text():
    import datetime as dt
    assert [cell_text(v) for v in (None, 3.0, 0.82, True, dt.date(2026, 1, 5), " x ")] == \
        ["", "3", "0,82", "так", "05.01.2026", "x"]
