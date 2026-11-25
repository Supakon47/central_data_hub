"""Import an Excel workbook as described by an import profile (JSON).

A profile states, for one source workbook, which sheets to import, where each
header row is, whether a sheet is an object register or a storage-location
list, and which sheets to skip and why. Profiles live in
``backend/import_profiles/``. The workbook itself is only ever read.

    python -m app.import_profile import_profiles/02-metal-1.json --dry-run
    python -m app.import_profile import_profiles --dry-run      # every profile
    python -m app.import_profile import_profiles                # import for real

A dry run reads and validates everything, then rolls back: nothing is saved
and no images are copied.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from sqlalchemy import select

from .config import IMAGE_STORAGE_DIR
from .database import SessionLocal
from .db_upgrade import upgrade_database
from .embedded_images import extract_embedded_images
from .import_workbook import TabularSheet, sync_tabular_sheets
from .models import DataQualityIssue, DataSource, SourceSheetConfig
from .normalization import normalise_header

ROLES = ("register", "location")
IMAGE_HEADERS = ("รูปภาพ", "รูป", "รูปถ่าย")
MAX_CONSECUTIVE_BLANK_ROWS = 1000
DEFAULT_RAWDATA_DIR = os.getenv("RAWDATA_DIR", "/rawdata")


class ProfileError(ValueError):
    """The profile does not match the workbook or is malformed."""


@dataclass(frozen=True)
class SheetRule:
    skip: str | None = None
    role: str | None = None
    header_row: int | None = None
    location: str | None = None


@dataclass(frozen=True)
class ImportProfile:
    path: Path
    source_name: str
    file: str
    role: str
    header_row: int = 1
    description: str | None = None
    owner_name: str | None = None
    sheets: dict[str, SheetRule] = field(default_factory=dict)
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SheetPlan:
    name: str
    role: str | None
    header_row: int
    location: str | None
    skip: str | None


def load_profile(path: Path) -> ImportProfile:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("source_name", "file", "role"):
        if not data.get(key):
            raise ProfileError(f"{path.name}: ต้องระบุ '{key}'")
    if data["role"] not in ROLES:
        raise ProfileError(f"{path.name}: role ต้องเป็น {' หรือ '.join(ROLES)}")
    sheets = {}
    for name, rule in (data.get("sheets") or {}).items():
        unknown = set(rule) - {"skip", "role", "header_row", "location"}
        if unknown:
            raise ProfileError(f"{path.name}: ชีต '{name}' มีค่าที่ไม่รู้จัก {sorted(unknown)}")
        if rule.get("role") and rule["role"] not in ROLES:
            raise ProfileError(f"{path.name}: ชีต '{name}' role ต้องเป็น {' หรือ '.join(ROLES)}")
        sheets[name] = SheetRule(**rule)
    return ImportProfile(
        path=path,
        source_name=data["source_name"],
        file=data["file"],
        role=data["role"],
        header_row=int(data.get("header_row", 1)),
        description=data.get("description"),
        owner_name=data.get("owner_name"),
        sheets=sheets,
        notes=tuple(data.get("notes") or ()),
    )


def plan_sheets(profile: ImportProfile, sheet_names: list[str]) -> list[SheetPlan]:
    missing = set(profile.sheets) - set(sheet_names)
    if missing:
        raise ProfileError(f"{profile.path.name}: ไม่พบชีต {sorted(missing)} ในไฟล์ {profile.file}")
    plans = []
    for name in sheet_names:
        rule = profile.sheets.get(name, SheetRule())
        plans.append(SheetPlan(
            name=name,
            role=None if rule.skip else (rule.role or profile.role),
            header_row=rule.header_row or profile.header_row,
            location=rule.location,
            skip=rule.skip,
        ))
    return plans


def image_column(header: tuple) -> int | None:
    for index, value in enumerate(header):
        if normalise_header(value) in IMAGE_HEADERS:
            return index
    return None


def save_sheet_configs(session, source: DataSource, plans: list[SheetPlan]) -> None:
    """Remember each sheet's role and header row; skipped sheets are kept inactive."""
    existing = {
        config.sheet_name: config
        for config in session.scalars(select(SourceSheetConfig).where(SourceSheetConfig.source_id == source.id))
    }
    for plan in plans:
        config = existing.get(plan.name)
        if config is None:
            config = SourceSheetConfig(source_id=source.id, sheet_name=plan.name, read_range="profile")
            session.add(config)
        config.header_row_number = plan.header_row
        config.role = plan.role
        config.is_active = plan.skip is None


