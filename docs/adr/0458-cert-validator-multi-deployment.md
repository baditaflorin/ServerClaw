# ADR 0458: Cert-Validator Multi-Deployment Mode (Auto-Detect)

> **Superseded by [ADR 0488](0488-single-deployment-per-repo-checkout.md)** (2026-05-17). The multi-deployment substrate is retired; each repo checkout now configures exactly one deployment via `.local/identity.yml`.


- Status: Superseded by ADR 0488
- Implementation Status: Implemented (`--all-deployments` flag + auto-trigger when no slug resolved AND multiple deployments registered)
- Date: 2026-04-29
- Concern: multi-deployment-coverage, gate-completeness
- Tags: tls, multi-deployment, cert-validation
- Implements: follow-up #3 from the [ws-0448 postmortem](../postmortems/2026-04-28-ws-0448-deployment-connection-registry.md)
- Depends on:
  - ADR 0440 (Per-Deployment Identity & Artifact Isolation)
  - ADR 0456 (Deployment-Aware Certificate Validation)

---

## Context

[ADR 0456](0456-deployment-aware-certificate-validation.md) added `--deployment <slug>` to `scripts/certificate_validator.py` so a multi-deployment install can scope cert checks to a single deployment. That solved the cross-deployment drift problem for *one* deployment at a time.

The remaining gap: in a multi-deployment install, the validator only ever sees one deployment per invocation. The pre-push gate's all-lane runner picks one slug (whichever `.local/active-deployment` happens to be). The other deployment's certs are silently uninspected. An expired cert in deployment B doesn't appear in deployment A's gate output.

## Decision

Add multi-deployment mode to the validator:

1. **`--all-deployments` flag** — explicit operator invocation. Walks every slug under `.local/deployments/`, runs the per-deployment validation logic in turn, aggregates results, exits 1 if *any* deployment reports an expired or mismatched cert.

2. **Auto-trigger** — when the operator passes neither `--deployment` nor `--fqdn` AND `.local/deployments/` contains more than one slug, behave as if `--all-deployments` were passed. Single-deployment installs are unaffected (legacy fallback path still runs). When `.local/deployments/` is absent or contains exactly one slug, the legacy single-deployment path runs as before.

3. **Per-deployment skip** — if a deployment's `identity.yml` is missing or set to the `example.com` placeholder, the validator emits an `[info]` line and moves on instead of failing the whole run.

## Consequences

- A pre-push gate that runs `python3 scripts/certificate_validator.py --check-all` (no flag) on a multi-deployment install now covers every deployment. The previous behavior of "the gate validates whichever deployment happens to be active" is replaced with "the gate validates every registered deployment."
- An expired cert in any deployment fails the gate, which is the desired behavior — operators want to see expirations regardless of which slug is active.
- The operator can still scope to one deployment with `--deployment <slug>` (ADR 0456) or one FQDN with `--fqdn <fqdn>` (ADR 0375). The auto-trigger only kicks in when neither is specified.
- The `cross_deployment_drift` reason code (added by ADR 0456) and `cert_lane_pre_existing_failures` (added by ADR 0451) remain valid escape hatches for legitimate drift.

## Operational Notes

```bash
# Explicit multi-deployment mode (recommended in CI):
python3 scripts/certificate_validator.py --check-all --all-deployments

# Auto-trigger (operator-friendly default in multi-deployment installs):
python3 scripts/certificate_validator.py --check-all

# Single-deployment scoping unchanged:
python3 scripts/certificate_validator.py --check-all --deployment 0fork
```

## References

- [ADR 0375 — Certificate Validation & Concordance Enforcement](0375-certificate-validation-and-concordance-enforcement.md)
- [ADR 0440 — Per-Deployment Identity & Artifact Isolation](0440-per-deployment-identity-and-artifact-isolation.md)
- [ADR 0456 — Deployment-Aware Certificate Validation](0456-deployment-aware-certificate-validation.md)
- [2026-04-28 ws-0448 postmortem](../postmortems/2026-04-28-ws-0448-deployment-connection-registry.md) — open follow-up #3.
