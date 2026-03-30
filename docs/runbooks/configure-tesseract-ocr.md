# Configure Tesseract OCR

## Purpose

This runbook converges ADR 0286 so scanned-image and image-only documents have
a shared, private OCR fallback service on `docker-runtime-lv3`.

## Result

- `docker-runtime-lv3` builds the repo-managed Tesseract OCR image from `/opt/tesseract-ocr/app`
- the private runtime listens on `10.10.10.20:3008`
- the service exposes `/healthz` and `/ocr`
- repo-managed verification confirms the OCR route extracts deterministic text from a known image fixture
- `scripts/document_extraction.py` can call Tika first and fall back to Tesseract OCR when Tika returns no text

## Commands

Syntax-check the Tesseract OCR workflow:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make syntax-check-tesseract-ocr
```

Converge the private runtime directly:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make converge-tesseract-ocr env=production
```

Run the governed live-apply wrapper:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=tesseract-ocr env=production
```

## Verification

Verify the private Tesseract OCR health endpoint on `docker-runtime-lv3`:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
curl -fsS http://10.10.10.20:3008/healthz
```

Verify direct OCR extraction through the `/ocr` endpoint:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
curl -fsS -F 'file=@collections/ansible_collections/lv3/platform/roles/tesseract_ocr_runtime/files/ocr-ok.png;filename=ocr-ok.png;type=image/png' http://10.10.10.20:3008/ocr
```

Verify the Tika-first fallback helper chooses OCR when Tika returns no text:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
python3 scripts/document_extraction.py collections/ansible_collections/lv3/platform/roles/tesseract_ocr_runtime/files/ocr-ok.png --tika-url http://10.10.10.20:9998 --tesseract-url http://10.10.10.20:3008
```

## Operating Notes

- Tesseract OCR is intentionally private-only. Do not publish it on the public NGINX edge.
- The OCR runtime is stateless and should stay that way. Do not add persistent volumes or ad hoc secrets unless a future ADR changes that contract.
- `scripts/document_extraction.py` is the supported Tika-first helper path: call Tika for every upload, then fall back to OCR only when the extracted text is empty and the content type is image-like or PDF.
- OCR is CPU-bound. Large multi-page scanned PDFs should be queued or rate-limited instead of fired in unbounded parallel batches.
