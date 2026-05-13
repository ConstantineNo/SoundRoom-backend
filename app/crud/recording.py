"""Recording CRUD operations."""

import os
from sqlalchemy.orm import Session

from app.models.recording import Recording


def get_recordings_by_user(db: Session, user_id: int) -> list[Recording]:
    """Get all recordings for a user."""
    return db.query(Recording).filter(Recording.user_id == user_id).all()


def get_recording(db: Session, recording_id: int, user_id: int) -> Recording | None:
    """Get a recording by ID, ensuring it belongs to the user."""
    return db.query(Recording).filter(
        Recording.id == recording_id,
        Recording.user_id == user_id,
    ).first()


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


def delete_recording(db: Session, recording_id: int, user_id: int) -> bool:
    """Delete a recording. Also removes the file from disk. Returns True if deleted."""
    recording = get_recording(db, recording_id, user_id)
    if not recording:
        return False
    file_path = recording.file_path
    db.delete(recording)
    db.commit()
    if os.path.exists(file_path):
        os.remove(file_path)
    return True
