import json
import math
import os
import re
from collections import Counter
from hashlib import md5

from openai import OpenAI

COMMON_STOP_WORDS = {
    # English
    "the", "and", "for", "with", "that", "this", "from", "have", "you", "are", "was", "but",
    "not", "your", "about", "also", "called", "into", "their", "they", "them", "than", "such",
    "many", "very", "more", "most", "can", "has", "had", "its", "it's", "between", "while",
    "including", "some", "used", "using", "often", "only", "other", "these", "those",
    # Norwegian
    "og", "det", "som", "den", "de", "til", "med", "av", "er", "en", "et", "på", "om", "fra",
    "har", "blir", "ble", "kan", "ikke", "også", "eller", "dette", "disse", "sine", "sitt",
    "sin", "der", "hvor", "hvordan", "hva", "hvem", "når", "ordet", "navnet", "brukt", "mange",
    "ofte", "bare", "under", "over", "innen", "mot", "hos", "seg", "sammen", "finnes",
}

# Extra words that are usually weak as standalone tags.
GENERIC_TAG_WORDS = {
    "mange",
    "rundt",
    "navnet",
    "ordet",
    "brukt",
    "ulike",
    "kalles",
    "kalt",
}


def _normalize_word(word: str) -> str:
    """
    Light normalization so simple plural forms map together.
    Example: cats -> cat, dogs -> dog.
    """
    lowered = word.lower().strip()
    if len(lowered) > 4 and lowered.endswith("ies"):
        return f"{lowered[:-3]}y"
    if len(lowered) > 3 and lowered.endswith("es"):
        return lowered[:-2]
    if len(lowered) > 3 and lowered.endswith("s"):
        return lowered[:-1]
    return lowered


def clean_tag_candidates(raw_tags: list[object], max_tags: int = 5) -> list[str]:
    """
    Normalize and filter tag candidates.
    Works for both OpenAI tags and fallback tags.
    """
    cleaned: list[str] = []
    seen = set()
    for raw_tag in raw_tags:
        candidate = _normalize_word(str(raw_tag).strip().lower())
        if not candidate:
            continue
        if candidate in seen:
            continue
        if len(candidate) < 3:
            continue
        if candidate in COMMON_STOP_WORDS or candidate in GENERIC_TAG_WORDS:
            continue
        if candidate.isdigit():
            continue
        seen.add(candidate)
        cleaned.append(candidate)
        if len(cleaned) == max_tags:
            break
    return cleaned


def _fallback_summary_and_tags(text: str) -> dict[str, object]:
    """
    Simple fallback so the endpoint still works without API key.
    This keeps local testing easy for students.
    """
    cleaned = " ".join(text.split())
    words = re.findall(r"[A-Za-z0-9]+", cleaned.lower())

    # Build a keyword profile from the full text first.
    keyword_counter: Counter[str] = Counter()
    for word in words:
        normalized = _normalize_word(word)
        if len(normalized) < 4 or normalized in COMMON_STOP_WORDS:
            continue
        keyword_counter[normalized] += 1

    # Generate a better fallback summary by selecting high-signal sentences.
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
    if not sentences:
        summary = cleaned[:220].strip()
        if len(cleaned) > 220:
            summary += "..."
    else:
        scored_sentences: list[tuple[float, int, str]] = []
        for index, sentence in enumerate(sentences):
            sentence_words = re.findall(r"[A-Za-z0-9]+", sentence.lower())
            if not sentence_words:
                continue
            score = 0.0
            meaningful = 0
            for sentence_word in sentence_words:
                normalized = _normalize_word(sentence_word)
                if len(normalized) < 4 or normalized in COMMON_STOP_WORDS:
                    continue
                score += keyword_counter.get(normalized, 0)
                meaningful += 1
            if meaningful > 0:
                score = score / meaningful
            scored_sentences.append((score, index, sentence))

        if not scored_sentences:
            summary = sentences[0]
        else:
            # Pick top 2 strongest sentences and keep natural reading order.
            top_sentences = sorted(scored_sentences, key=lambda item: item[0], reverse=True)[:2]
            top_sentences_sorted = sorted(top_sentences, key=lambda item: item[1])
            summary = " ".join(sentence for _score, _index, sentence in top_sentences_sorted)
            if len(summary) > 320:
                summary = f"{summary[:317].rstrip()}..."

    # Pick tags from frequency profile, preferring concrete keywords.
    top_tags = clean_tag_candidates([tag for tag, _count in keyword_counter.most_common(20)])
    return {"summary": summary or "No summary available.", "tags": top_tags}


def _fallback_embedding(text: str, dimensions: int = 256) -> list[float]:
    """
    Build a deterministic local embedding when OpenAI is unavailable.
    It is simple, but good enough for MVP semantic matching.
    """
    tokens = re.findall(r"[A-Za-z0-9]+", text.lower())
    if not tokens:
        return [0.0] * dimensions

    vector = [0.0] * dimensions
    for token in tokens:
        normalized = _normalize_word(token)
        # Stable hash across runs to keep vectors comparable.
        bucket = int(md5(normalized.encode("utf-8")).hexdigest(), 16) % dimensions
        vector[bucket] += 1.0

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def create_embedding(text: str) -> list[float]:
    """
    Create embedding for semantic search.
    Uses OpenAI embeddings when possible, otherwise local fallback.
    """
    cleaned = " ".join(text.split())
    if not cleaned:
        return _fallback_embedding("")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _fallback_embedding(cleaned)

    try:
        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        response = client.embeddings.create(model=model, input=cleaned)
        return list(response.data[0].embedding)
    except Exception:
        return _fallback_embedding(cleaned)


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Compute cosine similarity safely even when vectors differ in length.
    """
    if not vec_a or not vec_b:
        return 0.0

    size = min(len(vec_a), len(vec_b))
    if size == 0:
        return 0.0

    a = vec_a[:size]
    b = vec_b[:size]

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def extract_summary_and_tags(text: str) -> dict[str, object]:
    """
    Generate a short summary and tags from note text.
    Uses OpenAI when configured, otherwise falls back to local logic.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _fallback_summary_and_tags(text)

    try:
        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        prompt = (
            "Read the full text and write a fresh 1-2 sentence summary in the same language as the text. "
            "The summary should explain what the whole note is about at a high level. "
            "Paraphrase the text and avoid copying the opening sentence directly. "
            "Prefer an overview of the main topic, purpose, or key facts. "
            "Also provide 3-5 relevant tags that are useful for later search. "
            "Use broad concepts or topics, not random first words or filler words.\n"
            'Return ONLY valid JSON in this exact shape: {"summary": "...", "tags": ["...", "..."]}.\n\n'
            f"Text:\n{text}"
        )

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        raw = response.choices[0].message.content or ""

        # Some models wrap JSON in extra text, so we extract the JSON block.
        match = re.search(r"\{[\s\S]*\}", raw)
        json_blob = match.group(0) if match else raw
        parsed = json.loads(json_blob)

        summary = str(parsed.get("summary", "")).strip()
        tags = parsed.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        clean_tags = clean_tag_candidates(tags)

        if not summary:
            return _fallback_summary_and_tags(text)

        return {"summary": summary, "tags": clean_tags[:5]}
    except Exception:
        # If API fails for any reason, keep app usable with fallback output.
        return _fallback_summary_and_tags(text)
