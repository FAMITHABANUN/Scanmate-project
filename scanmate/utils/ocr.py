"""
Handwriting / printed text extraction using Google's Gemini AI (free tier).
See utils/ai_client.py for how to get your free API key.
"""
import os

from google.genai import types

from utils.ai_client import get_client, MISSING_KEY_MESSAGE

MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

EXTRACTION_PROMPT = (
    "Transcribe every word of text in this image exactly as written, "
    "including handwriting. The text may be in any language or script, or a "
    "mix of several - transcribe each part in its ORIGINAL language/script, "
    "do not translate or transliterate anything. Preserve line breaks and "
    "structure (lists, numbers, etc). Return ONLY the transcribed text - no "
    "commentary, no markdown formatting, no quotation marks around it. If "
    "there is truly no readable text in the image, respond with exactly: "
    "[No readable text found]"
)


def extract_text_from_image(image_path: str) -> str:
    client = get_client()
    if client is None:
        return MISSING_KEY_MESSAGE

    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        ext = os.path.splitext(image_path)[1].lower()
        mime_type = MIME_TYPES.get(ext, "image/jpeg")

        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                EXTRACTION_PROMPT,
            ],
        )
        text = (response.text or "").strip()
        return text if text else "[No readable text found]"

    except Exception as e:
        return f"[OCR could not process this image: {e}]"