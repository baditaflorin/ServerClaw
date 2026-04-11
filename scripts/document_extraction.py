#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.request
import uuid
from pathlib import Path
from typing import Any


IMAGE_CONTENT_TYPES = {
    "image/bmp",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}
OCR_EXTENSIONS = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


def guess_content_type(filename: str, reported_content_type: str | None = None) -> str:
    if reported_content_type and reported_content_type.strip():
        return reported_content_type.strip()
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def http_request(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[bytes, dict[str, str]]:
    request = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read()
        response_headers = {key: value for key, value in response.headers.items()}
    return body, response_headers


def call_tika_metadata(document: bytes, tika_url: str, content_type: str) -> dict[str, Any]:
    body, _headers = http_request(
        f"{tika_url.rstrip('/')}/meta",
        method="PUT",
        data=document,
        headers={
            "Accept": "application/json",
            "Content-Type": content_type,
        },
    )
    return json.loads(body.decode("utf-8"))


def call_tika_text(document: bytes, tika_url: str, content_type: str) -> str:
    body, _headers = http_request(
        f"{tika_url.rstrip('/')}/tika",
        method="PUT",
        data=document,
        headers={
            "Accept": "text/plain",
            "Content-Type": content_type,
        },
    )
    return body.decode("utf-8")


def build_multipart_body(
    *,
    fields: dict[str, str],
    file_field: str,
    filename: str,
    content_type: str,
    content: bytes,
) -> tuple[bytes, str]:
    boundary = f"lv3-boundary-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    for key, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )

    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            (f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n').encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks), boundary


def call_tesseract_ocr(
    document: bytes,
    tesseract_url: str,
    *,
    filename: str,
    content_type: str,
) -> dict[str, Any]:
    body, boundary = build_multipart_body(
        fields={},
        file_field="file",
        filename=filename,
        content_type=content_type,
        content=document,
    )
    response_body, _headers = http_request(
        f"{tesseract_url.rstrip('/')}/ocr",
        method="POST",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
    )
    return json.loads(response_body.decode("utf-8"))


def should_fallback_to_ocr(text: str, content_type: str, filename: str) -> bool:
    normalized_type = content_type.split(";", 1)[0].strip().lower()
    suffix = Path(filename).suffix.lower()
    return not text.strip() and (
        normalized_type in IMAGE_CONTENT_TYPES or normalized_type == "application/pdf" or suffix in OCR_EXTENSIONS
    )


def extract_document(
    path: Path,
    *,
    tika_url: str,
    tesseract_url: str,
    declared_content_type: str | None = None,
) -> dict[str, Any]:
    document = path.read_bytes()
    guessed_content_type = guess_content_type(path.name, declared_content_type)
    metadata = call_tika_metadata(document, tika_url, guessed_content_type)
    detected_content_type = str(metadata.get("Content-Type", guessed_content_type)).split(";", 1)[0].strip()
    tika_text = call_tika_text(document, tika_url, guessed_content_type)

    if should_fallback_to_ocr(tika_text, detected_content_type, path.name):
        ocr_payload = call_tesseract_ocr(
            document,
            tesseract_url,
            filename=path.name,
            content_type=detected_content_type or guessed_content_type,
        )
        return {
            "filename": path.name,
            "content_type": detected_content_type or guessed_content_type,
            "extraction_method": "tesseract",
            "fallback_used": True,
            "text": ocr_payload.get("text", ""),
            "metadata": metadata,
            "tika_text": tika_text,
        }

    return {
        "filename": path.name,
        "content_type": detected_content_type or guessed_content_type,
        "extraction_method": "tika",
        "fallback_used": False,
        "text": tika_text,
        "metadata": metadata,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract document text through Apache Tika first, then fall back to Tesseract OCR when Tika returns no text."
    )
    parser.add_argument("path", type=Path, help="Path to the document to extract.")
    parser.add_argument(
        "--tika-url",
        default=os.environ.get("LV3_TIKA_BASE_URL", "http://127.0.0.1:9998"),
        help="Base URL for the Apache Tika runtime.",
    )
    parser.add_argument(
        "--tesseract-url",
        default=os.environ.get("LV3_TESSERACT_OCR_BASE_URL", "http://127.0.0.1:3008"),
        help="Base URL for the Tesseract OCR runtime.",
    )
    parser.add_argument(
        "--content-type",
        default=None,
        help="Optional declared content type when the filename extension is not enough.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.path.is_file():
        print(f"error: file not found: {args.path}", file=sys.stderr)
        return 1

    payload = extract_document(
        args.path,
        tika_url=args.tika_url,
        tesseract_url=args.tesseract_url,
        declared_content_type=args.content_type,
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
