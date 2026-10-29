import json

import pytest

from cardgen.model import ELEMENT_TYPES, GroupElement, PhotoElement, Template, TextElement
from cardgen.model import serialization as ser
from cardgen.model.serialization import SchemaError


def roundtrip(template: Template) -> Template:
    # через справжній JSON-текст, як на диску
    text = json.dumps(ser.template_to_dict(template), ensure_ascii=False)
    return ser.template_from_dict(json.loads(text))


def test_full_template_roundtrip_is_lossless(full_template):
    assert roundtrip(full_template) == full_template


def test_roundtrip_keeps_concrete_element_types(full_template):
    restored = roundtrip(full_template)
    assert [type(e) for e in restored.elements] == [type(e) for e in full_template.elements]
    group = restored.elements[1]
    assert isinstance(group, GroupElement)
    assert [type(c) for c in group.children] == [type(c) for c in full_template.elements[1].children]


def test_every_element_type_roundtrips():
    for cls in ELEMENT_TYPES.values():
        template = Template(elements=[cls()])
        assert roundtrip(template) == template, cls.__name__


def test_ukrainian_text_preserved(full_template):
    data = ser.template_to_dict(full_template)
    text = json.dumps(data, ensure_ascii=False)
    assert "Кабель силіконовий" in text


def test_missing_fields_get_defaults():
    template = ser.template_from_dict({
        "name": "Мінімальний",
        "elements": [{"type": "text", "text": "Привіт"}],
    })
    element = template.elements[0]
    assert isinstance(element, TextElement)
    assert element.text == "Привіт"
    assert element.style.font_size == TextElement().style.font_size
    assert template.width == 1000


def test_unknown_fields_ignored():
    template = ser.template_from_dict({
        "name": "З майбутнього",
        "something_new": 42,
        "elements": [{"type": "photo", "future_option": True}],
    })
    assert isinstance(template.elements[0], PhotoElement)


def test_int_coerced_to_float():
    template = ser.template_from_dict({"elements": [{"type": "text", "x": 10}]})
    assert isinstance(template.elements[0].x, float)


def test_unknown_element_type_raises():
    with pytest.raises(SchemaError, match="Невідомий тип блоку"):
        ser.template_from_dict({"elements": [{"type": "hologram"}]})


def test_photo_is_bound_to_table_by_default():
    photo = PhotoElement()
    assert photo.binding.enabled and photo.binding.field_type == "image"


def test_element_ids_unique():
    ids = {TextElement().id for _ in range(1000)}
    assert len(ids) == 1000


# --- Версії формату ------------------------------------------------------

def test_missing_version_treated_as_first():
    assert ser.template_from_dict({"name": "Старий"}).name == "Старий"


def test_newer_version_rejected():
    with pytest.raises(SchemaError, match="новішою версією"):
        ser.template_from_dict({"schema_version": ser.SCHEMA_VERSION + 1})


def test_migrations_applied_in_order(monkeypatch):
    def v1_to_v2(data):
        data["name"] = data.pop("title")  # уявна зміна: поле перейменовано
        return data

    def v2_to_v3(data):
        data["width"] = data["width"] * 2
        return data

    monkeypatch.setattr(ser, "SCHEMA_VERSION", 3)
    monkeypatch.setattr(ser, "MIGRATIONS", {1: v1_to_v2, 2: v2_to_v3})
    template = ser.template_from_dict({"schema_version": 1, "title": "Старий", "width": 500})
    assert template.name == "Старий"
    assert template.width == 1000


def test_missing_migration_reported(monkeypatch):
    monkeypatch.setattr(ser, "SCHEMA_VERSION", 2)
    monkeypatch.setattr(ser, "MIGRATIONS", {})
    with pytest.raises(SchemaError, match="Немає міграції"):
        ser.template_from_dict({"schema_version": 1})
