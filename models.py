from sqlalchemy import Column, Integer, String, ForeignKey, JSON
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    hashed_password = Column(String(100))
    role = Column(String(20), default="user")

class Score(Base):
    __tablename__ = "scores"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100))
    flute_key = Column(String(10))
    fingering = Column(String(10))
    image_path = Column(String(255))
    audio_path = Column(String(255))
    tags = Column(JSON, nullable=True)

class Playlist(Base):
    __tablename__ = "playlists"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String(100))
    
    user = relationship("User")
    items = relationship("PlaylistItem", back_populates="playlist")

class PlaylistItem(Base):
    __tablename__ = "playlist_items"
    id = Column(Integer, primary_key=True, index=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id"))
    score_id = Column(Integer, ForeignKey("scores.id"))
    sort_order = Column(Integer, default=0)
    
    playlist = relationship("Playlist", back_populates="items")
    score = relationship("Score")

class Recording(Base):
    __tablename__ = "recordings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    score_id = Column(Integer, ForeignKey("scores.id"))
    file_path = Column(String(255))
    
    user = relationship("User")
    score = relationship("Score")
