from datetime import datetime
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from .database import SessionLocal
from .models import Note, NoteEmbedding, Tag
from .services.ai_service import clean_tag_candidates, cosine_similarity, create_embedding, extract_summary_and_tags

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


class ReindexResponse(BaseModel):
    total_notes: int
    updated_notes: int


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
    # Keep tag hygiene in one place for all flows.
    return clean_tag_candidates(raw_tags, max_tags=5)


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


def _combined_relevance_score(semantic_score: float, keyword_score: float) -> float:
    """
    Hybrid ranking with stronger keyword boost for exact/simple queries.
    This avoids scary low scores for obviously relevant matches.
    """
    combined = (0.6 * semantic_score) + (0.4 * keyword_score)
    if keyword_score >= 0.99:
        return max(combined, 0.82)
    if keyword_score >= 0.6:
        return max(combined, 0.68)
    return combined


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


def _assign_tags_to_note(note: Note, tag_names: list[str], db: Session) -> None:
    """
    Replace note tags with current normalized set.
    This lets us reindex old notes cleanly.
    """
    note.tags.clear()
    for tag_name in tag_names:
        existing_tag = db.query(Tag).filter(Tag.name == tag_name).first()
        if existing_tag:
            note.tags.append(existing_tag)
            continue
        note.tags.append(Tag(name=tag_name))


def _refresh_note_ai_data(note: Note, db: Session) -> None:
    """
    Recompute summary, tags, and embedding for a note based on current logic.
    """
    ai_result = extract_summary_and_tags(note.content)
    ai_summary = str(ai_result.get("summary", "")).strip() or None
    ai_tags = ai_result.get("tags", [])
    if not isinstance(ai_tags, list):
        ai_tags = []
    clean_tags = _normalize_tags(ai_tags)

    note.summary = ai_summary
    _assign_tags_to_note(note, clean_tags, db)

    embedding_text = _build_note_embedding_text(note.content, ai_summary, clean_tags)
    new_embedding = NoteEmbedding(vector_json=json.dumps(create_embedding(embedding_text)))
    note.embedding = new_embedding


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

    note = Note(content=cleaned_content)
    _refresh_note_ai_data(note, db)

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


@router.post("/admin/reindex", response_model=ReindexResponse)
def reindex_notes(db: Session = Depends(get_db)) -> ReindexResponse:
    """
    Reprocess all existing notes with current summary/tag/embedding logic.
    Useful after quality improvements so older notes catch up.
    """
    notes = db.query(Note).options(joinedload(Note.tags), joinedload(Note.embedding)).all()
    updated_count = 0
    for note in notes:
        _refresh_note_ai_data(note, db)
        updated_count += 1

    db.commit()
    return ReindexResponse(total_notes=len(notes), updated_notes=updated_count)


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
        combined_score = _combined_relevance_score(semantic_score, keyword_score)
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
