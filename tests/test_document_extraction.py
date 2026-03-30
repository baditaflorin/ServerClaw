from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import document_extraction  # noqa: E402


def test_guess_content_type_prefers_reported_type() -> None:
    assert document_extraction.guess_content_type("sample.bin", "application/pdf") == "application/pdf"


def test_should_fallback_to_ocr_for_empty_pdf_and_image_inputs() -> None:
    assert document_extraction.should_fallback_to_ocr("", "application/pdf", "scan.pdf") is True
    assert document_extraction.should_fallback_to_ocr("", "image/png", "scan.png") is True
    assert document_extraction.should_fallback_to_ocr("embedded text", "application/pdf", "scan.pdf") is False


def test_extract_document_returns_tika_result_when_text_is_present(tmp_path, monkeypatch) -> None:
    path = tmp_path / "document.pdf"
    path.write_bytes(b"fake-pdf")

    monkeypatch.setattr(document_extraction, "call_tika_metadata", lambda *_args, **_kwargs: {"Content-Type": "application/pdf"})
    monkeypatch.setattr(document_extraction, "call_tika_text", lambda *_args, **_kwargs: "embedded text")
    called = {"ocr": False}

    def fake_ocr(*_args, **_kwargs):
        called["ocr"] = True
        return {"text": "ocr text"}

    monkeypatch.setattr(document_extraction, "call_tesseract_ocr", fake_ocr)

    payload = document_extraction.extract_document(
        path,
        tika_url="http://tika.local",
        tesseract_url="http://ocr.local",
    )

    assert payload["extraction_method"] == "tika"
    assert payload["fallback_used"] is False
    assert payload["text"] == "embedded text"
    assert called["ocr"] is False


def test_extract_document_falls_back_to_tesseract_when_tika_returns_no_text(tmp_path, monkeypatch) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"fake-pdf")

    monkeypatch.setattr(document_extraction, "call_tika_metadata", lambda *_args, **_kwargs: {"Content-Type": "application/pdf"})
    monkeypatch.setattr(document_extraction, "call_tika_text", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(
        document_extraction,
        "call_tesseract_ocr",
        lambda *_args, **_kwargs: {"text": "ocr text", "page_count": 2, "extraction_method": "tesseract"},
    )

    payload = document_extraction.extract_document(
        path,
        tika_url="http://tika.local",
        tesseract_url="http://ocr.local",
    )

    assert payload["extraction_method"] == "tesseract"
    assert payload["fallback_used"] is True
    assert payload["text"] == "ocr text"
    assert payload["metadata"]["Content-Type"] == "application/pdf"
    assert payload["tika_text"] == ""
