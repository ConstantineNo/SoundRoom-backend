"""Score CRUD operations."""

import os
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.models.score import Score


def get_scores(
    db: Session, skip: int = 0, limit: int = 100
) -> tuple[list[Score], int]:
    """Get a list of scores with pagination. Returns (items, total)."""
    query = db.query(Score)
    total = query.count()
    items = query.offset(skip).limit(limit).all()
    return items, total


def get_score(db: Session, score_id: int) -> Score | None:
    """Get a score by ID."""
    return db.query(Score).filter(Score.id == score_id).first()


def create_score(
    db: Session,
    title: str,
    song_key: str,
    flute_key: str,
    fingering: str,
    image_path: str,
    audio_path: str,
    tags: Optional[list[str]] = None,
    created_by: Optional[int] = None,
) -> Score:
    """Create a new score."""
    db_score = Score(
        title=title,
        song_key=song_key,
        flute_key=flute_key,
        fingering=fingering,
        image_path=image_path,
        audio_path=audio_path,
        tags=tags or [],
        created_by=created_by,
    )
    db.add(db_score)
    db.commit()
    db.refresh(db_score)
    return db_score


def update_score_abc(
    db: Session,
    score_id: int,
    abc_source: str,
    structured_data: dict
) -> Score | None:
    """Update score with ABC content and parsed data."""
    score = get_score(db, score_id)
    if not score:
        return None

    score.abc_source = abc_source
    score.structured_data = structured_data
    score.updated_at = datetime.utcnow()

    db.add(score)
    db.commit()
    db.refresh(score)
    return score


def update_score_metadata(
    db: Session,
    score_id: int,
    title: Optional[str] = None,
    song_key: Optional[str] = None,
    flute_key: Optional[str] = None,
    fingering: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> Score | None:
    """Update score metadata fields. Only provided fields are updated."""
    score = get_score(db, score_id)
    if not score:
        return None
    if title is not None:
        score.title = title
    if song_key is not None:
        score.song_key = song_key
    if flute_key is not None:
        score.flute_key = flute_key
    if fingering is not None:
        score.fingering = fingering
    if tags is not None:
        score.tags = tags
    score.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(score)
    return score


def delete_score(db: Session, score_id: int) -> bool:
    """Delete a score and its associated files. Returns True if deleted, False if not found."""
    score = get_score(db, score_id)
    if not score:
        return False
    image_path = score.image_path
    audio_path = score.audio_path
    db.delete(score)
    db.commit()
    if image_path and os.path.exists(image_path):
        os.remove(image_path)
    if audio_path and os.path.exists(audio_path):
        os.remove(audio_path)
    return True
