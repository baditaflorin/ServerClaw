# ADR 0286: Tesseract OCR Service For Scanned Image Text Extraction

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

ADR 0275 established Apache Tika as the document extraction layer for the
RAG pipeline. Tika explicitly does not perform OCR: it extracts embedded text
from PDFs and Office documents, but returns empty content for:

- PDFs that are scanned images without an embedded text layer
- TIFF, PNG, and JPG images containing printed or handwritten text
- legacy fax documents converted to PDF image format

This is a known and stated boundary of ADR 0275. A meaningful fraction of
real-world documents that operators and agents need to ingest fall into one
of these categories: legacy invoices, scanned contracts, photographed
whiteboards, and printed configuration sheets.

Tesseract is the reference open-source OCR engine, CPU-only, maintained under
the Apache 2.0 licence, and accurate at printed text across 100+ languages.
`tesseract-ocr-server` wraps it behind a simple HTTP API so that it can be
called like any other extraction service.

## Decision

We will deploy **Tesseract OCR** as a REST service to fill the image-OCR gap
left by Tika's stated boundary.

### Deployment rules

- Tesseract OCR service runs as a Docker Compose service on the docker-runtime
  VM alongside Tika
- it is internal-only; no public subdomain is issued
- the service is stateless; it requires no database, no volume, and no secrets
- language packs beyond English (default) are declared in the Ansible role
  defaults and installed at image build time

### Extraction pipeline integration

- the RAG ingestion pipeline calls Tika first for all uploads
- if Tika returns an empty body and the MIME type indicates an image or
  image-PDF, the pipeline falls back to Tesseract OCR
- Tesseract receives either a raw image file or an image-bearing PDF and
  returns extracted plaintext
- the pipeline marks OCR-extracted documents in the provenance record with
  `extraction_method: tesseract` so that downstream consumers can apply
  appropriate confidence weighting

### Accepted input types

- TIFF, PNG, JPEG, BMP, GIF (direct image OCR)
- single-page and multi-page PDF composed entirely of scanned images
- WebP images

## Consequences

**Positive**

- The document ingestion pipeline handles the full spectrum of real-world
  document types including scanned and image-only content.
- Tesseract's CPU-only operation requires no hardware change; accuracy at
  `tessdata_best` engine mode is sufficient for printed document quality.
- The fallback-on-empty-Tika pattern keeps the pipeline logic simple and
  avoids sending every document through both engines.
- Language pack declarations in the Ansible role make multi-language OCR
  support explicit and reproducible.

**Negative / Trade-offs**

- Tesseract accuracy degrades significantly on handwritten text, low-resolution
  scans (below 300 DPI), and complex multi-column layouts; extracted text from
  these sources must be treated as approximate.
- OCR processing is CPU-intensive; large batches of scanned PDFs should be
  rate-limited at the ingestion queue level.

## Boundaries

- Tesseract OCR fills the image-text extraction gap only; it does not replace
  Tika for documents with embedded text.
- Tesseract does not perform layout analysis, table extraction, or document
  structure inference; it returns flat plaintext.
- Tesseract is not used for real-time video frame analysis or live camera
  input; it processes static image files only.
- Handwriting recognition is out of scope; Tesseract is deployed for printed
  document OCR only.

## Related ADRs

- ADR 0198: Qdrant vector search for semantic platform RAG
- ADR 0274: MinIO as the S3-compatible object storage layer
- ADR 0275: Apache Tika Server for document text extraction in the RAG pipeline
- ADR 0276: NATS JetStream as the platform event bus

## References

- <https://tesseract-ocr.github.io/tessdoc/>
