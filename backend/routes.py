from datetime import datetime
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from .database import SessionLocal
from .models import Note, Tag
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


SEARCH_STOP_WORDS = {
    "a",
    "an",
    "the",
    "what",
    "is",
    "are",
    "was",
    "were",
    "tell",
    "me",
    "about",
    "of",
    "in",
    "on",
    "to",
    "for",
    "and",
    "or",
}


def _normalize_search_token(token: str) -> str:
    cleaned = token.strip().lower()
    if len(cleaned) > 4 and cleaned.endswith("ies"):
        return f"{cleaned[:-3]}y"
    if len(cleaned) > 3 and cleaned.endswith("es"):
        return cleaned[:-2]
    if len(cleaned) > 3 and cleaned.endswith("s"):
        return cleaned[:-1]
    return cleaned


def _query_variants(text: str) -> list[str]:
    """
    Build a small set of search variants so cat/cats and dog/dogs
    match each other more often without full-text search setup.
    """
    base = text.strip().lower()
    if not base:
        return []

    variants = {base, _normalize_search_token(base)}
    normalized = _normalize_search_token(base)
    if normalized:
        variants.add(f"{normalized}s")
        variants.add(f"{normalized}es")
    return [item for item in variants if item]


def _extract_search_terms(query_text: str) -> list[str]:
    """
    Extract meaningful terms from normal language questions.
    Example: "what is a cat?" -> ["cat", "cats"].
    """
    words = re.findall(r"[a-zA-Z0-9]+", query_text.lower())
    candidates = []
    for word in words:
        if word in SEARCH_STOP_WORDS:
            continue
        if len(word) < 2:
            continue
        candidates.extend(_query_variants(word))

    # Keep order stable while removing duplicates.
    unique_terms = list(dict.fromkeys(candidates))

    # Fallback: if query had only stop words, use full cleaned query.
    if unique_terms:
        return unique_terms[:10]
    cleaned_full_query = query_text.strip().lower()
    return _query_variants(cleaned_full_query)


def _normalize_tags(raw_tags: list[object]) -> list[str]:
    # Normalize tags so duplicates like "AI" and "ai" collapse.
    normalized = []
    seen = set()
    for tag in raw_tags:
        name = str(tag).strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append(name)
    return normalized[:5]


def _to_note_response(note: Note) -> NoteCreateResponse:
    # Convert SQLAlchemy object to API shape used by frontend.
    return NoteCreateResponse(
        id=note.id,
        content=note.content,
        summary=note.summary,
        created_at=note.created_at,
        tags=[tag.name for tag in note.tags],
    )


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
    clean_tags = _normalize_tags(ai_tags)

    note = Note(content=cleaned_content, summary=ai_summary)

    # Reuse existing tags if they exist, otherwise create new ones.
    for tag_name in clean_tags:
        existing_tag = db.query(Tag).filter(Tag.name == tag_name).first()
        if existing_tag:
            note.tags.append(existing_tag)
            continue
        note.tags.append(Tag(name=tag_name))

    db.add(note)
    db.commit()
    saved_note = (
        db.query(Note).options(joinedload(Note.tags)).filter(Note.id == note.id).first()
    )
    if not saved_note:
        raise HTTPException(status_code=500, detail="failed to load saved note")
    return _to_note_response(saved_note)


@router.get("/notes", response_model=list[NoteCreateResponse])
def list_notes(db: Session = Depends(get_db)) -> list[NoteCreateResponse]:
    # Return newest notes first to improve usability in /docs and frontend.
    notes = db.query(Note).options(joinedload(Note.tags)).order_by(Note.created_at.desc()).all()
    return [_to_note_response(note) for note in notes]


@router.get("/search", response_model=list[NoteCreateResponse])
def search_notes(q: str = Query(min_length=1), db: Session = Depends(get_db)) -> list[NoteCreateResponse]:
    query_text = q.strip()
    if not query_text:
        return []

    terms = [f"%{term}%" for term in _extract_search_terms(query_text)]
    if not terms:
        return []

    filters = []
    for term in terms:
        filters.extend(
            [
                Note.content.ilike(term),
                Note.summary.ilike(term),
                Tag.name.ilike(term),
            ]
        )

    results = (
        db.query(Note)
        .options(joinedload(Note.tags))
        .outerjoin(Note.tags)
        .filter(or_(*filters))
        .distinct()
        .order_by(Note.created_at.desc())
        .all()
    )
    return [_to_note_response(note) for note in results]
