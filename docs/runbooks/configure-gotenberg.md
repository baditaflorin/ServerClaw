# Configure Gotenberg

## Purpose

This runbook converges ADR 0278 so document-producing workflows have a shared,
private HTML, Markdown, text, and Office-to-PDF rendering service on
`docker-runtime-lv3`.

## Result

- `docker-runtime-lv3` runs the stateless Gotenberg runtime from `/opt/gotenberg`
- the private runtime listens on `10.10.10.20:3007` for guest-network callers
- the shared API gateway refreshes `/v1/gotenberg` on `https://api.lv3.org` for authenticated operator and automation access
- Chromium and LibreOffice conversion routes are verified with repo-managed checks

## Commands

Syntax-check the Gotenberg workflow:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make syntax-check-gotenberg
```

Converge the private runtime and refresh the API gateway bundle:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make converge-gotenberg
```

Refresh the generated platform vars after topology or port changes:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
uv run --with pyyaml python scripts/generate_platform_vars.py --write
```

## Verification

Verify the local health endpoint on `docker-runtime-lv3`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'curl -fsS http://127.0.0.1:3007/health'
```

Verify the Chromium HTML route returns a PDF:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'html=$(mktemp --suffix=.html); pdf=$(mktemp); trap '\''rm -f "$html" "$pdf"'\'' EXIT; printf "<html><body><h1>LV3 Gotenberg runbook</h1></body></html>" >"$html"; curl -fsS -o "$pdf" -F "files=@${html};filename=index.html;type=text/html" http://127.0.0.1:3007/forms/chromium/convert/html; head -c 4 "$pdf"'
```

Verify the LibreOffice route returns a PDF from a text document:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'txt=$(mktemp --suffix=.txt); pdf=$(mktemp); trap '\''rm -f "$txt" "$pdf"'\'' EXIT; printf "LV3 Gotenberg runbook\n" >"$txt"; curl -fsS -o "$pdf" -F "files=@${txt};filename=runbook.txt;type=text/plain" http://127.0.0.1:3007/forms/libreoffice/convert; head -c 4 "$pdf"'
```

Verify the authenticated API gateway route proxies the health endpoint:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
LV3_TOKEN="$(cat .local/platform-context/api-token.txt)"
curl -fsS -H "Authorization: Bearer $LV3_TOKEN" https://api.lv3.org/v1/gotenberg/health
```

Verify the authenticated API gateway route proxies a Chromium render request:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
LV3_TOKEN="$(cat .local/platform-context/api-token.txt)"
html="$(mktemp --suffix=.html)"
pdf="$(mktemp)"
trap 'rm -f "$html" "$pdf"' EXIT
printf '<html><body><h1>LV3 Gateway Render Check</h1></body></html>' >"$html"
curl -fsS -o "$pdf" \
  -H "Authorization: Bearer $LV3_TOKEN" \
  -F "files=@${html};filename=index.html;type=text/html" \
  https://api.lv3.org/v1/gotenberg/forms/chromium/convert/html
head -c 4 "$pdf"
```

## Operating Notes

- Gotenberg is intentionally stateless. Do not add local volumes, persistent scratch storage, or ad hoc secrets unless a future ADR changes that contract.
- Keep direct access private to the guest network. The governed shared API route is the only supported authenticated access path outside that private boundary.
- Caller workflows own persistence. Store rendered PDFs in MinIO or another system of record after each successful conversion instead of treating Gotenberg as a file store.
- The readiness probe intentionally exercises a real render path so we catch broken Chromium or LibreOffice startup, not only the shallow `/health` endpoint.
