"""Recording endpoints."""

import os
import shutil
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.core.config import UPLOAD_DIR, ALLOWED_AUDIO_TYPES, MAX_UPLOAD_SIZE
from app.schemas import User, Recording
from app.crud import get_recordings_by_user, create_recording, delete_recording, get_score


router = APIRouter(
    tags=["recordings"],
    responses={404: {"description": "Not found"}},
)


@router.post("/", response_model=Recording)
def upload_recording_endpoint(
    score_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a recording for a score. Requires authentication."""
    score = get_score(db, score_id)
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")

    if file.content_type and file.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{file.content_type}' is not allowed. Accepted: {sorted(ALLOWED_AUDIO_TYPES)}"
        )
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File size {size} exceeds maximum allowed {MAX_UPLOAD_SIZE} bytes"
        )

    filename = f"rec_{current_user.id}_{score_id}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return create_recording(db, current_user.id, score_id, file_path)


@router.get("/", response_model=List[Recording])
def read_recordings_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all recordings for the current user."""
    return get_recordings_by_user(db, current_user.id)


@router.delete("/{recording_id}")
def delete_recording_endpoint(
    recording_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a recording. Removes file from disk."""
    deleted = delete_recording(db, recording_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Recording not found")
    return {"message": "Recording deleted"}
