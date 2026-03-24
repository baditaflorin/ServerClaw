# ADR 0134: Changelog Portal Content Redaction

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The deployment changelog portal (ADR 0081) renders live-apply receipts, version history, and mutation ledger (ADR 0115) summaries into a human-readable history of what changed and when. Even after adding Keycloak authentication (ADR 0133), the portal will be accessible to all authenticated operators.

The problem is that mutation ledger entries and live-apply receipts can contain:

- **Actor email addresses and usernames** from agent identities (e.g., `codex/adr-0113-workstream`) that could leak internal project structures or contractor names.
- **Ansible inventory hostnames and IP addresses** referenced in playbook output captured in receipts.
- **Workflow parameters** that may include service-specific configuration snippets, temporary credential references, or path structures.
- **Environment variable names** from Windmill job payloads that, while not containing values, reveal configuration key names.
- **Error messages** from failed executions that include stack traces with internal library paths, database connection strings (with redacted passwords but with usernames and hostnames), or API endpoint URLs.
- **Timing patterns** that reveal maintenance windows, deployment cadences, and scheduled task intervals — information useful for timing attacks.

These data classes are appropriate in the mutation ledger (a private, internal audit store) but are over-shared when displayed in any portal, even an authenticated-operator one. An operator account compromised through phishing, credential stuffing, or session hijacking becomes a full intelligence source.

The principle of least privilege applies to data display, not just access control: the portal should show operators what they need to understand the deployment history, not every field stored in the underlying event record.

## Decision

We will implement a **changelog portal redaction pipeline** — a processing layer between the raw ledger/receipt data and the portal renderer that strips or masks sensitive fields before rendering.

### Sensitive field taxonomy

Fields are classified into four redaction levels:

| Level | Fields | Portal treatment |
|---|---|---|
| `STRIP` | Stack traces, full error messages with paths, raw job payloads | Replaced with `[details omitted]` and a link to the operator-only raw log view |
| `MASK` | Actor email addresses (retain username prefix only), internal hostnames (retain service name, omit VM hostname suffix) | `ops@` → `ops`, `netbox-vm.lv3.internal` → `netbox` |
| `SUMMARISE` | Workflow parameters (show parameter names, not values) | `{db_password: [redacted], host: "netbox-vm"}` → `{2 params}` |
| `RETAIN` | Service name, workflow ID, event type, timestamp, duration, success/fail status | Shown as-is |

### Redaction configuration

```yaml
# config/changelog-redaction.yaml

rules:
  - field_pattern: "*.error_detail"
    level: STRIP

  - field_pattern: "*.stack_trace"
    level: STRIP

  - field_pattern: "*.job_payload"
    level: STRIP

  - field_pattern: "*.actor_email"
    level: MASK
    mask_fn: username_only       # keep left of @ sign

  - field_pattern: "*.vm_hostname"
    level: MASK
    mask_fn: service_name_only   # strip .lv3.internal suffix

  - field_pattern: "*.params"
    level: SUMMARISE
    summarise_fn: count_keys     # show "{N params}" instead of values

  - field_pattern: "*.env_vars"
    level: SUMMARISE
    summarise_fn: key_names_only  # show key names, not values

  # Retained verbatim
  - field_pattern: "*.workflow_id"
    level: RETAIN
  - field_pattern: "*.event_type"
    level: RETAIN
  - field_pattern: "*.service_id"
    level: RETAIN
  - field_pattern: "*.ts"
    level: RETAIN
  - field_pattern: "*.status"
    level: RETAIN
  - field_pattern: "*.duration_ms"
    level: RETAIN
```

### Raw view access

Operators with the `platform-admin` Keycloak role (ADR 0056) may access a `raw` view of any ledger entry by clicking "View raw" in the portal. The raw view is not subject to redaction rules. Access to the raw view is itself logged in the mutation ledger as a `portal.raw_view_accessed` event.

The raw view is served on a separate nginx location block (`/admin/raw/`) that requires the `platform-admin` role claim in the OIDC token, not just any authenticated operator session.

### Receipt file redaction

Live-apply receipts (`receipts/`) are committed to the repository. Since the repo may be shared more broadly than the portal, receipts must also pass through a pre-commit redaction step that removes `STRIP` and `MASK` fields from committed receipt files. The pre-commit hook (`scripts/redact_receipt.py`) runs on all files in `receipts/` matching `*.receipt.json`.

```bash
# .pre-commit-config.yaml addition
- repo: local
  hooks:
    - id: redact-receipts
      name: Redact live-apply receipts
      entry: python3 scripts/redact_receipt.py
      language: python
      files: ^receipts/.*\.receipt\.json$
      pass_filenames: true
```

### Ledger entries

Raw ledger entries in Postgres are never redacted — they are the authoritative audit record. Redaction occurs only in the read path: the portal renderer and the search fabric indexer (ADR 0121) both apply the redaction rules before displaying or indexing content.

The search fabric indexes the redacted view of receipts and ledger summaries. The unredacted content is not indexed and is not accessible via `lv3 search`.

## Consequences

**Positive**

- A compromised operator account exposes deployment history in summary form, not raw infrastructure data. The blast radius of a credential compromise is reduced.
- Receipt files committed to the repository (which may be in a semi-public git server) do not contain hostnames, stack traces, or parameter values.
- The `platform-admin` raw view preserves the full audit capability for incident investigation without exposing it to all operators by default.

**Negative / Trade-offs**

- The redaction layer adds processing overhead to every portal page render. For a deployment history with thousands of entries, this is measurable. Redacted views should be pre-computed and cached at indexer time rather than computed on request.
- Maintaining the redaction rules configuration requires careful thought: over-aggressive redaction (stripping the service name, for example) makes the changelog useless. Under-aggressive redaction (not stripping stack traces) reintroduces the exposure. The rules must be reviewed periodically.
- Operators accustomed to seeing full details in the portal will need to use the raw view for debugging. The raw view access is logged, which is correct, but introduces friction for legitimate debugging workflows.

## Boundaries

- Redaction applies to the portal render path and the search indexer. The Postgres ledger tables and receipt files pre-commit store unredacted data.
- This ADR covers text-field redaction. It does not cover binary artifacts, container image digests, or Packer build logs.
- The redaction rules in `config/changelog-redaction.yaml` are a configuration file subject to the validation pipeline (ADR 0031). Weakening redaction rules requires a pull request.

## Related ADRs

- ADR 0031: Repository validation pipeline (redaction config validated here)
- ADR 0036: Live-apply receipts (receipt files subject to pre-commit redaction)
- ADR 0056: Keycloak SSO (platform-admin role for raw view access)
- ADR 0081: Deployment changelog portal (portal that applies redaction)
- ADR 0115: Event-sourced mutation ledger (source of unredacted data; never modified)
- ADR 0121: Local search and indexing fabric (indexes redacted views only)
- ADR 0133: Portal authentication by default (access control; this ADR covers content redaction)
- ADR 0138: Published artifact secret scanning (companion pre-publish check)
