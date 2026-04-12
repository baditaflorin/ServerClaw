# ADR 0364: Native Build Server Gate Execution

**Status**: Accepted
**Implementation Status**: Implemented
**Implemented On**: 2026-04-12
**Implemented In Platform Version**: 0.178.77
**Date**: 2026-04-06
**Tags**: ci-cd, automation, platform
**First repo version**: 0.179.0
**First platform version**: n/a (operator toolchain change only)

## Context

The pre-push validation gate runs each check inside an amd64 Docker container pulled from
`registry.example.com/check-runner/*`. On the remote build server (10.10.10.30, x86_64, up to 24 CPUs)
each check pays per-check Docker overhead: image pull on cold cache, container start/teardown,
and emulation when the operator's controller machine is arm64 (Apple Silicon Mac).

Observed costs on a recent push:
- `ansible-lint` in Docker on remote: 549 s
- `ansible-syntax` in Docker on remote: 275 s
- Local arm64 fallback (amd64 emulation): ansible-lint killed by SIGTERM before completing

The build server already has Python 3.12, ansible-lint, ansible-playbook, and other tools
installed. The validation scripts in this repo (e.g. `scripts/validate_repo.sh`) are
architecture-agnostic shell/Python scripts that need only the host tool versions. Docker
is appropriate for fully hermetic per-developer isolation, but is unnecessary when the
build server is a controlled, Ansible-managed environment with pinned tool versions.

The controller's local fallback on arm64 hardware will also benefit: native execution
removes amd64 emulation overhead and eliminates the SIGTERM kill from the 10-minute
background task timeout.

## Decision

1. Add `native_command` to every check entry in `config/validation-gate.json`.
2. Add `LV3_NATIVE_EXECUTION` support to `scripts/parallel_check.py`:
   when `LV3_NATIVE_EXECUTION=1` (from env or from the source prefix `build-server-native`),
   the runner executes `native_command` directly instead of `docker run`.
3. Update `config/build-server.json` `pre-push-gate` to set `LV3_NATIVE_EXECUTION=1`.
4. Add a playbook (`playbooks/services/build-server-gate-tools.yml`) that installs and
   pins every tool the native gate checks require.
5. Keep Docker-based execution as the default for all other runners (local controller
   fallback, Gitea CI, Woodpecker) where the environment is not operator-managed.

## Consequences

### Positive
- Removes per-check Docker overhead on the build server (~3-5× speedup for Python checks).
- Eliminates amd64-emulation SIGTERM kills on arm64 controller fallback.
- Build server can saturate all 24 CPUs with parallel native processes instead of
  sequential Docker container start/stop.
- Single `playbooks/services/build-server-gate-tools.yml` is the authoritative
  tool version pin for the build server — no divergence between Docker image and native.

### Negative
- Tool version on the build server must be kept in sync with the Docker images via
  Ansible — a `make apply-gate-tools` step must be run after tool version bumps.
- Native execution bypasses the Docker hermetic sandbox. A compromised build server
  could affect validation results.
- If the build server is reprovisioned, `playbooks/services/build-server-gate-tools.yml`
  must be converged before the gate works.

## Implementation

- `config/validation-gate.json` — `native_command` added to all 23 checks.
- `scripts/parallel_check.py` — `native_command` field, `should_use_native_command()`,
  `LV3_NATIVE_EXECUTION` env var support.
- `config/build-server.json` — `LV3_NATIVE_EXECUTION=1` in `pre-push-gate` command.
- `playbooks/services/build-server-gate-tools.yml` — installs ansible-lint, yamllint,
  semgrep, trivy, tofu, packer, python3 packages on `docker-build`.

## Related ADRs

- ADR 0082 — Remote Build Execution Gateway (rsync+SSH pattern)
- ADR 0083 — Docker-Based Check Runner (rationale for Docker-per-check)
- ADR 0087 — Repository Validation Gate (gate manifest and lane model)
- ADR 0264 — Failure-Domain-Isolated Validation Lanes
- ADR 0266 — Validation Runner Capability Contracts
