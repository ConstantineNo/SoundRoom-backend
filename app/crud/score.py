"""Score CRUD operations."""

from typing import Optional
from sqlalchemy.orm import Session

from app.models.score import Score


def get_scores(db: Session, skip: int = 0, limit: int = 100) -> list[Score]:
    """Get a list of scores with pagination."""
    return db.query(Score).offset(skip).limit(limit).all()


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
    tags: Optional[list[str]] = None
) -> Score:
    """Create a new score."""
    db_score = Score(
        title=title,
        song_key=song_key,
        flute_key=flute_key,
        fingering=fingering,
        image_path=image_path,
        audio_path=audio_path,
        tags=tags or []
    )
    db.add(db_score)
    db.commit()
    db.refresh(db_score)
    return db_score
