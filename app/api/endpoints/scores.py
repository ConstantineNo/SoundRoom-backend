"""Score endpoints."""

import os
import shutil
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

import math
from fastapi import Query
from app.core.deps import get_db, get_current_user, get_current_admin
from app.core.config import UPLOAD_DIR, ALLOWED_IMAGE_TYPES, ALLOWED_AUDIO_TYPES, MAX_UPLOAD_SIZE
from app.core.responses import APIResponse, paginated_response
from app.schemas import Score, ScoreUpdateABC, ScoreUpdateMetadata
from app.crud import get_scores, get_score, create_score, update_score_abc, update_score_metadata, delete_score
from app.services.score_service import parse_abc_to_json


router = APIRouter(
    tags=["scores"],
    responses={404: {"description": "Not found"}},
)


def _validate_file(file: UploadFile, allowed_types: set, max_size: int):
    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{file.content_type}' is not allowed. Accepted: {sorted(allowed_types)}"
        )
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File size {size} exceeds maximum allowed {max_size} bytes"
        )


def _check_score_ownership(score, current_user) -> None:
    """Verify the current user owns the score or is an admin.

    Legacy scores (created_by is None) are editable by any authenticated user.
    Admin users bypass the ownership check.
    """
    if current_user.role == "admin":
        return
    if score.created_by is not None and score.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="You do not own this score")


def _save_upload(file: UploadFile, prefix: str) -> str:
    filename = f"{prefix}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return file_path


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
    current_user = Depends(get_current_user),
):
    """Create a new score with image and audio files. Requires authentication."""
    _validate_file(image, ALLOWED_IMAGE_TYPES, MAX_UPLOAD_SIZE)
    _validate_file(audio, ALLOWED_AUDIO_TYPES, MAX_UPLOAD_SIZE)

    image_path = _save_upload(image, "img")
    audio_path = _save_upload(audio, "audio")

    tags_list = tags.split(",") if tags else []

    return create_score(
        db=db,
        title=title,
        song_key=song_key,
        flute_key=flute_key,
        fingering=fingering,
        image_path=image_path,
        audio_path=audio_path,
        tags=tags_list,
        created_by=current_user.id,
    )


@router.get("/")
def read_scores_endpoint(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    skip: int = Query(None),
    limit: int = Query(None),
    db: Session = Depends(get_db),
):
    """Get a paginated list of scores.

    Supports both page/size (recommended) and legacy skip/limit parameters.
    If skip/limit are provided, they take precedence.
    """
    if skip is not None and limit is not None:
        items, total = get_scores(db, skip=skip, limit=limit)
        page_used = skip // limit + 1 if limit else 1
        size_used = limit
    else:
        offset = (page - 1) * size
        items, total = get_scores(db, skip=offset, limit=size)
        page_used = page
        size_used = size

    return paginated_response(items=items, page=page_used, size=size_used, total=total)


@router.get("/{score_id}", response_model=Score)
def read_score_endpoint(score_id: int, db: Session = Depends(get_db)):
    """Get a score by ID."""
    score = get_score(db, score_id)
    if score is None:
        raise HTTPException(status_code=404, detail="Score not found")
    return score


@router.put("/{score_id}/abc", response_model=Score)
def update_score_abc_endpoint(
    score_id: int,
    abc_data: ScoreUpdateABC,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Update a score's ABC content and generate structured JSON.
    Requires authentication.
    """
    score = get_score(db, score_id)
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")

    try:
        structured_data = parse_abc_to_json(abc_data.abc_content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal processing error: {str(e)}")

    updated_score = update_score_abc(
        db,
        score_id,
        abc_data.abc_content,
        structured_data
    )

    return updated_score


@router.put("/{score_id}", response_model=Score)
def update_score_metadata_endpoint(
    score_id: int,
    metadata: ScoreUpdateMetadata,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update score metadata. Requires authentication and ownership (or admin)."""
    score = get_score(db, score_id)
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")
    _check_score_ownership(score, current_user)

    updated = update_score_metadata(
        db, score_id,
        title=metadata.title,
        song_key=metadata.song_key,
        flute_key=metadata.flute_key,
        fingering=metadata.fingering,
        tags=metadata.tags,
    )
    return updated


@router.delete("/{score_id}")
def delete_score_endpoint(
    score_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Delete a score and its files. Requires authentication and ownership (or admin)."""
    score = get_score(db, score_id)
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")
    _check_score_ownership(score, current_user)

    delete_score(db, score_id)
    return {"message": "Score deleted"}
