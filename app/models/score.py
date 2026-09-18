"""Score model definition."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, JSON, Text, DateTime, ForeignKey

from sqlalchemy.orm import relationship
from app.core.database import Base


class Score(Base):
    """Musical score model."""
    __tablename__ = "scores"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100))
    song_key = Column(String(10))
    flute_key = Column(String(10))
    fingering = Column(String(10))
    image_path = Column(String(255))
    audio_path = Column(String(255))
    tags = Column(JSON, nullable=True)
    abc_source = Column(Text, nullable=True)
    structured_data = Column(JSON, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    original_key = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    visibility = Column(String(20), nullable=False, default="private", server_default="private")
    revision = Column(Integer, nullable=False, default=1, server_default="1")
    arrangements = relationship("Arrangement", cascade="all, delete-orphan", order_by="Arrangement.id", back_populates="score")
    assets = relationship("ScoreAsset", cascade="all, delete-orphan", order_by="ScoreAsset.id", back_populates="score")

    edition_label = Column(String(100), nullable=True)
    edition_original_artist = Column(String(200), nullable=True)
    edition_performer = Column(String(200), nullable=True)
    edition_album = Column(String(200), nullable=True)
    edition_release_date = Column(String(10), nullable=True)
