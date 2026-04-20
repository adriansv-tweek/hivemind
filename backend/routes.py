from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Note
from .services.ai_service import extract_summary_and_tags

router = APIRouter()


class NoteCreate(BaseModel):
    content: str


class NoteResponse(BaseModel):
    id: int
    content: str
    summary: str | None
    created_at: datetime


class NoteCreateResponse(NoteResponse):
    tags: list[str]


def get_db() -> Session:
    # Yield one DB session per request, then close it safely.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/note", response_model=NoteCreateResponse)
def create_note(payload: NoteCreate, db: Session = Depends(get_db)) -> NoteCreateResponse:
    # Keep validation simple in MVP: text must contain visible characters.
    cleaned_content = payload.content.strip()
    if not cleaned_content:
        raise HTTPException(status_code=400, detail="content cannot be empty")

    # Step 2: enrich the note with AI-generated summary and tags.
    ai_result = extract_summary_and_tags(cleaned_content)
    ai_summary = str(ai_result.get("summary", "")).strip() or None
    ai_tags = ai_result.get("tags", [])
    if not isinstance(ai_tags, list):
        ai_tags = []

    note = Note(content=cleaned_content)
    db.add(note)
    db.commit()
    db.refresh(note)

    # We return AI metadata in POST response, but keep DB schema simple for now.
    return NoteCreateResponse(
        id=note.id,
        content=note.content,
        summary=ai_summary,
        created_at=note.created_at,
        tags=[str(tag).strip() for tag in ai_tags if str(tag).strip()],
    )


@router.get("/notes", response_model=list[NoteResponse])
def list_notes(db: Session = Depends(get_db)) -> list[Note]:
    # Return newest notes first to improve usability in /docs and frontend.
    return db.query(Note).order_by(Note.created_at.desc()).all()
