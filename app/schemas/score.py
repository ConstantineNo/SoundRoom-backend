"""Score-related Pydantic schemas."""

from typing import List, Optional, Dict
from pydantic import BaseModel


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


class Score(ScoreBase):
    """Schema for score response."""
    id: int
    image_path: str
    audio_path: str
    abc_source: Optional[str] = None
    structured_data: Optional[dict] = None
    
    class Config:
        orm_mode = True
