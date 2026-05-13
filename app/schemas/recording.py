"""Recording-related Pydantic schemas."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class RecordingBase(BaseModel):
    """Base recording schema."""
    score_id: int


class RecordingCreate(RecordingBase):
    """Schema for recording creation."""
    pass


class Recording(RecordingBase):
    """Schema for recording response."""
    id: int
    user_id: int
    file_path: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
