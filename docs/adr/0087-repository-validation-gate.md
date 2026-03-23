# ADR 0087: Repository Validation Gate (Pre-Push and CI)

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.93.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-23
- Date: 2026-03-22

## Context

There is currently no enforcement boundary between a local edit and a push to `main`. The repository has:
- `.pre-commit-config.yaml` — but hooks run locally and are easy to skip with `--no-verify`
- `scripts/validate_repository_data_models.py` — but it is only run when the operator remembers
- `ansible-lint` and `yamllint` — available as manual `make` targets; not gated

This means broken playbooks, invalid JSON schemas, and misconfigured workstream YAML reach `main` routinely. The subsequent debugging session runs on the operator's laptop (see ADR 0082 for the CPU cost). More critically:
- A broken Ansible role on `main` can be consumed by Windmill's scheduled playbook runner and cause a live-apply failure in production
- An invalid `config/service-capability-catalog.json` breaks the ops portal generator (ADR 0074) and the ops portal goes dark
- A schema violation in `workstreams.yaml` breaks `make generate-status` which is called by other tooling

The solution is a **layered validation gate** that:
1. Runs fast, cheap checks locally via pre-commit (syntax, secrets scan) — under 5 seconds
2. Delegates expensive checks to the build server (lint, schema validation, security scan) — 8–15 seconds
3. Blocks the push if either layer fails

## Decision

We will implement a **two-layer validation gate** — local pre-commit hooks and a remote build server check — enforced on every `git push` to any branch.

### Layer 1: Local pre-commit hooks (fast, cheap)

`.pre-commit-config.yaml` contains only hooks that complete in < 5 seconds:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: check-yaml           # YAML parse (not lint)
      - id: check-json           # JSON parse
      - id: detect-private-key   # No private keys in repo
      - id: end-of-file-fixer
      - id: trailing-whitespace
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.2
    hooks:
      - id: gitleaks             # secret scan; fast on staged files only
```

These hooks run locally with no network dependency and no Docker.

### Layer 2: Remote build server gate (thorough)

A `pre-push` git hook at `.git/hooks/pre-push` (managed by `make install-hooks`) calls the remote execution gateway:

```bash
#!/usr/bin/env bash
# .git/hooks/pre-push (generated; do not edit manually — run `make install-hooks`)

set -euo pipefail
echo "⏳ Running validation gate on build server..."
scripts/remote_exec.sh pre-push-gate --local-fallback
```

The `pre-push-gate` command on the build server runs all checks in parallel (ADR 0083):

| Check | Tool | Typical duration |
|---|---|---|
| Ansible lint | ansible-lint 2.17 | 12 s |
| YAML lint (full) | yamllint | 3 s |
| Python type check | mypy | 5 s |
| Schema validation | validate_repository_data_models.py | 4 s |
| Playbook syntax check | ansible-playbook --syntax-check | 6 s |
| Tofu validate | tofu validate | 3 s |
| Packer validate | packer validate | 2 s |
| Security scan | trivy fs (HIGH/CRITICAL) | 15 s |

Run in parallel across 8 cores: **wall-clock time ≈ 15–18 seconds**.

Pass/fail summary is printed in the operator's terminal. A failing check shows the full output and the push is aborted with exit code 1.

### `make install-hooks`

Installs the pre-push hook and verifies connectivity to `build-lv3`. Run once after cloning the repo. Part of `make setup`.

### Bypass escape hatch

```bash
git push --no-verify         # skips pre-commit AND pre-push gate
SKIP_REMOTE_GATE=1 git push  # skips remote gate only (pre-commit still runs)
```

`SKIP_REMOTE_GATE=1` is logged explicitly in `receipts/gate-bypasses/`. Native Git hooks cannot observe `git push --no-verify` after the fact, so that path remains unaudited break-glass and must be recorded manually in the change notes when used.

### Windmill post-merge CI

The remote pre-push gate runs on the operator's machine. A second gate runs in Windmill after merge to `main`, using the same `pre-push-gate` check definition. If the Windmill gate fails after merge, a NATS event `platform.ci.gate-failed` is emitted and a Grafana alert fires. This catches race conditions (two branches pass independently but conflict on merge).

### `config/validation-gate.json`

Machine-readable definition of all checks, their images, commands, and severity:

```json
{
  "gates": [
    {
      "id": "ansible-lint",
      "image": "registry.lv3.org/check-runner/ansible:2.17",
      "command": "ansible-lint --profile production .",
      "severity": "error",
      "timeout_seconds": 120
    }
  ]
}
```

This file is the authoritative definition consumed by both `scripts/remote_exec.sh` and the Windmill CI workflow, ensuring they run identical checks.

## Consequences

**Positive**
- Every push to any branch is validated before it reaches `main`; broken state on `main` becomes an exception, not the norm
- Two-layer design keeps the local pre-commit hook near-instant (< 5 s) while the thorough checks run remotely (< 18 s)
- `config/validation-gate.json` ensures the pre-push gate and Windmill CI are identical — no "passes locally, fails in CI" class of bugs
- Explicit `SKIP_REMOTE_GATE=1` bypass logging provides an audit trail without blocking emergency pushes

**Negative / Trade-offs**
- `make install-hooks` must be run after cloning; it is not automatic; a new contributor can push without the gate until they run `make setup`
- `SKIP_REMOTE_GATE=1` is an honour-system bypass; a determined person can always skip it — this is acceptable for a small team
- `git push --no-verify` cannot be audit-logged by native hooks; the repo documents that limitation instead of pretending it is solved
- Build server reachability is required for the full gate; fallback to local Docker is slower but available

## Alternatives Considered

- **GitHub Actions**: external, internet-dependent, cannot access private inventory; unsuitable
- **Enforce only via Windmill post-merge**: validation happens after the damage is done; `main` can be broken for minutes
- **Only local pre-commit hooks**: not reproducible; operator can `--no-verify`; no protection against version drift

## Related ADRs

- ADR 0082: Remote build execution gateway (runs the expensive checks)
- ADR 0083: Docker check runner (defines the containers each check runs in)
- ADR 0086: Ansible collection packaging (collection lint is a gate check)
- ADR 0073: Environment promotion gate (this gate is prerequisite to staging promotion)
