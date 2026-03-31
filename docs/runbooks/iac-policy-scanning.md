# IaC Policy Scanning

## Purpose

ADR 0306 adds a repo-managed IaC policy scan that uses Checkov where the pinned
offline engine can evaluate the repository directly and layers repo-managed
OpenTofu invariants on top for the Proxmox provider surfaces that upstream
Checkov does not currently model.

## Primary Commands

Run the runner-backed gate slice exactly as the validation system sees it:

```bash
python3 scripts/parallel_check.py iac-policy-scan
```

Replay the wrapper directly from the current checkout and emit the JSON summary
plus SARIF receipts under `receipts/checkov/`:

```bash
uv run --with checkov==3.2.469 --with pyyaml python scripts/iac_policy_scan.py
```

## Governed Inputs

The authoritative ADR 0306 inputs are:

- [config/checkov/policy-gate.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/checkov/policy-gate.yaml)
- [config/checkov/skip-checks.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/checkov/skip-checks.yaml)
- [scripts/iac_policy_scan.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/iac_policy_scan.py)

`policy-gate.yaml` defines:

- which repo surfaces are scanned
- which check ids are blocking errors, non-blocking warnings, or informational notes
- the current bounded-gap note for Docker Compose templates

`skip-checks.yaml` is the only supported suppression path. Inline `#checkov:skip`
comments are not permitted.

## Current Coverage

The live implementation scans:

- OpenTofu under `tofu/`
- root playbooks under `playbooks/`
- legacy root roles under `roles/`
- packaged collection playbooks and roles under `collections/ansible_collections/lv3/platform/`

The current scan intentionally records Docker Compose as a bounded gap rather
than claiming direct coverage. This repository stores Compose as Jinja
templates, and pinned offline Checkov `3.2.469` does not currently expose the
`docker_compose` framework. Those templates remain under the existing Trivy
misconfiguration sweep until rendered Compose manifests become a governed repo
surface.

## Current Baseline

The latest branch-local replay on `2026-03-30` passed with:

- `0` blocking errors
- `2` non-blocking warnings for `provider "proxmox" { insecure = true }` in
  `tofu/environments/production/main.tf` and `tofu/environments/staging/main.tf`
- `799` non-blocking note-level Ansible findings from upstream built-in checks

Those note-level findings are preserved in the JSON summary and SARIF receipts.
They do not currently block the gate.

## Suppression Governance

Add a suppression only when all of these are true:

1. the finding is understood and deliberately accepted
2. the path scope is as narrow as possible
3. the reason and decision reference are explicit

Example shape:

```yaml
suppressions:
  - check_id: CKV2_ANSIBLE_1
    file: collections/ansible_collections/lv3/platform/roles/example/tasks/main.yml
    line_range: [10, 18]
    reason: Loopback HTTP health probe never leaves the guest network namespace.
    decision_ref: ADR 0306
```

## Outputs

Each run writes:

- `receipts/checkov/<git-sha>.json`
- `receipts/checkov/<git-sha>.sarif.json`

The JSON file is the operator-facing summary. The SARIF file is the portable
artifact for future CI or security tooling.

## Troubleshooting

- if the scan reports `CKV_LV3_1`, `CKV_LV3_2`, or `CKV_LV3_3`, fix the Proxmox
  OpenTofu invariant rather than suppressing it by default; those checks are the
  blocking platform-specific controls
- if the only findings are `CKV_LV3_4`, the gate will still pass; that warning
  records the current trusted-TLS gap on the Proxmox provider path
- if the wrapper reports a `CKV_LV3_PARSING` failure, treat it as a broken IaC
  input first and make the HCL parse clean again before trusting the scan
- if a remote build-server replay passes but the receipts are not present in the
  controller checkout, remember that `remote_exec.sh` only syncs the gate status
  file back from the immutable snapshot run; replay the wrapper locally when you
  need the JSON or SARIF artifact in the working tree
