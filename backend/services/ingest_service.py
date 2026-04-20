import base64
import io
import os
from pathlib import Path

from openai import OpenAI


def _extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise ValueError("PDF support is not installed. Run pip install -r requirements.txt.") from error

    reader = PdfReader(io.BytesIO(file_bytes))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(part for part in parts if part.strip()).strip()


def _extract_text_from_image(file_bytes: bytes, mime_type: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Image text extraction requires OPENAI_API_KEY.")

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")
    image_base64 = base64.b64encode(file_bytes).decode("utf-8")
    data_url = f"data:{mime_type};base64,{image_base64}"

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Extract all readable text from this image. "
                            "Return plain text only. Do not summarize. "
                            "If no readable text exists, return an empty string."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                ],
            }
        ],
        temperature=0,
    )
    return (response.choices[0].message.content or "").strip()


def extract_text_from_file(filename: str, file_bytes: bytes, content_type: str | None) -> str:
    suffix = Path(filename).suffix.lower()
    mime_type = (content_type or "").lower()

    if suffix == ".pdf" or mime_type == "application/pdf":
        return _extract_text_from_pdf(file_bytes)

    if mime_type.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return _extract_text_from_image(file_bytes, mime_type or "image/png")

    if mime_type.startswith("text/") or suffix in {".txt", ".md"}:
        return file_bytes.decode("utf-8", errors="ignore").strip()

    raise ValueError("Unsupported file type. Use PDF or image files.")
