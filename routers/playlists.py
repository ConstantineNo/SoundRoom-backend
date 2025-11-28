from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import models, schemas, database, utils

router = APIRouter(
    prefix="/playlists",
    tags=["playlists"],
    responses={404: {"description": "Not found"}},
)

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/", response_model=schemas.Playlist)
def create_playlist(playlist: schemas.PlaylistCreate, db: Session = Depends(get_db), current_user: schemas.User = Depends(utils.get_current_user)):
    db_playlist = models.Playlist(name=playlist.name, user_id=current_user.id)
    db.add(db_playlist)
    db.commit()
    db.refresh(db_playlist)
    return db_playlist

@router.get("/", response_model=List[schemas.Playlist])
def read_playlists(db: Session = Depends(get_db), current_user: schemas.User = Depends(utils.get_current_user)):
    playlists = db.query(models.Playlist).filter(models.Playlist.user_id == current_user.id).all()
    return playlists

@router.post("/{playlist_id}/items", response_model=schemas.PlaylistItem) # Need schema for this
def add_item_to_playlist(playlist_id: int, score_id: int, db: Session = Depends(get_db), current_user: schemas.User = Depends(utils.get_current_user)):
    playlist = db.query(models.Playlist).filter(models.Playlist.id == playlist_id, models.Playlist.user_id == current_user.id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    # Check if score exists
    score = db.query(models.Score).filter(models.Score.id == score_id).first()
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")

    item = models.PlaylistItem(playlist_id=playlist_id, score_id=score_id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item # This will fail if schema doesn't match. Need to add PlaylistItem schema.
