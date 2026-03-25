# Deployment History Portal

## Purpose

The deployment history portal is a generated static site under `build/changelog-portal/`.

It gives operators and agents one place to answer:

- what changed on the platform and when
- which services were affected
- whether a change came from a live apply, a promotion, or a mutation audit event
- which receipt or evidence file backs the entry

## Generation

Generate the portal locally:

```bash
make generate-changelog-portal
```

This renders:

- `build/changelog-portal/index.html`
- `build/changelog-portal/services/index.html`
- `build/changelog-portal/service/<service-id>/index.html`
- `build/changelog-portal/environment/production/index.html`
- `build/changelog-portal/environment/staging/index.html`
- `build/changelog-portal/promotions/index.html`

The generator reads:

- `receipts/live-applies/**/*.json`
- `receipts/promotions/**/*.json`
- `config/service-capability-catalog.json`
- `config/changelog-redaction.yaml`
- mutation audit events from Loki when configured, or an optional local JSONL file

## Redaction Boundary

Portal output and the governed `get-deployment-history` read surface pass through the changelog redaction policy in `config/changelog-redaction.yaml`.

The redacted view keeps timestamps, service names, workflow IDs, and outcomes, but masks or strips:

- actor emails and branch-like agent identifiers
- private IPs and internal hostnames such as `*-lv3`, `*-vm`, and `*.lv3.internal`
- inline credential material such as `password=...`, `token=...`, bearer tokens, and OpenBao tokens
- mutation-audit `params`, `env_vars`, `error_detail`, `stack_trace`, and `job_payload` fields

If the portal shows `[details omitted]` or `[redacted]`, inspect the authoritative receipt or audit source directly instead of weakening the shared read model.

## Audit Source

The generator prefers Loki for mutation audit events. It queries the last 90 days by default and falls back gracefully when Loki is unavailable.

Optional overrides:

```bash
LV3_MUTATION_AUDIT_LOKI_QUERY_URL=http://10.10.10.40:3100/loki/api/v1/query_range \
  uv run --with pyyaml --with jsonschema python scripts/generate_changelog_portal.py --write
```

For deterministic local or CI validation, use a local JSONL file instead:

```bash
uv run --with pyyaml --with jsonschema python scripts/generate_changelog_portal.py \
  --mutation-audit-file tests/fixtures/mutation_audit_history.jsonl \
  --write
```

When mutation audit events are unavailable, the portal renders a visible fallback banner and still shows the receipt-backed timeline.

## Validation

Run:

```bash
make validate-generated-portals
```

or directly:

```bash
uv run --with pyyaml --with jsonschema python scripts/generate_changelog_portal.py --check
```

## Live Verification

After publishing through the shared edge:

```bash
curl -Ik https://changelog.lv3.org/
```

Expected result: `HTTP/2 302` to `/oauth2/sign_in` for an unauthenticated request.

## Deployment Boundary

This workstream implements the generated site, the governed history query tool, and edge publication wiring for `changelog.lv3.org`.

`changelog.lv3.org` is live on platform version `0.40.0`; from platform version `0.114.7` onward it is also protected by the shared Keycloak portal auth gate defined in ADR 0133.
