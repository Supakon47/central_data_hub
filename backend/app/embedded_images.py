"""Extract embedded XLSX images by their worksheet anchor without altering the workbook."""

import xml.etree.ElementTree as ElementTree
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from posixpath import dirname, join, normpath
from urllib.parse import quote

NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "package_rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "drawing": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "drawing_main": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "rich_value_rel": "http://schemas.microsoft.com/office/spreadsheetml/2022/richvaluerel",
    "rich_data": "http://schemas.microsoft.com/office/spreadsheetml/2017/richdata",
}
SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}


@dataclass
class EmbeddedImageResult:
    urls_by_sheet_row: dict[str, dict[int, str]] = field(default_factory=dict)
    duplicate_rows_by_sheet: dict[str, set[int]] = field(default_factory=dict)
    exported_count: int = 0
    ignored_count: int = 0


def _entry_xml(archive: zipfile.ZipFile, name: str) -> ElementTree.Element | None:
    try:
        return ElementTree.fromstring(archive.read(name))
    except KeyError:
        return None


def _relationships(archive: zipfile.ZipFile, rel_name: str) -> dict[str, str]:
    root = _entry_xml(archive, rel_name)
    if root is None:
        return {}
    return {
        item.attrib["Id"]: item.attrib["Target"]
        for item in root.findall("package_rel:Relationship", NS)
    }


def _resolve(source_name: str, target: str) -> str:
    return normpath(join(dirname(source_name), target)).lstrip("/")


def _relationship_name(part_name: str) -> str:
    return f"{dirname(part_name)}/_rels/{Path(part_name).name}.rels"


def _source_key(source_name: str) -> str:
    return sha256(source_name.encode("utf-8")).hexdigest()[:16]


def _cell_coordinates(reference: str) -> tuple[int, int] | None:
    """Return zero-based ``(column, row)`` from an A1 cell reference."""
    letters = "".join(character for character in reference if character.isalpha())
    digits = "".join(character for character in reference if character.isdigit())
    if not letters or not digits:
        return None
    column = 0
    for character in letters.upper():
        column = column * 26 + ord(character) - ord("A") + 1
    return column - 1, int(digits)


def _rich_value_media_parts(archive: zipfile.ZipFile) -> dict[int, str]:
    """Map an Excel Rich Data value index to its image package part.

    Newer Excel versions store *Image in Cell* values in ``xl/richData``. A
    worksheet cell references metadata, metadata references a rich value, and
    that rich value references the image relationship. The original importer
    only understood drawing anchors, so these images were invisible to it.
    """
    relations_root = _entry_xml(archive, "xl/richData/richValueRel.xml")
    values_root = _entry_xml(archive, "xl/richData/rdrichvalue.xml")
    if relations_root is None or values_root is None:
        return {}
    relationship_ids = [
        item.attrib.get(f"{{{NS['rel']}}}id")
        for item in relations_root.findall("rich_value_rel:rel", NS)
    ]
    package_relationships = _relationships(
        archive,
        "xl/richData/_rels/richValueRel.xml.rels",
    )
    media_parts: dict[int, str] = {}
    for value_index, rich_value in enumerate(values_root.findall("rich_data:rv", NS)):
        fields = rich_value.findall("rich_data:v", NS)
        if not fields:
            continue
        try:
            relationship_index = int(fields[0].text or "")
        except ValueError:
            continue
        if not 0 <= relationship_index < len(relationship_ids):
            continue
        relationship_id = relationship_ids[relationship_index]
        target = package_relationships.get(relationship_id or "")
        if target:
            media_parts[value_index] = _resolve("xl/richData/richValueRel.xml", target)
    return media_parts


def _metadata_rich_value_indexes(archive: zipfile.ZipFile) -> dict[int, int]:
    """Map the one-based worksheet ``vm`` value to a Rich Data value index."""
    metadata = _entry_xml(archive, "xl/metadata.xml")
    if metadata is None:
        return {}
    value_metadata = metadata.find("main:valueMetadata", NS)
    if value_metadata is None:
        return {}
    indexes: dict[int, int] = {}
    for metadata_index, block in enumerate(value_metadata.findall("main:bk", NS), start=1):
        reference = block.find("main:rc", NS)
        if reference is None:
            continue
        try:
            indexes[metadata_index] = int(reference.attrib.get("v", ""))
        except ValueError:
            continue
    return indexes


