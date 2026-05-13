# CRUD module - Database operations
from app.crud.user import get_user_by_username, create_user, update_user_password
from app.crud.score import (
    get_scores, get_score, create_score, update_score_abc,
    update_score_metadata, delete_score,
)
from app.crud.playlist import (
    get_playlists_by_user, get_playlist, create_playlist, update_playlist,
    delete_playlist, create_playlist_item, delete_playlist_item,
    update_playlist_item_sort, DuplicatePlaylistItemError,
)
from app.crud.recording import get_recordings_by_user, get_recording, create_recording, delete_recording

__all__ = [
    "get_user_by_username", "create_user", "update_user_password",
    "get_scores", "get_score", "create_score", "update_score_abc",
    "update_score_metadata", "delete_score",
    "get_playlists_by_user", "get_playlist", "create_playlist", "update_playlist",
    "delete_playlist", "create_playlist_item", "delete_playlist_item",
    "update_playlist_item_sort", "DuplicatePlaylistItemError",
    "get_recordings_by_user", "get_recording", "create_recording", "delete_recording",
]
