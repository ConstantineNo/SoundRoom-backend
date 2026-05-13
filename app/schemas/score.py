"""Score-related Pydantic schemas."""

from datetime import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel, ConfigDict


class ScoreBase(BaseModel):
    """Base score schema with common attributes."""
    title: str
    song_key: str
    flute_key: str
    fingering: str
    tags: Optional[List[str]] = None


class ScoreCreate(ScoreBase):
    """Schema for score creation."""
    pass


class ScoreUpdateABC(BaseModel):
    """Schema for updating ABC content."""
    abc_content: str


class ScoreUpdateMetadata(BaseModel):
    """Schema for updating score metadata. All fields optional."""
    title: Optional[str] = None
    song_key: Optional[str] = None
    flute_key: Optional[str] = None
    fingering: Optional[str] = None
    tags: Optional[List[str]] = None


class Score(ScoreBase):
    """Schema for score response."""
    id: int
    image_path: str
    audio_path: str
    abc_source: Optional[str] = None
    structured_data: Optional[dict] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
