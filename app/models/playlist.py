"""Playlist and PlaylistItem model definitions."""

from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class Playlist(Base):
    """User playlist model."""
    __tablename__ = "playlists"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String(100))
    
    user = relationship("User")
    items = relationship("PlaylistItem", back_populates="playlist")


class PlaylistItem(Base):
    """Playlist item linking playlists to scores."""
    __tablename__ = "playlist_items"
    
    id = Column(Integer, primary_key=True, index=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id"))
    score_id = Column(Integer, ForeignKey("scores.id"))
    sort_order = Column(Integer, default=0)
    
    playlist = relationship("Playlist", back_populates="items")
    score = relationship("Score")
