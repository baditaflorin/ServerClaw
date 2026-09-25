# WS-0500: HTTPS alert runtime-output gate

## Decision

The HTTPS/TLS target and alert files are intentionally ignored runtime outputs
because they resolve deployment-local identity. A clean source checkout has
neither file, so the repository gate accepts that state. Once either output is
present, the generator comparison remains strict and rejects missing or stale
companion output.

## Scope

- Add a `--check-if-present` generator mode.
- Use that mode only in the alert-rule validation path.
- Cover clean absence and present drift with focused tests.

No output is force-added, no generator source catalog is changed, and no live
configuration is applied.
