"""Request bodies accepted by the API. Responses are plain dictionaries."""

from pydantic import BaseModel, ConfigDict, Field


class AdminLogin(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class RecordMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registration_no: str | None = None
    previous_registration_no: str | None = None
    title_description: str | None = None
    dimensions_text: str | None = None
    material: str | None = None
    period: str | None = None
    provenance: str | None = None
    image_url: str | None = None
    status_data_check: str | None = None
    status_photographed: str | None = None
    status_antique: str | None = None
    status_storage: str | None = None


class GoogleSheetConfigMutation(BaseModel):
    """An admin-only allow-list entry; credentials never come from this form."""

    model_config = ConfigDict(extra="forbid")

    source_name: str = Field(min_length=1, max_length=255)
    spreadsheet_id: str = Field(min_length=1, max_length=512)
    sheet_name: str = Field(min_length=1, max_length=255)
    read_range: str = Field(default="A:ZZ", min_length=1, max_length=255)
    owner_name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=5000)


class ImageBridgeConfigMutation(BaseModel):
    """Drive folder details only; no credential is ever accepted from a browser."""

    model_config = ConfigDict(extra="forbid")

    drive_folder_id: str = Field(min_length=1, max_length=512)
    manifest_file_name: str = Field(default="central-data-hub-images.json", min_length=1, max_length=255)


class SyncScheduleMutation(BaseModel):
    """A missing interval means manual sync only for this source."""

    model_config = ConfigDict(extra="forbid")

    sync_frequency_minutes: int | None = Field(default=None, ge=5, le=10080)


class DataQualityIssueResolution(BaseModel):
    """A deliberate staff acknowledgement; source data is never edited here."""

    is_resolved: bool


class LocationMatchReviewMutation(BaseModel):
    """A staff decision about a proposed object-to-location relationship."""

    model_config = ConfigDict(extra="forbid")

    object_record_id: int = Field(gt=0)
    location_record_id: int = Field(gt=0)
    decision: str = Field(pattern="^(approved|rejected)$")
    note: str | None = Field(default=None, max_length=2000)
