# ADR 0475: Workstream-Surfaces Validator Cleanup

- Status: Implemented
- Implementation Status: Complete (this release)
- Date: 2026-04-29
- Concern: gate-hygiene, workstream-registry, ci-cd
- Tags: workstream-surfaces, gate-cleanup, follow-up
- Reservation: res-0475-workstream-surfaces-cleanup
- Implements: ADR 0472/0473/0474 follow-up — eliminate the
  cross-deployment-drift gate bypass forced on phases 10/11/12.
- Depends on:
  - ADR 0326 — workstream registry shards
  - ADR 0444 — workstream surface ownership

## Context

Phases 10–12 each shipped under
`SKIP_REMOTE_GATE=1 GATE_BYPASS_REASON_CODE=cross_deployment_drift`
because the local pre-push gate's `workstream-surfaces` lane refused
the push on three pre-existing defects in the workstream registry:

1. `ws-0447-coolify-apps-self-healing` (active) had no `doc:` field
   and no `ownership_manifest`. The validator rejects active
   workstreams that lack either.
2. `ws-0452-workstream-lifecycle-auto-close` is an "umbrella for
   ADRs 0452/0453/0454" but claimed `docs/adr/0453-…md` and
   `docs/adr/0454-…md` as `mode: exclusive`. ws-0453 and ws-0454
   each independently claim their own ADR exclusively. Two
   workstreams cannot exclusively own the same path.
3. The same umbrella-vs-owner conflict applied to
   `receipts/audits/2026-04-28-gate-bypass-baseline.json`.

Each push therefore had to set `GATE_BYPASS_IMPACTED_LANES` to
include `workstream-surfaces`, which is operator overhead for a
class of fault that has nothing to do with the work being shipped.

## Decision

Two surgical edits:

### Phase 13.1 — populate `ws-0447`

Add `doc: docs/adr/0340-coolify-vm-separation.md` (the closest
existing ADR for this workstream's scope) and an
`ownership_manifest` claiming the two roles the workstream owns
(`coolify_runtime`, `coolify_app_deploy`) plus the workstream YAML
itself.

### Phase 13.2 — relax umbrella claims on `ws-0452`

Convert the three `mode: exclusive` claims that conflict with
sibling workstreams (`ws-0453`, `ws-0454`) into
`mode: shared_contract` with a `workstream-lifecycle-umbrella-v1`
contract id. Semantically: ws-0452 is the umbrella, ws-0453/ws-0454
are the owners; the umbrella shares the contract with the owners
rather than claiming exclusivity.

## Consequences

- `make doctor` and `validate_repo.sh workstream-surfaces` pass
  cleanly without bypass.
- Future pushes don't need `cross_deployment_drift` rationale on
  the workstream-surfaces lane.
- Cert-validation lane bypasses (the OTHER half of every Phase
  10/11/12 gate-bypass) are deferred until ADR 0414's
  `cert_lifecycle_manager.py sync-missing` runs from a session
  with operator network access to the lv3 / 0fork edge hosts.

## What this leaves open

- The pre-push gate still runs cert validation against live edges
  (`status.lv3.org`, `tasks.lv3.org`, etc). Until those certs are
  reissued, every push must continue to set `SKIP_CERT_VALIDATION=1`
  with a reason code. This is environmental drift, not a registry
  defect.
