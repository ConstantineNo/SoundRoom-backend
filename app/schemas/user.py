"""User-related Pydantic schemas."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


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
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PasswordChange(BaseModel):
    """Schema for password change."""
    current_password: str
    new_password: str
