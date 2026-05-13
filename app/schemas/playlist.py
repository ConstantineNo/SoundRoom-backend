"""Playlist-related Pydantic schemas."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict

from app.schemas.score import Score


class PlaylistItemBase(BaseModel):
    """Base playlist item schema."""
    score_id: int
    sort_order: int = 0


class PlaylistItemCreate(PlaylistItemBase):
    """Schema for playlist item creation."""
    pass


class PlaylistItem(PlaylistItemBase):
    """Schema for playlist item response."""
    id: int
    playlist_id: int
    score: Optional[Score] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PlaylistBase(BaseModel):
    """Base playlist schema."""
    name: str


class PlaylistCreate(PlaylistBase):
    """Schema for playlist creation."""
    pass


class Playlist(PlaylistBase):
    """Schema for playlist response."""
    id: int
    user_id: int
    items: List[PlaylistItem] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
