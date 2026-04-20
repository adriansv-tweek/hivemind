import base64
import io
import os
from pathlib import Path

import numpy as np
from openai import OpenAI
from PIL import Image

try:
    from rapidocr_onnxruntime import RapidOCR
except ImportError:  # pragma: no cover - optional local OCR fallback.
    RapidOCR = None

_local_ocr_engine = None
_openai_vision_disabled = False


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
    global _openai_vision_disabled

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and not _openai_vision_disabled:
        client = OpenAI(api_key=api_key)
        try:
            model = os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini")
            image_base64 = base64.b64encode(file_bytes).decode("utf-8")
            data_url = f"data:{mime_type};base64,{image_base64}"

            response = client.responses.create(
                model=model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "Extract all readable text from this image. "
                                    "Return plain text only. Do not summarize. "
                                    "If no readable text exists, return an empty string."
                                ),
                            },
                            {
                                "type": "input_image",
                                "image_url": data_url,
                            },
                        ],
                    }
                ],
                timeout=8.0,
            )
            output_text = getattr(response, "output_text", "")
            if output_text and output_text.strip():
                return output_text.strip()
        except Exception as error:
            # Image OCR should still work locally if OpenAI vision is unavailable.
            # If quota is gone, avoid waiting on OpenAI for every next screenshot.
            error_text = str(error).lower()
            if (
                "insufficient_quota" in error_text
                or "rate limit" in error_text
                or "timed out" in error_text
                or "timeout" in error_text
            ):
                _openai_vision_disabled = True

    return _extract_text_from_image_locally(file_bytes)


def _extract_text_from_image_locally(file_bytes: bytes) -> str:
    if RapidOCR is None:
        raise ValueError("Local image OCR is not installed. Run pip install -r requirements.txt.")

    global _local_ocr_engine
    if _local_ocr_engine is None:
        _local_ocr_engine = RapidOCR()

    image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    image_array = np.array(image)
    result, _ = _local_ocr_engine(image_array)
    if not result:
        raise ValueError("No readable text found in image.")

    lines = [str(item[1]).strip() for item in result if len(item) > 1 and str(item[1]).strip()]
    extracted_text = "\n".join(lines).strip()
    if not extracted_text:
        raise ValueError("No readable text found in image.")
    return extracted_text


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
