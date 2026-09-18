"""Close the old public static-file bypass without exposing storage paths."""
from pathlib import Path
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.core.config import UPLOAD_DIR
from app.core.deps import get_current_user, get_db
from app.core.classification_errors import ClassificationError
from app.models.score import Score
from app.models.recording import Recording

router = APIRouter()


@router.get("/uploads/{filename:path}", include_in_schema=False)
def legacy_upload(filename: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    root = Path(UPLOAD_DIR).resolve()
    path = (root / filename).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ClassificationError(404, "NOT_FOUND")
    candidates = [str(Path(UPLOAD_DIR) / filename), str(path), "/uploads/" + filename]
    owned_score = db.scalar(select(Score.id).where(Score.created_by == user.id,
        or_(Score.image_path.in_(candidates), Score.audio_path.in_(candidates))))
    owned_recording = db.scalar(select(Recording.id).where(Recording.user_id == user.id, Recording.file_path.in_(candidates)))
    if owned_score is None and owned_recording is None:
        raise ClassificationError(404, "NOT_FOUND")
    return FileResponse(path, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
