"""Persistence for score arrangements and safe creation retries."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base


class Arrangement(Base):
    __tablename__ = "score_arrangements"
    id = Column(Integer, primary_key=True)
    score_id = Column(Integer, ForeignKey("scores.id"), nullable=False, index=True)
    label = Column(String(100), nullable=False)
    coverage = Column(String(20), nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)
    notes = Column(Text)
    score = relationship("Score", back_populates="arrangements")
    sections = relationship("Section", cascade="all, delete-orphan", order_by="Section.position", back_populates="arrangement")


class Section(Base):
    __tablename__ = "score_sections"
    id = Column(Integer, primary_key=True)
    arrangement_id = Column(Integer, ForeignKey("score_arrangements.id"), nullable=False, index=True)
    position = Column(Integer, nullable=False)
    location_label = Column(String(200), nullable=False)
    local_key = Column(String(200))
    performance_key = Column(String(200))
    key_basis = Column(String(20), nullable=False, default="original")
    instrument_profile = Column(String(100), nullable=False, default="standard_six_hole_dizi")
    fingering_code = Column(String(20))
    fingering_raw = Column(String(200))
    flute_key = Column(String(10))
    classification_status = Column(String(20), nullable=False, default="pending")
    evidence = Column(JSON, nullable=False, default=dict)
    notes = Column(Text)
    arrangement = relationship("Arrangement", back_populates="sections")


class IdempotencyRecord(Base):
    __tablename__ = "score_idempotency"
    __table_args__ = (UniqueConstraint("user_id", "method", "path", "key", name="uq_score_idempotency"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    method = Column(String(10), nullable=False)
    path = Column(String(250), nullable=False)
    key = Column(String(200), nullable=False)
    digest = Column(String(64), nullable=False)
    response = Column(JSON, nullable=False)
    etag = Column(String(100), nullable=False)
    expires_at = Column(DateTime, nullable=False)


class ScoreAsset(Base):
    __tablename__ = "score_assets"
    id = Column(Integer, primary_key=True)
    score_id = Column(Integer, ForeignKey("scores.id"), nullable=False, index=True)
    arrangement_id = Column(Integer, ForeignKey("score_arrangements.id", ondelete="SET NULL"))
    purpose = Column(String(30), nullable=False)
    storage_key = Column(String(100), nullable=False)
    legacy_path = Column(String(255), nullable=True)
    media_type = Column(String(100), nullable=False)
    size = Column(Integer, nullable=True)
    processing_status = Column(String(20), nullable=False)
    issues = Column(JSON, nullable=False, default=list)
    # Publication of a score never grants permission to expose its attachments.
    public_allowed = Column(Boolean, nullable=False, default=False)
    copy_allowed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False)
    score = relationship("Score", back_populates="assets")
