"""Score model definition."""

from sqlalchemy import Column, Integer, String, JSON, Text

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
