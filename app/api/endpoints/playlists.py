"""Playlist endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.services.classification import accessible, summary
from app.core.deps import get_db, get_current_user
from app.schemas import User, Playlist, PlaylistCreate, PlaylistItem
from app.crud import (
    get_playlists_by_user, get_playlist, create_playlist, update_playlist,
    delete_playlist, create_playlist_item, delete_playlist_item,
    update_playlist_item_sort, get_score, DuplicatePlaylistItemError,
)


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
    return playlist_view(create_playlist(db, playlist.name, current_user.id), current_user.id)


@router.get("/", response_model=List[Playlist])
def read_playlists_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all playlists for the current user."""
    return [playlist_view(p, current_user.id) for p in get_playlists_by_user(db, current_user.id)]


@router.put("/{playlist_id}", response_model=Playlist)
def rename_playlist_endpoint(
    playlist_id: int,
    name: str = Query(..., description="New playlist name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rename a playlist."""
    playlist = update_playlist(db, playlist_id, current_user.id, name)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return playlist_view(playlist, current_user.id)


@router.delete("/{playlist_id}")
def delete_playlist_endpoint(
    playlist_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a playlist."""
    deleted = delete_playlist(db, playlist_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"message": "Playlist deleted"}


@router.post("/{playlist_id}/items", response_model=PlaylistItem)
def add_item_to_playlist_endpoint(
    playlist_id: int,
    score_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add a score to a playlist."""
    playlist = get_playlist(db, playlist_id, current_user.id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")

    score = accessible(db, score_id, current_user.id)
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")

    try:
        return item_view(create_playlist_item(db, playlist_id, score_id), current_user.id)
    except DuplicatePlaylistItemError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{playlist_id}/items/{item_id}")
def remove_item_from_playlist_endpoint(
    playlist_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove an item from a playlist."""
    playlist = get_playlist(db, playlist_id, current_user.id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")

    deleted = delete_playlist_item(db, item_id, playlist_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Playlist item not found")
    return {"message": "Item removed from playlist"}


@router.put("/{playlist_id}/items/{item_id}/sort", response_model=PlaylistItem)
def reorder_playlist_item_endpoint(
    playlist_id: int,
    item_id: int,
    sort_order: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change the sort order of a playlist item."""
    playlist = get_playlist(db, playlist_id, current_user.id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")

    item = update_playlist_item_sort(db, item_id, playlist_id, sort_order)
    if not item:
        raise HTTPException(status_code=404, detail="Playlist item not found")
    return item_view(item, current_user.id)


def item_view(item, user_id: int) -> dict:
    score = item.score
    visible = score and (score.created_by == user_id or score.visibility == "public")
    return {"id": item.id, "playlist_id": item.playlist_id, "score_id": item.score_id,
            "sort_order": item.sort_order, "created_at": item.created_at,
            "score": summary(score) if visible else None}


def playlist_view(playlist, user_id: int) -> dict:
    return {"id": playlist.id, "name": playlist.name, "user_id": playlist.user_id,
            "created_at": playlist.created_at, "updated_at": playlist.updated_at,
            "items": [item_view(item, user_id) for item in playlist.items]}
