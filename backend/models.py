from sqlalchemy import Column, DateTime, Integer, String, func

from .database import Base


class Note(Base):
    # SQL table name in the database.
    __tablename__ = "notes"

    # Basic MVP fields: raw text + optional summary for later AI step.
    id = Column(Integer, primary_key=True, index=True)
    content = Column(String, nullable=False)
    summary = Column(String, nullable=True)
    # Auto timestamp set by the database when the row is created.
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
