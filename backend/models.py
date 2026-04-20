from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

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
    # Many-to-many relation through NoteTag.
    tags = relationship("Tag", secondary="note_tags", back_populates="notes")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    # Keep tag names unique so we can reuse existing tags.
    name = Column(String, unique=True, nullable=False, index=True)
    notes = relationship("Note", secondary="note_tags", back_populates="tags")


class NoteTag(Base):
    __tablename__ = "note_tags"

    note_id = Column(Integer, ForeignKey("notes.id"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id"), primary_key=True)
