from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import shutil
import os
import models, schemas, database, utils
from fastapi.staticfiles import StaticFiles

router = APIRouter(
    prefix="/scores",
    tags=["scores"],
    responses={404: {"description": "Not found"}},
)

UPLOAD_DIR = "uploads"

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/", response_model=schemas.Score)
def create_score(
    title: str = Form(...),
    song_key: str = Form(...),
    flute_key: str = Form(...),
    fingering: str = Form(...),
    tags: Optional[str] = Form(None), # JSON string or comma separated
    image: UploadFile = File(...),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    # current_user: schemas.User = Depends(utils.get_current_user) # Add auth later
):
    # Save files
    image_filename = f"img_{image.filename}"
    audio_filename = f"audio_{audio.filename}"
    image_path = os.path.join(UPLOAD_DIR, image_filename)
    audio_path = os.path.join(UPLOAD_DIR, audio_filename)
    
    with open(image_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)
    with open(audio_path, "wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)
        
    # Parse tags if needed (simple string for now or use json.loads if sent as json)
    # For simplicity, assuming tags is a JSON string or we just store it as is if model allows
    # But model expects JSON. Let's assume it's a list of strings passed as form data? 
    # FastAPI Form doesn't handle List well without separate fields. 
    # Let's keep it simple: tags is a string, we split by comma.
    
    tags_list = tags.split(",") if tags else []
    
    db_score = models.Score(
        title=title,
        song_key=song_key,
        flute_key=flute_key,
        fingering=fingering,
        image_path=image_path,
        audio_path=audio_path,
        tags=tags_list
    )
    db.add(db_score)
    db.commit()
    db.refresh(db_score)
    return db_score

@router.get("/", response_model=List[schemas.Score])
def read_scores(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    scores = db.query(models.Score).offset(skip).limit(limit).all()
    return scores

@router.get("/{score_id}", response_model=schemas.Score)
def read_score(score_id: int, db: Session = Depends(get_db)):
    score = db.query(models.Score).filter(models.Score.id == score_id).first()
    if score is None:
        raise HTTPException(status_code=404, detail="Score not found")
    return score
