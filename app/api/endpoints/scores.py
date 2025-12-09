"""Score endpoints."""

import os
import shutil
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.config import UPLOAD_DIR
from app.schemas import Score
from app.crud import get_scores, get_score, create_score


router = APIRouter(
    tags=["scores"],
    responses={404: {"description": "Not found"}},
)


@router.post("/", response_model=Score)
def create_score_endpoint(
    title: str = Form(...),
    song_key: str = Form(...),
    flute_key: str = Form(...),
    fingering: str = Form(...),
    tags: Optional[str] = Form(None),
    image: UploadFile = File(...),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Create a new score with image and audio files."""
    # Save files
    image_filename = f"img_{image.filename}"
    audio_filename = f"audio_{audio.filename}"
    image_path = os.path.join(UPLOAD_DIR, image_filename)
    audio_path = os.path.join(UPLOAD_DIR, audio_filename)
    
    with open(image_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)
    with open(audio_path, "wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)
    
    # Parse tags
    tags_list = tags.split(",") if tags else []
    
    return create_score(
        db=db,
        title=title,
        song_key=song_key,
        flute_key=flute_key,
        fingering=fingering,
        image_path=image_path,
        audio_path=audio_path,
        tags=tags_list
    )


@router.get("/", response_model=List[Score])
def read_scores_endpoint(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Get a list of scores."""
    return get_scores(db, skip=skip, limit=limit)


@router.get("/{score_id}", response_model=Score)
def read_score_endpoint(score_id: int, db: Session = Depends(get_db)):
    """Get a score by ID."""
    score = get_score(db, score_id)
    if score is None:
        raise HTTPException(status_code=404, detail="Score not found")
    return score
