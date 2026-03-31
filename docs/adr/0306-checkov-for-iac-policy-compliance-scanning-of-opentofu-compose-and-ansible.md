# ADR 0306: Checkov For IaC Policy Compliance Scanning Of OpenTofu, Compose, And Ansible

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

The platform's infrastructure is expressed as code across three primary IaC
surfaces:

- **OpenTofu** HCL files that provision Proxmox VMs, networks, and storage
  (ADR 0085)
- **Docker Compose** YAML files that declare each service's runtime configuration
- **Ansible** playbooks and roles that configure every VM

ADR 0301 introduced Semgrep for SAST against application source code, Python
scripts, and Dockerfiles. Semgrep is a general-purpose pattern engine; it does
not have built-in knowledge of IaC-specific risk patterns such as:

- a Docker Compose service with `privileged: true` or a host-volume mount to
  `/var/run/docker.sock` that bypasses all container isolation
- an OpenTofu resource that opens a security group rule to `0.0.0.0/0`
- an Ansible task that disables a firewall (`ufw disable`) without an explicit
  exception record

These IaC misconfigurations are a distinct risk class from application SAST
findings. They directly change the attack surface of the platform
infrastructure rather than the application logic.

Checkov (`bridgecrewio/checkov`) is a static analysis tool purpose-built for
infrastructure-as-code policy scanning. It is Apache-2.0-licensed, written in
Python, ships as a Docker image, and has been in production use since 2019. It
includes over 1000 built-in policies for Terraform/OpenTofu, Docker Compose,
Kubernetes YAML, Ansible, and Dockerfile. Every policy maps to a CWE or CVE
identifier and is documented with a remediation example. Checkov produces SARIF
and JSON output, integrates with CI systems via exit code, and exposes a REST API
in its SaaS mode (not used here; self-hosted rule execution is sufficient).

## Decision

We will integrate **Checkov** as a required CI gate step for all IaC surfaces in
the repository, running on `docker-build-lv3` alongside the existing Semgrep step.

### Deployment rules

- Checkov runs as a Docker Compose `run` step in the Gitea Actions CI gate
  (ADR 0087); the image is pulled through Harbor (ADR 0068) and pinned to a
  SHA digest
- the Checkov version is tracked in `versions/stack.yaml` and updated via the
  Renovate Bot process (ADR 0297)
- no Checkov SaaS account or network call to `bridgecrew.cloud` is made; all
  policies are evaluated using the bundled policy set and the custom platform
  overrides in `config/checkov/`

### Live implementation note

The pinned offline Checkov build currently used by the repository is
`3.2.469`. Two practical limits matter for this implementation:

- the offline CLI does not currently expose the `docker_compose` framework
- the repository stores Docker Compose as Jinja templates rather than static
  committed Compose YAML

The live implementation therefore scans the repo's actual OpenTofu and Ansible
surfaces directly, emits the Compose gap as an explicit bounded note, and uses
repo-managed rule levels from `config/checkov/policy-gate.yaml` because offline
Checkov output does not populate severity values consistently without the SaaS
backend.

### Scanned surfaces and policy sets

| Surface | Path pattern | Checkov framework |
|---|---|---|
| OpenTofu resources | `tofu/**/*.tf` | `terraform` |
| Docker Compose services | `collections/ansible_collections/lv3/platform/roles/*/templates/docker-compose*.j2` | bounded gap recorded by the wrapper until rendered Compose becomes a governed repo surface |
| Ansible playbooks and roles | `playbooks/**/*.yml`, `roles/**/*.yml` | `ansible` |
| Kubernetes/Nomad job files | `config/nomad/**/*.hcl` | `terraform` (HCL parser) |

### Severity and gate behaviour

- findings are classified by the repo-managed level map in
  `config/checkov/policy-gate.yaml`; this preserves deterministic blocking
  behaviour even when offline Checkov does not populate severities
- the current blocking levels are the custom Proxmox OpenTofu invariants
  `CKV_LV3_1` through `CKV_LV3_3`
- the current provider TLS finding `CKV_LV3_4` is warning-level and does not
  fail the gate
- all upstream built-in Ansible findings are currently preserved as note-level
  evidence unless they are later promoted or suppressed through the repo-managed
  policy catalog

### Skip list governance

- platform-specific policy suppressions are maintained in
  `config/checkov/skip-checks.yaml`; each entry requires:
  - the Checkov check ID (e.g. `CKV_DOCKER_2`)
  - the file path and line range the skip applies to
  - a cited business reason and the ADR or operator decision that justifies the
    deviation
- skip-list additions require a pull request with the same review gate as any
  other configuration change; inline `#checkov:skip` comments in source files are
  not permitted (they are invisible in the audit trail)

### Output and receipt model

- Checkov emits a SARIF report at `receipts/checkov/<git-sha>.sarif.json` after
  every gate run; this is archived as a CI artefact for 90 days
- net-new findings introduced by a commit (not present in the previous green
  baseline) are logged to the mutation audit log (ADR 0066) as
  `iac_policy_finding_introduced` events
- a weekly Windmill job runs Checkov against the full repository (not just
  changed files) to surface findings that slipped through incremental gates due
  to changed context

## Consequences

**Positive**

- Docker Compose privilege escalation risks (privileged containers, dangerous
  volume mounts, capability additions) are caught before they are deployed,
  closing a gap that Semgrep's application-code focus does not cover
- OpenTofu HCL policy enforcement means that a misconfigured VM resource (open
  firewall rule, no encryption at rest) is detected at PR time rather than after
  `tofu apply`
- the skip-list governance model preserves an auditable record of every deliberate
  policy deviation; an operator cannot silently bypass a policy without a
  documented justification

**Negative / Trade-offs**

- Checkov's Python runtime adds scan time to the CI gate; repositories with many
  Ansible roles will see the longest incremental duration
- Checkov's built-in policies are updated in each release; a Renovate Bot version
  bump (ADR 0297) may introduce new policy failures that block unrelated PRs until
  the skip list or code is updated
- some Checkov Ansible policies produce false positives for tasks that are
  intentionally elevated (e.g. the Falco eBPF installation step that requires
  CAP_BPF); these must be documented in the skip list

## Boundaries

- Checkov covers IaC surfaces (OpenTofu, Compose, Ansible); it does not cover
  application source code, Python scripts, or Go binaries — those are the
  responsibility of Semgrep (ADR 0301)
- Checkov does not perform runtime policy enforcement; it is a design-time gate;
  Falco (ADR 0300) and the OPA command catalog (ADR 0230) govern runtime policy
- Checkov does not replace the architecture fitness functions in the validation
  gate (ADR 0213); fitness functions test structural platform invariants while
  Checkov tests security policy compliance

## Related ADRs

- ADR 0066: Structured mutation audit log
- ADR 0068: Container image policy and supply chain integrity
- ADR 0085: OpenTofu VM lifecycle
- ADR 0087: Repository validation gate
- ADR 0102: Security posture reporting
- ADR 0213: Architecture fitness functions in the validation gate
- ADR 0230: Policy decisions via OPA and Conftest
- ADR 0297: Renovate Bot as the automated stack version upgrade proposer
- ADR 0298: Syft and Grype for SBOM and CVE scanning
- ADR 0300: Falco for container runtime security monitoring
- ADR 0301: Semgrep for SAST and application code security scanning

## References

- <https://github.com/bridgecrewio/checkov>