def run_profile(profile: ImportProfile, rawdata_dir: Path, dry_run: bool) -> dict:
    workbook_path = (rawdata_dir / profile.file).resolve()
    if not workbook_path.is_file():
        raise ProfileError(f"{profile.path.name}: ไม่พบไฟล์ {workbook_path}")
    workbook = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
    plans = plan_sheets(profile, workbook.sheetnames)
    active = [plan for plan in plans if plan.skip is None]

    photo_columns = {}
    for plan in active:
        header = next(workbook[plan.name].iter_rows(min_row=plan.header_row, max_row=plan.header_row,
                                                    values_only=True), ())
        column = image_column(header)
        if column is not None:
            photo_columns[plan.name] = column
    images = None
    if not dry_run:
        images = extract_embedded_images(workbook_path, profile.source_name, photo_columns, IMAGE_STORAGE_DIR)

    session = SessionLocal()
    try:
        source = session.scalar(select(DataSource).where(DataSource.name == profile.source_name))
        if source is None:
            source = DataSource(name=profile.source_name, connection_type="xlsx_import", classification="internal")
            session.add(source)
        source.owner_name = profile.owner_name or source.owner_name or "ยังไม่ระบุ"
        source.description = profile.description or source.description
        source.external_id = str(workbook_path)
        session.flush()
        save_sheet_configs(session, source, plans)

        sheets = [
            TabularSheet(
                name=plan.name,
                rows=workbook[plan.name].iter_rows(min_row=plan.header_row, values_only=True),
                header_row_number=plan.header_row,
                embedded_image_urls_by_row=images.urls_by_sheet_row.get(plan.name, {}) if images else {},
                duplicate_embedded_image_rows=images.duplicate_rows_by_sheet.get(plan.name, set()) if images else set(),
                skip_unidentified_rows=True,
                max_consecutive_blank_rows=MAX_CONSECUTIVE_BLANK_ROWS,
                default_location=plan.location,
            )
            for plan in active
        ]
        result = sync_tabular_sheets(
            session, source, sheets, f"Imported {workbook_path.name} with profile {profile.path.name}",
        )
        for sheet_name, row_number, media_part in images.unreadable_media if images else []:
            already_reported = session.scalar(select(DataQualityIssue.id).where(
                DataQualityIssue.source_id == source.id,
                DataQualityIssue.source_sheet == sheet_name,
                DataQualityIssue.source_row_number == row_number,
                DataQualityIssue.code == "UNREADABLE_EMBEDDED_IMAGE",
            ))
            if already_reported:
                continue
            session.add(DataQualityIssue(
                source_id=source.id,
                source_sheet=sheet_name,
                source_row_number=row_number,
                severity="warning",
                code="UNREADABLE_EMBEDDED_IMAGE",
                message=f"ภาพที่ฝังในไฟล์ Excel เสียหาย อ่านไม่ได้ ({media_part}) จึงไม่ได้นำภาพนี้เข้า",
            ))
        roles = {plan.name: plan.role for plan in plans}
        for sheet_report in result["sheets"]:
            sheet_report["role"] = roles.get(sheet_report["sheet"])
        result["sheets"] += [
            {"sheet": plan.name, "status": "skipped", "reason": plan.skip} for plan in plans if plan.skip
        ]
        result.update({
            "source_name": profile.source_name,
            "file": profile.file,
            "profile": profile.path.name,
            "dry_run": dry_run,
            "embedded_images_exported": images.exported_count if images else None,
            "unreadable_images": len(images.unreadable_media) if images else 0,
        })
        if dry_run:
            session.rollback()
        else:
            session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def profile_paths(target: Path) -> list[Path]:
    return sorted(target.glob("*.json")) if target.is_dir() else [target]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Import Excel workbooks using import profiles")
    parser.add_argument("target", type=Path, help="a profile .json file, or a folder of profiles")
    parser.add_argument("--rawdata", type=Path, default=Path(DEFAULT_RAWDATA_DIR), help="folder of source workbooks")
    parser.add_argument("--dry-run", action="store_true", help="validate and count without saving anything")
    args = parser.parse_args()

    upgrade_database()
    results = []
    for path in profile_paths(args.target):
        profile = load_profile(path)
        mode = "dry-run" if args.dry_run else "import"
        print(f"{mode}: {path.name} → {profile.source_name}", file=sys.stderr, flush=True)
        results.append(run_profile(profile, args.rawdata, args.dry_run))
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
