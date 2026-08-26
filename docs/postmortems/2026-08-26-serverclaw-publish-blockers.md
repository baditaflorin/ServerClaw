# 2026-08-26: ServerClaw publish blocked on two unrelated stale-state issues

## Context

A routine `make publish-serverclaw-push` (after merging ADR 0489's firewall
provenance/drift-detection work) surfaced a pre-existing sanitization
coverage gap, and the fix for that in turn ran into a pre-existing,
unrelated certificate-validation failure on push. Neither issue was
introduced by the change being published; both were latent drift the
respective gates correctly caught.

## Issue 1: sanitization coverage gap (example.org)

`scripts/audit_sanitization_coverage.py` found 3 CRITICAL gaps: the
`example.org` domain and two PII strings from an old identity overlay
were never added to `config/publication-sanitization.yaml`'s Tier C
rules, meaning `docs/adr/0424` and several workstream files carrying the
real domain, operator PII, the real public IP/IPv6, Hetzner DNS zone ID,
and Hetzner server order number would have leaked to the public
ServerClaw repo on next publish.

Fix: added Tier C `string_replacements` + `leak_markers` for all of the
above, mirroring the existing `example.com`/prod treatment.

## Issue 2: changelog/docs/headscale cert_mismatch

The pre-push cert validation gate (ADR 0375) flagged
`changelog.example.com`, `docs.example.com`, `headscale.example.com` as
`cert_mismatch`. Root cause was two-fold:

1. **Live**: `certbot-dns-hetzner` was missing entirely on the
   nginx-edge host, and `/etc/letsencrypt/hetzner.ini` held a token from
   before the `dns.hetzner.com` → `api.hetzner.cloud` migration (that
   old API is now fully retired — it 301-redirects to a login page).
   Fixed live: plugin installed, credentials corrected to a
   project-scoped Hetzner Cloud API token, `0mcp-edge` and
   `apps.example.org` certs renewed (`0mcp-edge` had ~5 hours left at time
   of fix).
2. **Declared**: `config/certificate-catalog.json` still listed these
   three services under their pre-rename `.example.com` names and the old
   `lv3-edge` bundle path, even though the live nginx vhosts have used
   `changelog.example.org` / `docs.example.org` / `headscale.example.org` and the
   `0mcp-edge` bundle for some time. The gate was correctly detecting
   real drift between declared and live state — the declared state was
   just stale. Fixed: updated the three catalog entries to match live
   reality.

## Follow-ups (not done here, out of scope for this fix)

- `.local/hetzner/dns.env`'s documented token was *also* stale (resolved
  to an unrelated Hetzner Cloud project) — corrected locally, not
  committed since `.local/` is gitignored.
- The broader `config/certificate-catalog.json` has 50 other entries
  sharing the same stale `lv3-edge` bundle path; only the 3 that were
  actively failing validation were corrected here. Worth a dedicated
  audit pass rather than a blind bulk find-replace, since some services
  may have their own dedicated cert bundles (as `apps.example.org` does)
  rather than the shared wildcard.
- A `0mpc.com` domain (transposed from `example.org`) has ~25 certificates,
  all already expired or failing renewal, mirroring `example.org`'s entire
  subdomain structure. Not investigated — unclear if it's active,
  abandoned, or a historical typo artifact.
