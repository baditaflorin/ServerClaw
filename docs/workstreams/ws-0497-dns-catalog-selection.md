# WS-0497: Selected DNS catalog comparison

## Goal

Eliminate false DNS catalog drift warnings when a guarded deployment preflight
uses an explicit non-generic identity overlay.

## Scope

- Resolve the generic `example.com` catalog hostnames in memory using the
  identity file explicitly selected for the generation run.
- Keep `config/subdomain-catalog.json` generic and unmodified.
- Prove the 0mcp DNS declarations compare cleanly against the selected catalog.
- Refresh generated status artifacts that became stale when rebasing onto the
  current `main` branch.

## Boundary

This changes validation and generation comparison only. It does not create,
delete, or modify DNS records, certificates, NGINX routes, or live services.

## Result

The selected 0mcp identity now resolves the generic subdomain catalog only in
memory before DNS comparison, eliminating the false missing-record warnings
without changing `config/subdomain-catalog.json`. The focused generator suite
also contained one stale expectation for the retired `sso.example.com`
Keycloak hairpin; it now asserts only the active Authentik routes.

The branch was refreshed onto current `main`; this also regenerated the
canonical README summary, merged-workstream history, and platform manifest so
the fresh-main validation gate checks current repository truth.

After PR #221 merged, this workstream was marked `merged` and its patch note
was queued under `Unreleased`. Cutting the repository version remains pending
the release manager's existing repository-wide blockers; `platform_version`
is unchanged because this workstream made no live infrastructure change.

All four guarded production selectors (Authentik, GlitchTip, Outline, and
OpenBao) pass with the explicit 0mcp identity and topology inputs. The
remaining catalog-only advisory routes belong to infrastructure services that
are intentionally outside `platform_service_registry`; this workstream does
not alter their DNS or exposure state.

The full gate's HTTPS/TLS alert check was rerun through its canonical command
after the initial report and passed without any generated-file delta.
