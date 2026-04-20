from datetime import datetime
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from .database import SessionLocal
from .models import Note, NoteEmbedding, Tag
from .services.ai_service import cosine_similarity, create_embedding, extract_summary_and_tags

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
    relevance_score: float | None = None


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
        relevance_score=None,
    )


def _build_note_embedding_text(content: str, summary: str | None, tags: list[str]) -> str:
    # Store one semantic representation containing content + structure.
    joined_tags = ", ".join(tags)
    return f"Summary: {summary or ''}\nTags: {joined_tags}\nContent: {content}"


def _keyword_match_score(note: Note, search_terms: list[str]) -> float:
    if not search_terms:
        return 0.0
    searchable_text = " ".join(
        [
            note.content or "",
            note.summary or "",
            " ".join(tag.name for tag in note.tags),
        ]
    ).lower()
    matches = sum(1 for term in search_terms if term in searchable_text)
    return matches / max(1, len(search_terms))


def _read_note_embedding(note: Note) -> list[float]:
    # Old notes might not have embedding yet, so compute on the fly.
    if note.embedding and note.embedding.vector_json:
        try:
            parsed = json.loads(note.embedding.vector_json)
            if isinstance(parsed, list):
                return [float(value) for value in parsed]
        except Exception:
            pass

    note_tags = [tag.name for tag in note.tags]
    embedding_text = _build_note_embedding_text(note.content, note.summary, note_tags)
    return create_embedding(embedding_text)


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

    # Save semantic embedding so future search can find this note by meaning.
    embedding_text = _build_note_embedding_text(cleaned_content, ai_summary, clean_tags)
    note.embedding = NoteEmbedding(vector_json=json.dumps(create_embedding(embedding_text)))

    db.add(note)
    db.commit()
    saved_note = (
        db.query(Note)
        .options(joinedload(Note.tags), joinedload(Note.embedding))
        .filter(Note.id == note.id)
        .first()
    )
    if not saved_note:
        raise HTTPException(status_code=500, detail="failed to load saved note")
    return _to_note_response(saved_note)


@router.get("/notes", response_model=list[NoteCreateResponse])
def list_notes(db: Session = Depends(get_db)) -> list[NoteCreateResponse]:
    # Return newest notes first to improve usability in /docs and frontend.
    notes = (
        db.query(Note)
        .options(joinedload(Note.tags), joinedload(Note.embedding))
        .order_by(Note.created_at.desc())
        .all()
    )
    return [_to_note_response(note) for note in notes]


@router.get("/search", response_model=list[NoteCreateResponse])
def search_notes(q: str = Query(min_length=1), db: Session = Depends(get_db)) -> list[NoteCreateResponse]:
    query_text = q.strip()
    if not query_text:
        return []

    search_terms = _extract_search_terms(query_text)
    if not search_terms:
        return []

    query_embedding = create_embedding(query_text)
    notes = (
        db.query(Note)
        .options(joinedload(Note.tags), joinedload(Note.embedding))
        .order_by(Note.created_at.desc())
        .all()
    )
    ranked_results: list[tuple[float, Note]] = []
    for note in notes:
        note_embedding = _read_note_embedding(note)
        semantic_score = cosine_similarity(query_embedding, note_embedding)
        keyword_score = _keyword_match_score(note, search_terms)

        # Hybrid score keeps literal matches useful while adding semantic recall.
        combined_score = (0.75 * semantic_score) + (0.25 * keyword_score)
        if combined_score < 0.12 and keyword_score == 0:
            continue
        ranked_results.append((combined_score, note))

    ranked_results.sort(key=lambda item: item[0], reverse=True)

    response: list[NoteCreateResponse] = []
    for score, note in ranked_results[:20]:
        note_response = _to_note_response(note)
        note_response.relevance_score = round(score, 4)
        response.append(note_response)
    return response
