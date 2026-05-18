# Postmortem: Service Inventory Gap — Multi-Deployment Discovery

**Status:** Open. Root cause identified. Remediation proposed.
**Severity:** Low (operational friction; no outage).
**Author:** claude
**Related:** ADR 0424, ADR 0437, ADR 0444, ADR 0480, `config/subdomain-exposure-registry.json`.

---

## Summary

When asked "what services are running on both 0fork.com and example.com?" there was
no single command, file, or script that could answer it. The authoritative
service registry — `config/subdomain-exposure-registry.json` — is baked from
the example.com identity and contains no entries for 0fork.com. Answering the
question required cross-referencing three separate files, knowing that 0fork.com
is a topology-identical clone of example.com (ADR 0424), and inferring that every
example.com service maps 1:1 to the same subdomain prefix on 0fork.com.

This is exactly the kind of query that agents and operators should be able to
answer in one command. They cannot.

---

## Timeline

- **2026-04-21** — ADR 0424 forks example.com onto Hetzner AX41-NVMe under 0fork.com.
  Service topology is copied; no corresponding registry entry is created for
  the new deployment.
- **2026-04-28** — ADR 0480 (multi-deployment certificate validation) begins.
  `config/certificate-catalog.json` gains 0fork.com certificate definitions.
  The subdomain-exposure-registry is *not* updated to include 0fork.com
  publications.
- **2026-05-11** — Operator asks for a side-by-side service list across both
  domains. No single artifact exists. Agent must grep five files to reconstruct
  the answer.

---

## What Happened

The subdomain-exposure-registry schema has a `zone_name` field at the top level.
When the registry was designed, a single deployment was assumed. Adding 0fork.com
as a fork exposed the assumption: the registry generator (`platform_manifest.py`)
and the exposure registry do not accept a `--deployment` or `--identity-overlay`
argument. They bake `example.com` into the output unconditionally.

Three specific gaps compounded:

### Gap 1 — `subdomain-exposure-registry.json` is single-zone

```json
{
  "schema_version": "2.0.0",
  "zone_name": "localhost",
  "publications": [...]
}
```

`zone_name` is a placeholder (`localhost`). Every `fqdn` in `publications` is
hardcoded to `*.example.com` and `*.staging.example.com`. There is no mechanism to
generate or query a parallel registry for `0fork.com`.

### Gap 2 — `platform_manifest.py` has no deployment selector

`scripts/platform_manifest.py --write` regenerates `build/platform-manifest.json`
from the example.com identity. It has no `--identity-overlay` or `--deployment` flag.
A 0fork.com manifest would require a separate script invocation or a fork of the
script. Neither exists.

### Gap 3 — 0fork.com service state is undocumented in IaC

The fork workstream (ws-0424) records that a full converge was run and services
were deployed. But neither the workstream YAML nor any other committed artifact
records *which* services are actually running on 0fork.com (some were disabled
in `fork-overrides.yml`: glitchtip OIDC, mail submission recovery). Consumers
cannot tell which example.com services were skipped or configured differently on
0fork.com.

---

## Impact

- **Operational friction.** Operators cannot audit "is 0fork.com running service X?"
  without SSH access or memory of the fork converge output.
- **Agent context cost.** An agent asked about cross-deployment service parity must
  read ~5 files and reason about identity overlays to reconstruct a list that should
  be a one-liner.
- **Drift risk.** If 0fork.com diverges (a service enabled on example.com but not yet
  converged on 0fork.com), there is no automated detection. No diff is possible
  when there is no 0fork.com inventory artifact.

---

## Root Cause

The exposure registry and platform manifest were designed for a single-deployment
world. ADR 0407 ("generic by default") and ADR 0424 (0fork.com clone) assumed
that multi-deployment support would be added later. It was not. The fork was
deployed successfully but its service inventory was never persisted in any
machine-readable form.

---

## What a Programmatic Solution Looks Like

### Option A — Multi-deployment exposure registry (recommended)

Extend the registry format to support multiple deployments:

```json
{
  "schema_version": "3.0.0",
  "deployments": {
    "example.com": {
      "platform_domain": "example.com",
      "environment": "production",
      "publications": [...]
    },
    "0fork.com": {
      "platform_domain": "0fork.com",
      "environment": "production",
      "overrides": ["keycloak_glitchtip_enabled=false"],
      "publications": [...]
    }
  }
}
```

The generator would accept `--write-deployment example.com` and `--write-deployment 0fork.com`
and merge results. A query script would answer:

```bash
python3 scripts/list_services.py --deployment 0fork.com --status active
python3 scripts/list_services.py --diff example.com 0fork.com   # services in one but not the other
```

### Option B — Per-deployment manifests generated from identity overlays

Extend `platform_manifest.py` with `--identity-overlay`:

```bash
# Current (example.com only):
python scripts/platform_manifest.py --write

# Proposed (per-deployment):
python scripts/platform_manifest.py --identity-overlay .local/identity.yml.0fork \
  --out build/platform-manifest-0fork.json
```

A CI step or Makefile target would regenerate manifests for each known deployment.
The example.com manifest already exists; the 0fork.com manifest would be generated
and committed alongside it.

### Option C — Service diff from fork-overrides.yml (low effort, partial fix)

`playbooks/vars/fork-overrides.yml` already tracks which flags differ on 0fork.com.
Extend it to also declare which services are disabled:

```yaml
# Explicitly disabled on 0fork.com
services_disabled_on_fork:
  - glitchtip        # keycloak_glitchtip_enabled: false
  - mail_submission_recovery   # keycloak_mail_platform_submission_recovery_enabled: false
```

A `make diff-services` target would read this file and produce a human-readable
comparison against the example.com registry. Fast to implement; does not require a
schema change.

---

## Recommended Remediation

| Priority | Action | Effort | Owner |
|----------|--------|--------|-------|
| P1 | Add `services_disabled_on_fork` block to `fork-overrides.yml` (Option C) | 30 min | claude |
| P2 | Extend `platform_manifest.py` with `--identity-overlay` flag (Option B) | 2h | claude |
| P3 | Schema v3 multi-deployment registry + `list_services.py` (Option A) | 1 day | claude |
| P3 | CI job: regenerate both manifests on every push to main | 1h | claude |

Option C can ship today and closes the "is this service enabled on 0fork.com?"
question immediately. Options A/B are the durable fix.

---

## Lessons Learned

1. **Every fork needs a machine-readable service manifest at converge time.**
   The `make converge-*` flow should emit (or update) a `build/platform-manifest-<deployment>.json`
   automatically, not leave it for a human to remember.

2. **The exposure registry must be deployment-aware from the start.**
   Adding a second deployment exposed that `zone_name: localhost` was always
   a placeholder. The schema should have been `deployments: {}` from ADR 0424 onward.

3. **`fork-overrides.yml` is a policy file that already tracks divergence.**
   It's the right place to declare *service-level* divergence, not just
   variable-level divergence. This is a zero-cost extension of existing
   practice.

4. **Programmatic answers reduce agent context cost.**
   Every time an agent must reconstruct the service list from first principles,
   it reads 5+ files and reasons about identity overlays. A `list_services.py`
   script would reduce this to one subprocess call and a JSON parse.
