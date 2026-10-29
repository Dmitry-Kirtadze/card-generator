"""Картинки, вставлені в Excel, з прив'язкою до клітинки.

Excel вміє вставляти картинку двома способами:
- «поверх клітинок» (класичний) — картинка прив'язана до клітинки свого лівого
  верхнього кута; їх читає openpyxl;
- «у клітинку» (Excel 365: Вставлення → Зображення → Розмістити в клітинці) —
  зберігається як «rich value» у xl/richData; openpyxl цього не розуміє,
  тому розбираємо XML самі.

Результат: {(рядок, стовпець): байти}, нумерація з 1, як в Excel.
"""
from __future__ import annotations

import logging
import posixpath
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from openpyxl import load_workbook

log = logging.getLogger(__name__)

Cell = tuple[int, int]


def embedded_images(path: Path, sheet_index: int = 0) -> dict[Cell, bytes]:
    result: dict[Cell, bytes] = {}
    try:
        result.update(_floating_images(path, sheet_index))
    except Exception as e:  # noqa: BLE001 — картинки необов'язкові, дані важливіші
        log.warning("Не вдалося прочитати картинки поверх клітинок: %s", e)
    try:
        result.update(_in_cell_images(path, sheet_index))
    except Exception as e:  # noqa: BLE001
        log.warning("Не вдалося прочитати картинки в клітинках: %s", e)
    return result


def _floating_images(path: Path, sheet_index: int) -> dict[Cell, bytes]:
    wb = load_workbook(path)
    ws = wb.worksheets[sheet_index]
    result = {}
    for image in getattr(ws, "_images", []):
        anchor = getattr(image.anchor, "_from", None)
        if anchor is None:
            continue
        result[(anchor.row + 1, anchor.col + 1)] = image._data()
    return result


# --- Картинки «у клітинці» (rich value) ------------------------------------

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _attr(element, name: str) -> str | None:
    for key, value in element.attrib.items():
        if _local(key) == name:
            return value
    return None


def _xml(zf: zipfile.ZipFile, name: str):
    try:
        return ElementTree.fromstring(zf.read(name))
    except KeyError:
        return None


def _rels(zf: zipfile.ZipFile, part: str) -> dict[str, str]:
    """rId -> повний шлях цілі для частини part."""
    folder, name = posixpath.split(part)
    root = _xml(zf, posixpath.join(folder, "_rels", name + ".rels"))
    if root is None:
        return {}
    result = {}
    for rel in root:
        target = rel.get("Target", "")
        full = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(folder, target))
        result[rel.get("Id")] = full
    return result


def _sheet_part(zf: zipfile.ZipFile, sheet_index: int) -> str | None:
    workbook = _xml(zf, "xl/workbook.xml")
    if workbook is None:
        return None
    sheets = [e for e in workbook.iter() if _local(e.tag) == "sheet"]
    if sheet_index >= len(sheets):
        return None
    rid = _attr(sheets[sheet_index], "id")
    return _rels(zf, "xl/workbook.xml").get(rid)


def _cell_ref(ref: str) -> Cell:
    match = re.fullmatch(r"([A-Z]+)(\d+)", ref)
    letters, row = match.groups()
    col = 0
    for ch in letters:
        col = col * 26 + ord(ch) - 64
    return int(row), col


def _in_cell_images(path: Path, sheet_index: int) -> dict[Cell, bytes]:
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        if "xl/richData/rdrichvalue.xml" not in names:
            return {}
        sheet = _sheet_part(zf, sheet_index)
        sheet_xml = _xml(zf, sheet) if sheet else None
        if sheet_xml is None:
            return {}
        cells_vm = {}
        for cell in sheet_xml.iter():
            if _local(cell.tag) == "c" and cell.get("vm"):
                cells_vm[_cell_ref(cell.get("r"))] = int(cell.get("vm"))
        if not cells_vm:
            return {}

        # vm (з 1) -> bk у valueMetadata -> rc v -> bk у futureMetadata XLRICHVALUE -> rvb i
        metadata = _xml(zf, "xl/metadata.xml")
        rich_index_of_vm: dict[int, int] = {}
        if metadata is not None:
            future = next((f for f in metadata if _local(f.tag) == "futureMetadata"
                           and f.get("name") == "XLRICHVALUE"), None)
            future_rv = []
            if future is not None:
                for bk in (b for b in future if _local(b.tag) == "bk"):
                    rvb = next((e for e in bk.iter() if _local(e.tag) == "rvb"), None)
                    future_rv.append(int(rvb.get("i")) if rvb is not None else -1)
            value_meta = next((v for v in metadata if _local(v.tag) == "valueMetadata"), None)
            if value_meta is not None:
                for n, bk in enumerate(b for b in value_meta if _local(b.tag) == "bk"):
                    rc = next((e for e in bk if _local(e.tag) == "rc"), None)
                    if rc is not None and int(rc.get("v")) < len(future_rv):
                        rich_index_of_vm[n + 1] = future_rv[int(rc.get("v"))]
        else:  # без metadata.xml — найпростіше припущення: vm-1 = номер rich value
            rich_index_of_vm = {vm: vm - 1 for vm in cells_vm.values()}

        # структури: індекс -> позиція ключа _rvRel:LocalImageIdentifier
        structures = _xml(zf, "xl/richData/rdrichvaluestructure.xml")
        image_key_pos: dict[int, int] = {}
        if structures is not None:
            for n, s in enumerate(e for e in structures if _local(e.tag) == "s"):
                keys = [k.get("n") for k in s if _local(k.tag) == "k"]
                if "_rvRel:LocalImageIdentifier" in keys:
                    image_key_pos[n] = keys.index("_rvRel:LocalImageIdentifier")

        values = _xml(zf, "xl/richData/rdrichvalue.xml")
        rel_index_of_rich: dict[int, int] = {}
        for n, rv in enumerate(e for e in values if _local(e.tag) == "rv"):
            pos = image_key_pos.get(int(rv.get("s", "0")), 0 if not image_key_pos else None)
            vs = [v.text for v in rv if _local(v.tag) == "v"]
            if pos is not None and pos < len(vs):
                rel_index_of_rich[n] = int(vs[pos])

        rel_part = "xl/richData/richValueRel.xml"
        rel_list = _xml(zf, rel_part)
        rids = [_attr(r, "id") for r in rel_list if _local(r.tag) == "rel"] if rel_list is not None else []
        targets = _rels(zf, rel_part)

        result = {}
        for cell, vm in cells_vm.items():
            rich = rich_index_of_vm.get(vm)
            rel = rel_index_of_rich.get(rich) if rich is not None else None
            if rel is None or rel >= len(rids):
                continue
            target = targets.get(rids[rel])
            if target and target in names:
                result[cell] = zf.read(target)
        return result
