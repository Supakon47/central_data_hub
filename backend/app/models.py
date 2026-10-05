from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    owner_name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    connection_type: Mapped[str] = mapped_column(String(50), default="xlsx_import")
    external_id: Mapped[str | None] = mapped_column(String(512))
    classification: Mapped[str] = mapped_column(String(50), default="internal")
    sync_frequency_minutes: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    records: Mapped[list["Record"]] = relationship(back_populates="source")
    sync_runs: Mapped[list["SyncRun"]] = relationship(back_populates="source")
    sheet_configs: Mapped[list["SourceSheetConfig"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class SourceSheetConfig(Base):
    """An approved tab in an external spreadsheet.

    Keeping this allow-list in the central database means the sync command
    cannot be pointed at arbitrary spreadsheets from a web request.
    """

    __tablename__ = "source_sheet_configs"
    __table_args__ = (UniqueConstraint("source_id", "sheet_name", name="uq_source_sheet_config"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)
    sheet_name: Mapped[str] = mapped_column(String(255))
    read_range: Mapped[str] = mapped_column(String(255), default="A:ZZ")
    header_row_number: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    source: Mapped["DataSource"] = relationship(back_populates="sheet_configs")


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_read: Mapped[int] = mapped_column(Integer, default=0)
    rows_inserted: Mapped[int] = mapped_column(Integer, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text)

    source: Mapped["DataSource"] = relationship(back_populates="sync_runs")


class Record(Base):
    __tablename__ = "records"
    __table_args__ = (UniqueConstraint("source_id", "source_sheet", "source_row_key", name="uq_record_source_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)
    source_sheet: Mapped[str] = mapped_column(String(255), index=True)
    source_row_number: Mapped[int] = mapped_column(Integer)
    source_row_key: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    raw_hash: Mapped[str] = mapped_column(String(64), index=True)
    registration_no: Mapped[str | None] = mapped_column(String(255), index=True)
    previous_registration_no: Mapped[str | None] = mapped_column(String(255), index=True)
    title_description: Mapped[str | None] = mapped_column(Text)
    dimensions_text: Mapped[str | None] = mapped_column(Text)
    material: Mapped[str | None] = mapped_column(String(500), index=True)
    period: Mapped[str | None] = mapped_column(String(500), index=True)
    provenance: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(2048))
    status_data_check: Mapped[str | None] = mapped_column(String(100), index=True)
    status_photographed: Mapped[str | None] = mapped_column(String(100), index=True)
    status_antique: Mapped[str | None] = mapped_column(String(100), index=True)
    status_storage: Mapped[str | None] = mapped_column(String(100), index=True)
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    source: Mapped["DataSource"] = relationship(back_populates="records")


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)
    record_id: Mapped[int | None] = mapped_column(ForeignKey("records.id"), index=True)
    source_sheet: Mapped[str | None] = mapped_column(String(255))
    source_row_number: Mapped[int | None] = mapped_column(Integer)
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    code: Mapped[str] = mapped_column(String(100), index=True)
    message: Mapped[str] = mapped_column(Text)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """Append-only record of central-copy edits made through the admin page."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(30), index=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str] = mapped_column(String(100), index=True)
    actor: Mapped[str] = mapped_column(String(100), default="local-admin")
    before_data: Mapped[dict | None] = mapped_column(JSON)
    after_data: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
