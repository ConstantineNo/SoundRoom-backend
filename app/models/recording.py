"""Recording model definition."""

from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class Recording(Base):
    """User recording model."""
    __tablename__ = "recordings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    score_id = Column(Integer, ForeignKey("scores.id"))
    file_path = Column(String(255))
    
    user = relationship("User")
    score = relationship("Score")
