"""Playlist CRUD operations."""

from sqlalchemy.orm import Session

from app.models.playlist import Playlist, PlaylistItem


def get_playlists_by_user(db: Session, user_id: int) -> list[Playlist]:
    """Get all playlists for a user."""
    return db.query(Playlist).filter(Playlist.user_id == user_id).all()


def get_playlist(db: Session, playlist_id: int, user_id: int) -> Playlist | None:
    """Get a playlist by ID, ensuring it belongs to the user."""
    return db.query(Playlist).filter(
        Playlist.id == playlist_id,
        Playlist.user_id == user_id
    ).first()


def create_playlist(db: Session, name: str, user_id: int) -> Playlist:
    """Create a new playlist for a user."""
    db_playlist = Playlist(name=name, user_id=user_id)
    db.add(db_playlist)
    db.commit()
    db.refresh(db_playlist)
    return db_playlist


def create_playlist_item(
    db: Session,
    playlist_id: int,
    score_id: int,
    sort_order: int = 0
) -> PlaylistItem:
    """Add an item to a playlist."""
    db_item = PlaylistItem(
        playlist_id=playlist_id,
        score_id=score_id,
        sort_order=sort_order
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item
