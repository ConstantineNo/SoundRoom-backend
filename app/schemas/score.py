"""Score-related Pydantic schemas."""

from typing import List, Optional
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


class Score(ScoreBase):
    """Schema for score response."""
    id: int
    image_path: str
    audio_path: str
    
    class Config:
        orm_mode = True
