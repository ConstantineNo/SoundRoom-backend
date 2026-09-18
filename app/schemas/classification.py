"""Strict write DTOs and explicit classification response schemas."""
from datetime import date
import re
from typing import Generic, Literal, TypeVar
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EditionMetadata(StrictModel):
    """Optional musical edition, retaining partial calendar-date precision."""
    label: str | None = Field(None, max_length=100)
    original_artist: str | None = Field(None, max_length=200)
    performer: str | None = Field(None, max_length=200)
    album: str | None = Field(None, max_length=200)
    release_date: str | None = Field(None, max_length=10, description="YYYY, YYYY-MM or YYYY-MM-DD; no inferred month/day")

    @field_validator("label", "original_artist", "performer", "album", "release_date", mode="before")
    @classmethod
    def normalize_text(cls, value):
        return (value.strip() or None) if isinstance(value, str) else value

    @field_validator("release_date")
    @classmethod
    def valid_release_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.fullmatch(r"[0-9]{4}(?:-[0-9]{2}(?:-[0-9]{2})?)?", value):
            raise ValueError("Use YYYY, YYYY-MM or YYYY-MM-DD")
        parts = [int(part) for part in value.split("-")]
        # Missing components are used only for validation, never written back.
        try:
            date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
        except ValueError:
            raise ValueError("Invalid Gregorian calendar date") from None
        return value


class FingeringInput(StrictModel):
    code: str | None = None
    raw: str | None = Field(None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def one_value(self):
        if (self.code is None) == (self.raw is None) or (self.raw is not None and not self.raw.strip()):
            raise ValueError("Exactly one of code/raw is required")
        return self


class ClassificationDecision(StrictModel):
    method: Literal["candidate", "manual"]
    flute_key: str
    candidate_token: str | None = None

    @model_validator(mode="after")
    def token_required(self):
        if self.method == "candidate" and not self.candidate_token:
            raise ValueError("candidate_token is required")
        return self


class CandidateInput(StrictModel):
    original_key: str = Field(max_length=200)
    local_key: str | None = Field(None, max_length=200)
    performance_key: str | None = Field(None, max_length=200)
    fingering: FingeringInput
    key_basis: Literal["original", "local", "performance"] = "original"
    instrument_profile: str = Field("standard_six_hole_dizi", min_length=1, max_length=100)


class SectionInput(StrictModel):
    id: int | None = Field(None, gt=0)
    location_label: str = Field(min_length=1, max_length=200)
    fingering: FingeringInput
    local_key: str | None = Field(None, max_length=200)
    performance_key: str | None = Field(None, max_length=200)
    key_basis: Literal["original", "local", "performance"] = "original"
    instrument_profile: str = Field("standard_six_hole_dizi", min_length=1, max_length=100)
    notes: str | None = None
    classification_decision: ClassificationDecision | None = None


class ArrangementInput(StrictModel):
    label: str = Field(min_length=1, max_length=100)
    coverage: Literal["complete", "unknown"]
    sections: list[SectionInput] = Field(min_length=1)
    notes: str | None = None
    is_default: bool | None = None


class ScoreCreate(StrictModel):
    edition: EditionMetadata | None = None
    title: str = Field(min_length=1, max_length=100)
    original_key: str = Field(min_length=1, max_length=200)
    fingering: FingeringInput
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    instrument_profile: str = Field("standard_six_hole_dizi", min_length=1, max_length=100)
    classification_decision: ClassificationDecision | None = None

    @field_validator("title", mode="before")
    @classmethod
    def trim_title(cls, value):
        return value.strip() if isinstance(value, str) else value


class ScorePatch(StrictModel):
    edition: EditionMetadata | None = None
    title: str | None = Field(None, min_length=1, max_length=100)
    original_key: str | None = Field(None, min_length=1, max_length=200)
    notes: str | None = None
    tags: list[str] | None = None

    @field_validator("title", mode="before")
    @classmethod
    def trim_title(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def valid_patch(self):
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        if self.model_fields_set == {"edition"} and self.edition is not None and not self.edition.model_fields_set:
            raise ValueError("At least one effective field is required")
        for key in ("title", "original_key", "tags"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        return self


class LegacyPatch(StrictModel):
    title: str | None = Field(None, min_length=1, max_length=100)
    song_key: str | None = Field(None, min_length=1, max_length=200)
    flute_key: str | None = None
    fingering: str | None = None
    tags: list[str] | None = None


class ABCInput(StrictModel):
    abc_content: str


class CopyInput(StrictModel):
    title: str | None = Field(None, min_length=1, max_length=100)

    @field_validator("title", mode="before")
    @classmethod
    def trim_title(cls, value):
        return value.strip() if isinstance(value, str) else value


class PracticeCapability(StrictModel):
    status: Literal["not_provided", "unverified", "available", "unavailable"]
    available: bool = False
    notation_asset_id: int | None = None
    reasons: list[str] = Field(default_factory=list)


class SectionView(StrictModel):
    id: int
    position: int
    location_label: str
    local_key: str | None
    performance_key: str | None
    key_basis: str
    instrument_profile: str
    notes: str | None
    fingering: dict
    flute_key: str | None
    classification_status: str
    classification_evidence: dict | None = None


class ArrangementView(StrictModel):
    id: int
    label: str
    coverage: str
    is_default: bool
    notes: str | None
    sections: list[SectionView]
    classification_complete: bool
    requires_flute_switch: bool | None
    requires_fingering_switch: bool | None
    practice_capability: PracticeCapability


class ScoreSummary(StrictModel):
    edition: EditionMetadata
    id: int
    title: str | None
    original_key: str | None
    notes: str | None
    tags: list[str]
    owner: dict
    visibility: str
    classification_incomplete: bool
    updated_at: str | None
    matched_arrangements: list[dict] | None = None


class ScoreDetail(ScoreSummary):
    arrangements: list[ArrangementView]
    assets: list[dict] = Field(default_factory=list)


class NotationBinding(StrictModel):
    section_id: int = Field(gt=0)
    start_measure: int = Field(ge=1)
    end_measure: int = Field(ge=1)
    part_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_measure < self.start_measure:
            raise ValueError("end_measure must not precede start_measure")
        return self


class NotationBindings(StrictModel):
    notation_asset_id: int = Field(gt=0)
    bindings: list[NotationBinding]


class AssetView(StrictModel):
    id: int
    purpose: str
    arrangement_id: int | None
    media_type: str
    size: int | None
    processing_status: str
    issues: list
    created_at: str


# Generic response models keep OpenAPI aligned with the actual envelope.
T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: T


class ScorePage(StrictModel):
    items: list[ScoreSummary]
    page: int
    size: int
    total: int
    total_pages: int


class Removed(StrictModel):
    removed_id: int
