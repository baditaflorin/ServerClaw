# ADR 0083: Docker-Based Check Runner on Build Server

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

Validation and lint toolchains are currently installed directly on the operator's laptop as system or `pipx` packages. This creates version drift: a developer who upgrades `ansible-lint` gets different results from a colleague on an older version, and both differ from any future CI agent. When a lint rule change silently breaks a previously-passing playbook, the failure surface is invisible until after a push.

The build server (ADR 0082) provides remote execution capacity, but raw SSH execution still suffers from the same tool-version problem unless the remote environment is also pinned. Docker containers on the build server solve this cleanly: every check runs in an immutable, versioned image that is identical to whatever Windmill CI will use.

A secondary benefit is parallelism: individual check containers can run concurrently across cores on the build server, reducing total wall-clock time from sequential serial execution.

## Decision

We will maintain a set of **platform check runner images** defined in `docker/check-runners/` and published to the internal registry (`registry.lv3.org`).

### Image inventory

| Image | Tag | Tools included |
|---|---|---|
| `check-runner/ansible` | `<ansible-version>` | ansible-lint, ansible-core, jinja2, yamllint, community.general |
| `check-runner/python` | `<python-version>` | flake8, mypy, black, isort, pytest, jsonschema |
| `check-runner/infra` | `<version>` | tofu, packer, yamllint, jsonlint, trivy |
| `check-runner/security` | `<version>` | trivy, gitleaks, checkov |

All images are built from `docker/check-runners/<name>/Dockerfile` with pinned base images and `requirements.txt` / `.tool-versions`. Tags track the primary tool version (e.g. `check-runner/ansible:2.17`).

### `config/check-runner-manifest.json`

Central manifest mapping each `make` target to a runner image and command:

```json
{
  "lint-ansible": {
    "image": "registry.lv3.org/check-runner/ansible:2.17",
    "command": "ansible-lint --profile production .",
    "working_dir": "/workspace",
    "timeout_seconds": 120
  },
  "lint-yaml": {
    "image": "registry.lv3.org/check-runner/ansible:2.17",
    "command": "yamllint -c .yamllint .",
    "working_dir": "/workspace",
    "timeout_seconds": 60
  },
  "validate-schemas": {
    "image": "registry.lv3.org/check-runner/python:3.12",
    "command": "python scripts/validate_repository_data_models.py",
    "working_dir": "/workspace",
    "timeout_seconds": 90
  },
  "security-scan": {
    "image": "registry.lv3.org/check-runner/security:latest",
    "command": "trivy fs --exit-code 1 --severity HIGH,CRITICAL .",
    "working_dir": "/workspace",
    "timeout_seconds": 180
  }
}
```

### Execution model on the build server

`scripts/remote_exec.sh` (ADR 0082) reads the manifest, then runs:

```bash
docker run --rm \
  -v /opt/builds/proxmox_florin_server:/workspace:ro \
  -w /workspace \
  --cpus=4 \
  <image> <command>
```

Multiple checks run concurrently using a small Go or Python runner script (`scripts/parallel_check.py`) that launches containers in parallel and collects exit codes, producing a unified pass/fail summary with per-check timing.

### Update policy

Images are rebuilt by a Windmill workflow (`platform-check-runner-rebuild`) whenever a `docker/check-runners/*/Dockerfile` changes on `main`. The new image is pushed to `registry.lv3.org` and the digest is written back to `config/check-runner-manifest.json` in a follow-up commit. The build server pulls the updated image as part of that workflow.

Images are **never** rebuilt ad-hoc on the operator's laptop.

### Local development path

When `build-lv3` is unreachable, `scripts/remote_exec.sh --local-fallback` runs the same `docker run` command locally, consuming the same image. This preserves reproducibility at the cost of local CPU.

## Consequences

**Positive**
- Identical tool versions between interactive development, build server, and Windmill CI
- Parallel execution of independent checks (ansible-lint, yamllint, Python validation) reduces wall-clock time by 3–4×
- Adding a new lint tool requires only a Dockerfile change and a manifest entry — no laptop install instructions
- `trivy` and `gitleaks` run on every pre-push without requiring any local security toolchain installation

**Negative / Trade-offs**
- First run after an image update requires a Docker pull (~200–400 MB); subsequent runs are instant from cache
- Internal registry (`registry.lv3.org`) must be live before images can be pulled; bootstrap order matters (see workstream dependencies)
- Dockerfile maintenance adds a small ongoing overhead

## Alternatives Considered

- **`mise` / `asdf` for tool versioning on the build server**: pins versions but still requires native installation; does not give parallelism or security scan isolation
- **Nix**: hermetic and reproducible but high learning curve and complex to integrate with Ansible playbooks
- **Pre-built GitHub Actions runner images**: public images; not suitable for a private registry with custom tooling

## Related ADRs

- ADR 0082: Remote build execution gateway (calls into these containers)
- ADR 0068: Container image policy (governs how these images are scanned and promoted)
- ADR 0087: Repository validation gate (orchestrates the parallel check set defined here)
- ADR 0089: Build artifact cache (keeps images warm; caches pip and apt layers)
