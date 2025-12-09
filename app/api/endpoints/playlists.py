"""Playlist endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.schemas import User, Playlist, PlaylistCreate, PlaylistItem
from app.crud import get_playlists_by_user, get_playlist, create_playlist, create_playlist_item, get_score


router = APIRouter(
    tags=["playlists"],
    responses={404: {"description": "Not found"}},
)


@router.post("/", response_model=Playlist)
def create_playlist_endpoint(
    playlist: PlaylistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new playlist."""
    return create_playlist(db, playlist.name, current_user.id)


@router.get("/", response_model=List[Playlist])
def read_playlists_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all playlists for the current user."""
    return get_playlists_by_user(db, current_user.id)


@router.post("/{playlist_id}/items", response_model=PlaylistItem)
def add_item_to_playlist_endpoint(
    playlist_id: int,
    score_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add a score to a playlist."""
    playlist = get_playlist(db, playlist_id, current_user.id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    score = get_score(db, score_id)
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")
    
    return create_playlist_item(db, playlist_id, score_id)
