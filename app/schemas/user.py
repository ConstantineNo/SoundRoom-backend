"""User-related Pydantic schemas."""

from pydantic import BaseModel


class UserBase(BaseModel):
    """Base user schema with common attributes."""
    username: str


class UserCreate(UserBase):
    """Schema for user registration."""
    password: str


class User(UserBase):
    """Schema for user response."""
    id: int
    role: str
    
    class Config:
        orm_mode = True
