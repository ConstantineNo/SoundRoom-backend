"""User CRUD operations."""

from datetime import datetime
from sqlalchemy.orm import Session

from app.models.user import User
from app.core.security import get_password_hash, verify_password


def get_user_by_username(db: Session, username: str) -> User | None:
    """Get a user by username."""
    return db.query(User).filter(User.username == username).first()


def create_user(db: Session, username: str, password: str) -> User:
    """Create a new user with hashed password."""
    hashed_password = get_password_hash(password)
    db_user = User(username=username, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def update_user_password(
    db: Session, user: User, current_password: str, new_password: str
) -> bool:
    """Change user password. Returns True on success, False if current password is wrong."""
    if not verify_password(current_password, user.hashed_password):
        return False
    user.hashed_password = get_password_hash(new_password)
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return True
