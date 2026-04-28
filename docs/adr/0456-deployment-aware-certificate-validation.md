# ADR 0456: Deployment-Aware Certificate Validation

- Status: Accepted
- Implementation Status: Implemented (`--deployment` flag on certificate validator + `cross_deployment_drift` reason code)
- Date: 2026-04-28
- Concern: multi-deployment-correctness, gate-noise
- Tags: tls, multi-deployment, cert-validation, gate-bypass
- Implements: follow-up #2 from [ws-0448 postmortem](../postmortems/2026-04-28-ws-0448-deployment-connection-registry.md)
- Depends on: ADR 0375, ADR 0410 Phase 4a, ADR 0440, ADR 0448

---

## Context

`scripts/certificate_validator.py` (ADR 0375) reads `platform_domain` from a
single shared overlay path: `.local/identity.yml`. In a multi-deployment world
(ADR 0440), each deployment carries its own identity at
`.local/deployments/<slug>/identity.yml`. The legacy single-overlay path is
either stale (ops.0fork.com recovery left `.local/identity.yml` saying
`lv3.org` while the active host serves 0fork.com) or a forced choice.

Result: 44 spurious `cert_mismatch` failures on every push between
2026-04-28 11:00 UTC and 16:00 UTC. The hook printed
`Bypass: SKIP_CERT_VALIDATION=1` as remediation, but the
gate-bypass-waiver-catalog had no reason code that allowed the
`skip_cert_validation` bypass — every reason code only allowed
`skip_remote_gate`. The advertised escape hatch was unreachable.

(ADR 0451 added a `cert_lane_pre_existing_failures` reason after this
postmortem was written; ADR 0456 is the orthogonal scoping fix that
eliminates the *category* of failure rather than just bypassing it.)

## Decision

### 1. `--deployment <slug>` on the cert validator

When passed, the validator reads `platform_domain` from
`.local/deployments/<slug>/identity.yml` and only checks FQDNs that match.
Cross-deployment domains in the catalog are filtered before any TCP
connection attempt; they never produce a `cert_mismatch` for the deployment
under test.

When the flag is absent, resolve the active slug from (in order):
`$DEPLOYMENT` env var, `.local/active-deployment` file, then fall back to
legacy `.local/identity.yml` for backward compatibility. Single-deployment
installations are byte-identical to pre-ADR-0456 behavior.

### 2. `cross_deployment_drift` reason code

`config/gate-bypass-waiver-catalog.json` gains a new entry:

```json
"cross_deployment_drift": {
  "summary": "A multi-deployment platform host (ADR 0440) is now serving a different deployment than the cert catalog was generated for; ...",
  "max_expiry_days": 2,
  "allowed_bypasses": ["skip_cert_validation", "skip_remote_gate"]
}
```

Composes with `cert_lane_pre_existing_failures` (added by ADR 0451) by
documenting the multi-deployment hostname-mapping class of drift specifically.
2-day max expiry forces operators to either fix the host's deployment
registration or apply the `--deployment` scoping on the next push.

## Consequences

- Pushes from a worktree where the active deployment is set correctly
  (`.local/active-deployment` or `$DEPLOYMENT`) no longer produce spurious
  `cert_mismatch` failures for sibling deployments.
- Single-deployment installations are unaffected.
- The validator's behavior is now load-bearing on the
  `.local/active-deployment` file being correct.

## Operational Notes

```bash
# Validate a specific deployment regardless of active state:
python3 scripts/certificate_validator.py --check-all --deployment 0fork

# When you legitimately can't fix the drift before pushing:
SKIP_CERT_VALIDATION=1 \
GATE_BYPASS_REASON_CODE=cross_deployment_drift \
GATE_BYPASS_DETAIL="<which deployment is on the host>" \
GATE_BYPASS_REMEDIATION_REF="docs/adr/0456-deployment-aware-certificate-validation.md" \
GATE_BYPASS_SUBSTITUTE_EVIDENCE="<path>" \
git push origin <branch>
```

## References

- [ADR 0375 — Certificate Validation & Concordance Enforcement](0375-certificate-validation-and-concordance-enforcement.md)
- [ADR 0440 — Per-Deployment Identity & Artifact Isolation](0440-per-deployment-identity-and-artifact-isolation.md)
- [ADR 0448 — Per-Deployment Connection Registry](0448-deployment-connection-registry-and-wrapper.md)
- [ADR 0451 — Phase 6 Self-Healing Actions](0451-phase6-self-healing-actions.md) — adds `cert_lane_pre_existing_failures`
- [2026-04-28 ws-0448 postmortem](../postmortems/2026-04-28-ws-0448-deployment-connection-registry.md) — open follow-up #2.
