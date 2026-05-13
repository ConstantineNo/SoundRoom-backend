"""Playlist CRUD operations."""

from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.playlist import Playlist, PlaylistItem


class DuplicatePlaylistItemError(Exception):
    """Raised when the same score is added to a playlist twice."""
    pass


def get_playlists_by_user(db: Session, user_id: int) -> list[Playlist]:
    """Get all playlists for a user."""
    return db.query(Playlist).filter(Playlist.user_id == user_id).all()


def get_playlist(db: Session, playlist_id: int, user_id: int) -> Playlist | None:
    """Get a playlist by ID, ensuring it belongs to the user."""
    return db.query(Playlist).filter(
        Playlist.id == playlist_id,
        Playlist.user_id == user_id
    ).first()


def get_playlist_item(db: Session, item_id: int, playlist_id: int) -> PlaylistItem | None:
    """Get a playlist item by ID, ensuring it belongs to the playlist."""
    return db.query(PlaylistItem).filter(
        PlaylistItem.id == item_id,
        PlaylistItem.playlist_id == playlist_id,
    ).first()


def create_playlist(db: Session, name: str, user_id: int) -> Playlist:
    """Create a new playlist for a user."""
    db_playlist = Playlist(name=name, user_id=user_id)
    db.add(db_playlist)
    db.commit()
    db.refresh(db_playlist)
    return db_playlist


def update_playlist(db: Session, playlist_id: int, user_id: int, name: str) -> Playlist | None:
    """Rename a playlist."""
    playlist = get_playlist(db, playlist_id, user_id)
    if not playlist:
        return None
    playlist.name = name
    playlist.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(playlist)
    return playlist


def delete_playlist(db: Session, playlist_id: int, user_id: int) -> bool:
    """Delete a playlist. Returns True if deleted, False if not found."""
    playlist = get_playlist(db, playlist_id, user_id)
    if not playlist:
        return False
    db.delete(playlist)
    db.commit()
    return True


def create_playlist_item(
    db: Session,
    playlist_id: int,
    score_id: int,
    sort_order: int = 0
) -> PlaylistItem:
    """Add an item to a playlist. Raises DuplicatePlaylistItemError if the score is already in the playlist."""
    db_item = PlaylistItem(
        playlist_id=playlist_id,
        score_id=score_id,
        sort_order=sort_order
    )
    db.add(db_item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DuplicatePlaylistItemError(
            f"Score {score_id} is already in playlist {playlist_id}"
        )
    db.refresh(db_item)
    return db_item


def delete_playlist_item(db: Session, item_id: int, playlist_id: int) -> bool:
    """Remove an item from a playlist. Returns True if deleted, False if not found."""
    item = get_playlist_item(db, item_id, playlist_id)
    if not item:
        return False
    db.delete(item)
    db.commit()
    return True


def update_playlist_item_sort(
    db: Session, item_id: int, playlist_id: int, sort_order: int
) -> PlaylistItem | None:
    """Update the sort order of a playlist item."""
    item = get_playlist_item(db, item_id, playlist_id)
    if not item:
        return None
    item.sort_order = sort_order
    db.commit()
    db.refresh(item)
    return item