def extract_embedded_images(
    workbook_path: Path,
    source_name: str,
    photo_columns_by_sheet: dict[str, int],
    output_root: Path,
) -> EmbeddedImageResult:
    """Copy unambiguous images to local storage and return browser URLs.

    Only anchors in a worksheet's declared `รูปภาพ` column are eligible. If
    multiple pictures share a cell, that row is intentionally left unmapped.
    """
    result = EmbeddedImageResult(
        urls_by_sheet_row=defaultdict(dict),
        duplicate_rows_by_sheet=defaultdict(set),
    )
    with zipfile.ZipFile(workbook_path) as archive:
        workbook = _entry_xml(archive, "xl/workbook.xml")
        if workbook is None:
            return result
        workbook_rels = _relationships(archive, "xl/_rels/workbook.xml.rels")
        sheets: dict[str, str] = {}
        for sheet in workbook.findall("main:sheets/main:sheet", NS):
            relationship_id = sheet.attrib.get(f"{{{NS['rel']}}}id")
            if relationship_id and relationship_id in workbook_rels:
                sheets[sheet.attrib["name"]] = _resolve("xl/workbook.xml", workbook_rels[relationship_id])

        candidates: dict[tuple[str, int], list[str]] = defaultdict(list)
        rich_media_parts = _rich_value_media_parts(archive)
        rich_value_indexes = _metadata_rich_value_indexes(archive)
        for sheet_name, sheet_part in sheets.items():
            expected_column = photo_columns_by_sheet.get(sheet_name)
            if expected_column is None:
                continue
            worksheet = _entry_xml(archive, sheet_part)
            if worksheet is not None and rich_media_parts and rich_value_indexes:
                for cell in worksheet.findall(".//main:c", NS):
                    coordinates = _cell_coordinates(cell.attrib.get("r", ""))
                    metadata_value = cell.attrib.get("vm")
                    if coordinates is None or not metadata_value:
                        continue
                    column, row_number = coordinates
                    if column != expected_column:
                        continue
                    try:
                        rich_value_index = rich_value_indexes[int(metadata_value)]
                    except (KeyError, ValueError):
                        continue
                    media_part = rich_media_parts.get(rich_value_index)
                    if media_part and Path(media_part).suffix.lower() in SUPPORTED_SUFFIXES:
                        candidates[(sheet_name, row_number)].append(media_part)
            sheet_rels = _relationships(archive, _relationship_name(sheet_part))
            drawing_targets = [
                _resolve(sheet_part, target) for target in sheet_rels.values()
                if target.lower().endswith(".xml") and "drawing" in target.lower()
            ]
            for drawing_part in drawing_targets:
                drawing = _entry_xml(archive, drawing_part)
                if drawing is None:
                    continue
                drawing_rels = _relationships(archive, _relationship_name(drawing_part))
                anchors = drawing.findall("drawing:twoCellAnchor", NS) + drawing.findall("drawing:oneCellAnchor", NS)
                for anchor in anchors:
                    start = anchor.find("drawing:from", NS)
                    blip = anchor.find(".//drawing_main:blip", NS)
                    if start is None or blip is None:
                        continue
                    column = int(start.findtext("drawing:col", default="-1", namespaces=NS))
                    row_number = int(start.findtext("drawing:row", default="-1", namespaces=NS)) + 1
                    embed_id = blip.attrib.get(f"{{{NS['rel']}}}embed")
                    target = drawing_rels.get(embed_id or "")
                    if column != expected_column or not target:
                        result.ignored_count += 1
                        continue
                    media_part = _resolve(drawing_part, target)
                    if Path(media_part).suffix.lower() not in SUPPORTED_SUFFIXES:
                        result.ignored_count += 1
                        continue
                    candidates[(sheet_name, row_number)].append(media_part)

        source_key = _source_key(source_name)
        for (sheet_name, row_number), media_parts in candidates.items():
            if len(media_parts) != 1:
                result.duplicate_rows_by_sheet[sheet_name].add(row_number)
                continue
            media_part = media_parts[0]
            suffix = Path(media_part).suffix.lower().replace(".jpeg", ".jpg")
            sheet_key = sha256(sheet_name.encode("utf-8")).hexdigest()[:16]
            relative_path = Path(source_key) / sheet_key / f"row-{row_number}{suffix}"
            output_path = output_root / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(archive.read(media_part))
            result.urls_by_sheet_row[sheet_name][row_number] = "/media/" + quote(relative_path.as_posix())
            result.exported_count += 1

    return result
