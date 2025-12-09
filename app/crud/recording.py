"""Recording CRUD operations."""

from sqlalchemy.orm import Session

from app.models.recording import Recording


def get_recordings_by_user(db: Session, user_id: int) -> list[Recording]:
    """Get all recordings for a user."""
    return db.query(Recording).filter(Recording.user_id == user_id).all()


def create_recording(
    db: Session,
    user_id: int,
    score_id: int,
    file_path: str
) -> Recording:
    """Create a new recording."""
    db_recording = Recording(
        user_id=user_id,
        score_id=score_id,
        file_path=file_path
    )
    db.add(db_recording)
    db.commit()
    db.refresh(db_recording)
    return db_recording
