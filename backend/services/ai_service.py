import json
import os
import re

from openai import OpenAI


def _fallback_summary_and_tags(text: str) -> dict[str, object]:
    """
    Simple fallback so the endpoint still works without API key.
    This keeps local testing easy for students.
    """
    cleaned = " ".join(text.split())
    words = re.findall(r"[A-Za-z0-9]+", cleaned.lower())

    # Make a short summary by clipping the text.
    summary = cleaned[:180].strip()
    if len(cleaned) > 180:
        summary += "..."

    # Pick up to 5 useful-looking words as lightweight tags.
    skip_words = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "have",
        "you",
        "are",
        "was",
        "but",
        "not",
        "your",
        "about",
    }
    unique_words = []
    for word in words:
        if len(word) < 4 or word in skip_words:
            continue
        if word not in unique_words:
            unique_words.append(word)
        if len(unique_words) == 5:
            break

    return {"summary": summary or "No summary available.", "tags": unique_words}


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
            "Summarize this text in 1-2 sentences. "
            "Also provide 3-5 relevant tags.\n"
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
        clean_tags = [str(tag).strip() for tag in tags if str(tag).strip()]

        if not summary:
            return _fallback_summary_and_tags(text)

        return {"summary": summary, "tags": clean_tags[:5]}
    except Exception:
        # If API fails for any reason, keep app usable with fallback output.
        return _fallback_summary_and_tags(text)
