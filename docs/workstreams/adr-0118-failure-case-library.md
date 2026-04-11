# Workstream ADR 0118: Replayable Failure Case Library

- ADR: [ADR 0118](../adr/0118-replayable-failure-case-library.md)
- Title: Structured Postgres case store for past failures with symptoms, root cause, remediation, and replay linkage — BM25 + signal-overlap retrieval surfaces similar cases in every triage report
- Status: ready
- Branch: `codex/adr-0118-failure-case-library`
- Worktree: `../proxmox-host_server-failure-case-library`
- Owner: codex
- Depends On: `adr-0057-mattermost-chatops`, `adr-0061-glitchtip`, `adr-0092-platform-api-gateway`, `adr-0093-interactive-ops-portal`, `adr-0098-postgres-ha`, `adr-0114-incident-triage-engine`, `adr-0115-mutation-ledger`
- Conflicts With: none
- Shared Surfaces: `platform/cases/`, `cases.failure_cases` Postgres schema, `/v1/cases/*` API gateway endpoints, `config/case-root-cause-categories.yaml`

## Scope

- create Postgres migration `migrations/0013_cases_schema.sql` — `cases.failure_cases` table with tsvector generated column, GIN FTS index, trigram index, and all other indexes from ADR 0118
- create `config/case-root-cause-categories.yaml` — controlled vocabulary from ADR 0118
- create `platform/cases/__init__.py`
- create `platform/cases/store.py` — `CaseStore.create()`, `CaseStore.update()`, `CaseStore.close()`, `CaseStore.search()`, `CaseStore.get_similar()` methods
- create `platform/cases/retrieval.py` — `CaseRetriever.find_similar()`: BM25 query + signal overlap scoring; returns top-3 with composite score
- create `windmill/cases/auto-create-case.py` — Windmill workflow subscribed to GlitchTip incident-opened events; creates a skeleton case record
- create `windmill/cases/audit-case-quality.py` — weekly workflow: flags unresolved cases, re-runs verification commands, archives stale open cases
- register `/v1/cases/*` routes on the platform API gateway (ADR 0092): `GET /v1/cases`, `GET /v1/cases/{id}`, `POST /v1/cases`, `PATCH /v1/cases/{id}`, `GET /v1/cases/search?q=`
- update triage engine (ADR 0114) `run-triage.py` — add `similar_cases` block to triage report by calling `CaseRetriever.find_similar()` on the assembled signal set
- add case management UI to ops portal (ADR 0093): case list, case detail, close-case form
- write `tests/unit/test_case_retrieval.py` — BM25 query tests, signal overlap scoring tests, empty-library edge case

## Non-Goals

- Automated root cause determination — root cause is always written by a human operator
- Storing full log dumps in cases — `ledger_event_ids` links to the ledger; the case itself stores summaries only

## Expected Repo Surfaces

- `migrations/0013_cases_schema.sql`
- `config/case-root-cause-categories.yaml`
- `platform/cases/__init__.py`
- `platform/cases/store.py`
- `platform/cases/retrieval.py`
- `windmill/cases/auto-create-case.py`
- `windmill/cases/audit-case-quality.py`
- `docs/adr/0118-replayable-failure-case-library.md`
- `docs/workstreams/adr-0118-failure-case-library.md`

## Expected Live Surfaces

- `cases.failure_cases` table exists with GIN and trigram indexes
- Triggering a GlitchTip incident (via test alert) automatically creates a skeleton case within 60 seconds
- `GET /v1/cases/search?q=connection+pool` returns any relevant cases
- The ops portal case list page at `/cases` renders without errors
- A triage report fired after at least one resolved case exists includes a `similar_cases` section

## Verification

- Run `pytest tests/unit/test_case_retrieval.py -v` → all passes including empty-library edge case
- Create a test case manually via `POST /v1/cases`; close it with a root cause; then fire a new triage for the same service and verify `similar_cases` returns the closed case
- Run the weekly audit workflow manually → confirm it flags any open cases older than 90 days and posts the summary to Mattermost

## Merge Criteria

- Unit tests pass
- Automatic case creation from GlitchTip verified end-to-end
- At least 3 real resolved cases exist in the library (created during platform operation, not test fixtures)
- `similar_cases` integration with triage engine verified
- Case management UI reachable in the ops portal

## Notes For The Next Assistant

- The `verification_command` re-execution in the audit workflow should run on the controller (not inside Windmill's execution environment) since it may use `lv3` CLI commands; use the platform API gateway's `/v1/platform/exec` endpoint if available, or skip re-execution for the first release and just flag the case for operator review
- The signal overlap score is not cosine similarity; it is a simple count of signals that appear in both the current incident and the case, weighted by signal importance. Do not implement vector arithmetic here; it is not needed.
- `CaseStore.close()` must require `root_cause` to be non-null and non-empty before setting `status: resolved`. Enforce this in application code, not just at the DB constraint level, so the error message is operator-friendly.
- The GlitchTip webhook for `incident.opened` events must be registered in the Windmill workflow resource configuration, not hardcoded; use the `platform/secrets` OpenBao path for the webhook secret.
