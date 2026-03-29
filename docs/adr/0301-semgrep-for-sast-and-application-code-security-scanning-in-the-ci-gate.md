# ADR 0301: Semgrep For SAST And Application Code Security Scanning In The CI Gate

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

The platform's validation gate (ADR 0087) enforces structural, schema, and
fitness-function checks before any commit is eligible to merge. It currently
has no automated static application security testing (SAST) pass. This means:

- Python scripts in `scripts/` and Windmill workflow code can introduce unsafe
  patterns (shell injection, hardcoded credentials, unsafe deserialization) without
  any automated detection
- Dockerfiles can embed practices that violate the image policy (ADR 0068) without
  a machine-readable finding
- operator-authored Ansible tasks can contain common misconfigurations (e.g.
  `become: yes` with `shell:` and unquoted variables) that static analysis would
  catch before they reach production

The platform also has no rule-based enforcement for secrets accidentally committed
to the repository; the existing supply-chain hardening relies on correct operator
behaviour rather than automated detection.

Semgrep (`semgrep/semgrep`) is a static analysis engine that runs pattern-based
rules against source code with no runtime execution of the analysed code. It is
LGPL-2.1-licensed for the engine, ships as a Python package and a Docker image,
and has been in active production use since 2020. It supports Python, Go,
Dockerfile, YAML (including Ansible playbooks), and more. Semgrep exposes a
JSON and SARIF output mode suitable for CI integration and has a published REST
API for registry rule management. Rules are plain YAML files stored alongside
the code; no SaaS dependency is required for self-hosted rule execution.

## Decision

We will integrate **Semgrep** as a required step in the Gitea Actions CI
validation gate (ADR 0087) running on `docker-build-lv3`.

### Deployment rules

- Semgrep runs as a Docker Compose `run` step in the Gitea Actions pipeline;
  the image is pulled through Harbor (ADR 0068) and pinned to a SHA digest
- no Semgrep SaaS account or network call to `semgrep.dev` is made; all rules
  are stored in `config/semgrep/rules/` and resolved locally
- the Semgrep image version is pinned in `versions/stack.yaml` and updated via
  the Renovate Bot process (ADR 0297)

### Rule sets

Three rule sets are applied in sequence:

1. **Secrets detection** (`config/semgrep/rules/secrets.yaml`): patterns for
   common secret shapes committed in code (API keys, PEM headers, OpenBao token
   prefixes, Gitea token prefixes); a match is always a blocking gate failure
   regardless of severity
2. **Application SAST** (`config/semgrep/rules/sast.yaml`): Python and Go
   patterns for shell injection, unsafe subprocess usage, SQL string formatting,
   and unsafe deserialization; findings at `ERROR` severity are blocking; `WARNING`
   findings produce a non-blocking annotation in the Gitea PR
3. **Dockerfile and image policy** (`config/semgrep/rules/dockerfile.yaml`):
   rules that enforce image policy (ADR 0068) conventions: no `FROM latest`, no
   `RUN apt-get` without `--no-install-recommends`, secrets not passed as `ENV`
   or `ARG`; all findings are blocking

### Output and receipt rules

- Semgrep produces a SARIF report at `receipts/sast/<git-sha>.sarif.json` for
  every gate run; the report is archived as a CI artefact for 90 days
- the gate summary script reads the SARIF file and counts findings by severity;
  it exits non-zero if any blocking-severity finding is present, halting the merge
- net-new findings (present in the current commit but not in the previous green
  run) are logged to the mutation audit log (ADR 0066) as
  `sast_finding_introduced` events

### Custom rule governance

- platform-specific rules in `config/semgrep/rules/` are version-controlled and
  require PR review; no rule is added without a comment explaining what risk it
  mitigates
- upstream Semgrep registry rule IDs referenced in the rule files must be pinned
  to a specific rule revision hash in `config/semgrep/rule-pins.yaml` so that
  an upstream rule change does not silently alter gate behaviour

## Consequences

**Positive**

- secrets accidentally committed to the repository are caught before merge rather
  than after a security incident
- the gate catches common Python and Dockerfile misconfigurations without
  requiring a running instance or a CVE database refresh
- SARIF output is a standard format that can be consumed by future security
  dashboards, Superset views (ADR 0292), or external tools without format
  translation

**Negative / Trade-offs**

- Semgrep's Python rules do not execute the code; complex control flow and
  dynamic patterns are missed; it is a complement to, not a replacement for,
  runtime monitoring (Falco, ADR 0300)
- the rule set requires active maintenance; stale rules produce false positives
  that reduce gate trust
- Semgrep adds scan time to the CI gate; repositories with large `scripts/` trees
  or many Ansible roles will see the longest incremental gate duration

## Boundaries

- Semgrep covers application source code, Dockerfiles, and Ansible YAML; it does
  not cover OpenTofu HCL or infrastructure policy — that is governed by Checkov
  (ADR 0306)
- Semgrep does not scan compiled binaries or container image layers; that is the
  responsibility of Syft and Grype (ADR 0298)
- Semgrep does not replace code review; it raises findings that reviewers must
  assess, not conclusions about intent

## Related ADRs

- ADR 0066: Structured mutation audit log
- ADR 0068: Container image policy and supply chain integrity
- ADR 0087: Repository validation gate
- ADR 0102: Security posture reporting
- ADR 0138: Published artifact secret scanning
- ADR 0213: Architecture fitness functions in the validation gate
- ADR 0297: Renovate Bot as the automated stack version upgrade proposer
- ADR 0298: Syft and Grype for SBOM and CVE scanning
- ADR 0300: Falco for container runtime security monitoring
- ADR 0306: Checkov for IaC policy compliance scanning

## References

- <https://github.com/semgrep/semgrep>
