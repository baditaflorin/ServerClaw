# ADR 0467: Pre-Converge Live State Check (DNS + Cert SAN)

- Status: Accepted
- Implementation Status: Implemented (`scripts/preconverge_live_check.py`)
- Date: 2026-04-29
- Concern: shift-left, pre-converge-feedback
- Tags: dns, cert, pre-converge, live-state
- Implements: improvement #5 from the 2026-04-29 reliability review
- Depends on: ADR 0463 (post-converge health probes)

---

## Context

The pre-push gate validates committed state but cannot see live drift: DNS records pointed at the wrong IP, certs whose SANs don't cover the FQDN, hosts not actually reachable. The 2026-04-28 ops.0fork.com 500 incident is the canonical case — the operator only learned the cert mismatch existed when nginx returned 500 to the browser.

`scripts/converge_dry_run.py` (ws-0445) gives `ansible-playbook --check --diff` coverage but not live-state coverage.

## Decision

`scripts/preconverge_live_check.py`:

- Reads `catalog/services/<svc>/service.yaml::service.subdomain` for each requested service.
- DNS check: `socket.gethostbyname(fqdn)`; when `--expected-ip` is set, asserts membership.
- Cert SAN check: TLS handshake to port 443, parse SANs (uses `cryptography` if installed for DER parsing fallback), confirm SAN list covers the FQDN per RFC 6125 (exact match or single-label wildcard).
- Skips silently when a service has no public subdomain.
- Exit codes: `0` all OK, `1` any drift, `2` usage / data error.

CLI:

```bash
python3 scripts/preconverge_live_check.py --service ops_portal
python3 scripts/preconverge_live_check.py --all --expected-ip 65.109.84.223 --json
```

## Consequences

- Operators get a "is the cert + DNS state right?" answer in seconds, before kicking off a converge that takes 5+ minutes.
- Composes with ADR 0463 (post-converge probes) — same catalog input, same skip-when-absent semantics.

## References

- [ADR 0463 — Health-Probe Runner](0463-post-converge-health-probe.md)
- ws-0445 `scripts/converge_dry_run.py` — the static-state half of pre-converge feedback.
