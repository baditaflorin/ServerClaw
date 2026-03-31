#!/usr/bin/env python3

from __future__ import annotations

import io
import mimetypes
import os
from typing import Final

import pytesseract
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pdf2image import convert_from_bytes, pdfinfo_from_bytes
from PIL import Image, ImageOps
from pydantic import BaseModel


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:  # pragma: no cover - defensive runtime guard
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < 1:
        raise RuntimeError(f"{name} must be >= 1")
    return value


DEFAULT_LANGUAGE: Final[str] = os.environ.get("TESSERACT_OCR_DEFAULT_LANGUAGE", "eng").strip() or "eng"
MAX_PAGES: Final[int] = env_int("TESSERACT_OCR_MAX_PAGES", 20)
RENDER_DPI: Final[int] = env_int("TESSERACT_OCR_RENDER_DPI", 200)
SUPPORTED_IMAGE_CONTENT_TYPES: Final[set[str]] = {
    "image/bmp",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}
SUPPORTED_IMAGE_EXTENSIONS: Final[set[str]] = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}

app = FastAPI(title="LV3 Tesseract OCR Service", version="1.0.0")


class OCRResponse(BaseModel):
    filename: str
    content_type: str
    extraction_method: str
    languages: str
    page_count: int
    text: str


def detect_content_type(filename: str, reported_content_type: str | None) -> str:
    if reported_content_type and reported_content_type.strip() and reported_content_type != "application/octet-stream":
        return reported_content_type.strip()
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def normalize_image(image: Image.Image) -> Image.Image:
    grayscale = ImageOps.grayscale(image.convert("RGB"))
    return ImageOps.autocontrast(grayscale)


def image_to_text(image: Image.Image, languages: str) -> str:
    return pytesseract.image_to_string(normalize_image(image), lang=languages).strip()


def extract_from_image(data: bytes, languages: str) -> tuple[str, int]:
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        return image_to_text(image, languages), 1


def extract_from_pdf(data: bytes, languages: str) -> tuple[str, int]:
    info = pdfinfo_from_bytes(data)
    page_count = int(info["Pages"])
    if page_count > MAX_PAGES:
        raise HTTPException(
            status_code=413,
            detail=f"PDF has {page_count} pages; the OCR runtime limit is {MAX_PAGES}.",
        )

    images = convert_from_bytes(data, dpi=RENDER_DPI, first_page=1, last_page=page_count, fmt="png")
    texts = [image_to_text(image, languages) for image in images]
    return "\n\n".join(part for part in texts if part), page_count


def languages_or_default(language: str | None) -> str:
    return (language or DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE


@app.get("/healthz")
def healthz() -> dict[str, str | int]:
    return {
        "status": "ok",
        "default_language": DEFAULT_LANGUAGE,
        "max_pages": MAX_PAGES,
        "render_dpi": RENDER_DPI,
    }


@app.post("/ocr", response_model=OCRResponse)
async def ocr(file: UploadFile = File(...), language: str | None = Form(None)) -> OCRResponse:
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    filename = file.filename or "upload"
    content_type = detect_content_type(filename, file.content_type)
    languages = languages_or_default(language)

    try:
        if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
            text, page_count = extract_from_pdf(payload, languages)
            content_type = "application/pdf"
        elif content_type in SUPPORTED_IMAGE_CONTENT_TYPES or any(
            filename.lower().endswith(extension) for extension in SUPPORTED_IMAGE_EXTENSIONS
        ):
            text, page_count = extract_from_image(payload, languages)
        else:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported OCR content type '{content_type}' for '{filename}'.",
            )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - exercised in the live runtime
        raise HTTPException(status_code=422, detail=f"OCR extraction failed: {exc}") from exc

    return OCRResponse(
        filename=filename,
        content_type=content_type,
        extraction_method="tesseract",
        languages=languages,
        page_count=page_count,
        text=text,
    )
