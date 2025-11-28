from pydantic import BaseModel
from typing import List, Optional

class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    role: str
    class Config:
        orm_mode = True

class ScoreBase(BaseModel):
    title: str
    flute_key: str
    fingering: str
    tags: Optional[List[str]] = None

class ScoreCreate(ScoreBase):
    pass

class Score(ScoreBase):
    id: int
    image_path: str
    audio_path: str
    class Config:
        orm_mode = True

class PlaylistBase(BaseModel):
    name: str

class PlaylistCreate(PlaylistBase):
    pass

class Playlist(PlaylistBase):
    id: int
    user_id: int
    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class PlaylistItemBase(BaseModel):
    score_id: int
    sort_order: int = 0

class PlaylistItemCreate(PlaylistItemBase):
    pass

class PlaylistItem(PlaylistItemBase):
    id: int
    playlist_id: int
    score: Optional[Score] = None
    class Config:
        orm_mode = True

class RecordingBase(BaseModel):
    score_id: int

class RecordingCreate(RecordingBase):
    pass

class Recording(RecordingBase):
    id: int
    user_id: int
    file_path: str
    class Config:
        orm_mode = True
