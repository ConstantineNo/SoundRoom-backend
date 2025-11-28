from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
import shutil
import os
import models, schemas, database, utils
from typing import List

router = APIRouter(
    prefix="/recordings",
    tags=["recordings"],
    responses={404: {"description": "Not found"}},
)

UPLOAD_DIR = "uploads"

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/", response_model=schemas.Recording) # Need schema
def upload_recording(
    score_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(utils.get_current_user)
):
    # Verify score exists
    score = db.query(models.Score).filter(models.Score.id == score_id).first()
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")

    # Save file
    filename = f"rec_{current_user.id}_{score_id}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    db_recording = models.Recording(
        user_id=current_user.id,
        score_id=score_id,
        file_path=file_path
    )
    db.add(db_recording)
    db.commit()
    db.refresh(db_recording)
    return db_recording

@router.get("/", response_model=List[schemas.Recording]) # Need schema
def read_recordings(db: Session = Depends(get_db), current_user: schemas.User = Depends(utils.get_current_user)):
    recordings = db.query(models.Recording).filter(models.Recording.user_id == current_user.id).all()
    return recordings
