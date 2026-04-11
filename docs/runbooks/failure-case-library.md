# Failure Case Library — Operator Runbook

**ADR reference:** ADR 0118 — Replayable Failure Case Library

## Purpose

The failure case library captures the full narrative of past incidents in a
structured, retrievable format.  Unlike the triage engine's rule table (ADR
0114), which fires on current signals, the case library is queried *after*
initial triage to surface the closest historical match for operator guidance.

Retrieval is symbolic and lexical (BM25 + signal overlap).  No embeddings,
no vector database, no LLM in the retrieval path.

---

## Repo Surfaces

| Path | Role |
|------|------|
| `config/case-root-cause-categories.yaml` | Controlled vocabulary for `root_cause_category` |
| `migrations/0018_cases_schema.sql` | Postgres schema (apply once per environment) |
| `scripts/cases/store.py` | JSON-backed case store (local dev and Windmill workers) |
| `scripts/cases/retrieval.py` | BM25 + signal-overlap retrieval engine |
| `config/windmill/scripts/auto-create-case.py` | Windmill: skeleton case creation from an incident payload |
| `config/windmill/scripts/audit-case-quality.py` | Windmill: weekly quality audit |

Local development and Windmill workers persist cases under:
`.local/state/cases/failure_cases.json`

---

## Case Lifecycle

```
open  →  resolved  →  (archived after 90 days if not closed)
open  →  archived  (automatic via quality audit)
```

Closing a case requires:
- `root_cause` — one or two sentences
- `root_cause_category` — from the controlled vocabulary
- at least one `remediation_step`
- `verification_command` — strongly encouraged; re-executed during quality audit

---

## CLI Operations

### Create a case manually

```bash
python3 scripts/lv3_cli.py cases create \
  --title "NetBox health probe failed after deploy" \
  --service netbox \
  --symptom "HTTP 502 from /health" \
  --symptom "Container restart loop in portainer"
```

### Search for similar cases

```bash
python3 scripts/lv3_cli.py cases search "connection pool exhausted" --service netbox
```

### List open cases

```bash
python3 scripts/lv3_cli.py cases list --status open
```

### Close a case

```bash
python3 scripts/lv3_cli.py cases close <case-id> \
  --root-cause "A bad deploy shipped an invalid database DSN." \
  --category deployment_regression \
  --step "Rolled back the release" \
  --step "Re-ran the smoke check" \
  --verify "python3 scripts/lv3_cli.py status netbox"
```

### Replay the linked mutation timeline

```bash
python3 scripts/lv3_cli.py cases replay <case-id>
```

Replay reads from `.local/state/mutation-audit/mutation-audit.jsonl` and
correlates events by `case_id`, `incident_id`, `triage_report_id`, and any
`ledger_event_ids` stored on the case.

---

## Windmill Workflows

### Auto-create a skeleton case from an incident payload

Called automatically when GlitchTip (ADR 0061) opens an incident.  Can also
be triggered manually for incidents discovered outside the automated path.

```bash
python3 config/windmill/scripts/auto-create-case.py \
  --repo-path /srv/proxmox-host_server \
  --payload-file /tmp/incident.json
```

Example `incident.json`:

```json
{
  "affected_service": "netbox",
  "title": "NetBox health probe failed",
  "symptoms": ["HTTP 502 from /health"],
  "correlated_signals": {
    "error_rate": 1.0,
    "health_probe_ok": false
  },
  "first_observed_at": "2026-04-08T14:00:00Z"
}
```

### Run the weekly quality audit

```bash
python3 config/windmill/scripts/audit-case-quality.py \
  --repo-path /srv/proxmox-host_server
```

Add `--verify-commands` only when the controller can safely execute the stored
`verification_command` values against the live platform.

Post the summary to Mattermost:

```bash
python3 config/windmill/scripts/audit-case-quality.py \
  --repo-path /srv/proxmox-host_server \
  --mattermost-webhook-url https://mattermost.example.com/hooks/xxx
```

---

## Postgres Schema

Apply the migration once on each environment that runs the live platform:

```bash
psql -h 10.10.10.60 -U platform -d platform \
  -f migrations/0018_cases_schema.sql
```

The migration is idempotent (`IF NOT EXISTS` throughout).

---

## Root Cause Category Vocabulary

Defined in `config/case-root-cause-categories.yaml`.  Do not add categories
ad-hoc — open a PR to update the YAML and let the PR review serve as the
governance gate.

| Category | Meaning |
|----------|---------|
| `deployment_regression` | A deployment introduced the failure |
| `resource_exhaustion` | CPU, memory, disk, or connection pool saturation |
| `certificate_expiry` | TLS certificate expired or near-expired |
| `configuration_drift` | Live config diverged from repo state |
| `dependency_failure` | Upstream service failed first |
| `network_partition` | Connectivity loss between components |
| `data_corruption` | Database or file state corruption |
| `operator_error` | Manual action caused the failure |
| `external_dependency` | Failure in a service outside the platform |
| `unknown` | Root cause could not be determined |

---

## Quality Audit Enforcement

The weekly Windmill audit (schedule: every Monday 06:00 UTC) checks:

1. **Resolved cases with no `root_cause`** — flagged and posted to Mattermost.
2. **`verification_command` re-execution** — failures indicate the fix may have
   regressed (run with `--verify-commands` on the audit schedule).
3. **Stale open cases** — open cases older than 90 days are automatically moved
   to `archived` with an annotation.

---

## Operational Notes

- The JSON store under `.local/state/cases/` is the source of truth for local
  development and Windmill.  The Postgres schema (`migrations/0018_cases_schema.sql`)
  is the intended live target once the database-backed runtime is wired.
- Replays use the mutation-audit sink at `.local/state/mutation-audit/mutation-audit.jsonl`
  until ADR 0115 is live.
- The `similar_cases` key in triage reports (ADR 0114) is populated by
  `CaseStore.get_similar()` using the BM25 + signal-overlap retriever.
- Never store PII, customer data, or secrets in case fields.
