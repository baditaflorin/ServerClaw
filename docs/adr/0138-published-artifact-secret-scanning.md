# ADR 0138: Published Artifact Secret Scanning

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.123.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

The repository already protects source files with the fast `gitleaks` pre-commit hook from ADR 0087. That does not cover the generated artifacts that are later published to operator surfaces or committed as operational evidence:

- live-apply and gate-bypass receipts under `receipts/`
- triage reports under `.local/triage/reports/`
- generated search documents under `build/search-index/`
- generated deployment-history portal files under `build/changelog-portal/`

Those artifacts are not primary source code, but they can still contain secrets if a workflow, script, or error path serializes token material into a JSON payload or rendered page. Once that happens, the secret can be indexed, reviewed in a browser, or merged into the repository without any dedicated artifact-stage check.

## Decision

We will add a **published artifact secret-scanning stage** that runs before merge and before artifact publication.

### Scanner contract

The stage is implemented by `scripts/published_artifact_secret_scan.py`.

It scans these repo-managed artifact surfaces:

- `receipts/**/*.json`
- `.local/triage/reports/**/*.json`
- `build/search-index/**/*.json`
- `build/changelog-portal/**/*.html`
- `build/changelog-portal/**/*.json`

When `gitleaks` is available, the scanner shells out to `gitleaks detect --no-git` with the repository `.gitleaks.toml`. When `gitleaks` is unavailable, it falls back to the repo-specific regex rules and allowlists defined in `.gitleaks.toml` so local repo-managed checks can still catch the platform-specific dummy and runtime token patterns.

### Validation-gate integration

`config/validation-gate.json` gains a new blocking `artifact-secret-scan` check that runs in the security check-runner image, where `gitleaks` is already present.

This keeps the artifact scan in the same enforced pre-push and post-merge gate path as the rest of the repository controls.

### Operator command

A dedicated `make scan-published-artifacts` target runs the scanner directly from a checkout.

The existing publication-oriented targets:

- `make search-index-rebuild`
- `make generate-changelog-portal`

now run the artifact scan immediately after writing their outputs.

### Rule coverage

`.gitleaks.toml` is extended with repo-specific rules for:

- OpenBao / Vault-style service tokens
- step-ca provisioner passwords in config-like text
- Keycloak client secret assignments

Placeholder strings used in ADRs, runbooks, and redacted examples are allowlisted explicitly to avoid drowning the stage in documentation-only false positives.

## Consequences

**Positive**

- published JSON and HTML artifacts get a dedicated security stage instead of relying only on source-file scanning
- the same stage is available both as a manual command and as a blocking gate check
- dummy-secret fixtures can validate the scanner end to end without depending on a live platform

**Negative / Trade-offs**

- the fallback mode only enforces repo-defined `.gitleaks.toml` rules, not every upstream generic rule
- generated artifacts that are never written into the checkout still need the calling workflow to invoke the scanner explicitly
- documentation placeholders need ongoing allowlist maintenance

## Boundaries

- This ADR covers text artifacts written into the repository checkout or its generated build outputs.
- It does not scan binary artifacts such as container images, VM templates, or backups.
- It does not rotate or revoke leaked secrets; it detects the artifact exposure before publication or merge.

## Related ADRs

- ADR 0081: Platform changelog and deployment history
- ADR 0087: Repository validation gate
- ADR 0114: Rule-based incident triage engine
- ADR 0121: Local search and indexing fabric
