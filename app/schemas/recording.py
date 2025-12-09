"""Recording-related Pydantic schemas."""

from pydantic import BaseModel


class RecordingBase(BaseModel):
    """Base recording schema."""
    score_id: int


class RecordingCreate(RecordingBase):
    """Schema for recording creation."""
    pass


class Recording(RecordingBase):
    """Schema for recording response."""
    id: int
    user_id: int
    file_path: str
    
    class Config:
        orm_mode = True
