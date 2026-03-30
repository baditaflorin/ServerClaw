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
cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/collections/ansible_collections/lv3/platform/roles/tesseract_ocr_runtime/files/ocr-ok.png | ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519   -o IdentitiesOnly=yes   -J ops@100.64.0.1   ops@10.10.10.20   'image=$(mktemp --suffix=.png); trap '''rm -f "$image"''' EXIT; cat >"$image";   curl -fsS -F "file=@${image};filename=ocr-ok.png;type=image/png" http://127.0.0.1:3008/ocr'
```

Run the governed live-apply wrapper:

```bash
cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/collections/ansible_collections/lv3/platform/roles/tesseract_ocr_runtime/files/ocr-ok.png | ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519   -o IdentitiesOnly=yes   -J ops@100.64.0.1   ops@10.10.10.20   'image=$(mktemp --suffix=.png); trap '''rm -f "$image"''' EXIT; cat >"$image";   python3 /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/document_extraction.py "$image" --tika-url http://127.0.0.1:9998 --tesseract-url http://127.0.0.1:3008'
```

## Verification

Verify the private Tesseract OCR health endpoint on `docker-runtime-lv3`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'curl -fsS http://127.0.0.1:3008/healthz'
```

Verify direct OCR extraction through the `/ocr` endpoint:

```bash
scp -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/collections/ansible_collections/lv3/platform/roles/tesseract_ocr_runtime/files/ocr-ok.png ops@10.10.10.20:/tmp/ocr-ok.png
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'curl -fsS -F "file=@/tmp/ocr-ok.png;filename=ocr-ok.png;type=image/png" http://127.0.0.1:3008/ocr && rm -f /tmp/ocr-ok.png'
```

Verify the Tika-first fallback helper chooses OCR when Tika returns no text:

```bash
scp -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/collections/ansible_collections/lv3/platform/roles/tesseract_ocr_runtime/files/ocr-ok.png ops@10.10.10.20:/tmp/ocr-ok.png
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'python3 /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/document_extraction.py /tmp/ocr-ok.png --tika-url http://127.0.0.1:9998 --tesseract-url http://127.0.0.1:3008 && rm -f /tmp/ocr-ok.png'
```

## Operating Notes

- Tesseract OCR is intentionally private-only. Do not publish it on the public NGINX edge.
- The OCR runtime is stateless and should stay that way. Do not add persistent volumes or ad hoc secrets unless a future ADR changes that contract.
- `scripts/document_extraction.py` is the supported Tika-first helper path: call Tika for every upload, then fall back to OCR only when the extracted text is empty and the content type is image-like or PDF.
- OCR is CPU-bound. Large multi-page scanned PDFs should be queued or rate-limited instead of fired in unbounded parallel batches.
