# Workstream ws-0417-main-merge-edge-cert-and-sftpgo

- ADR: [ADR 0375](../adr/0375-certificate-validation-and-concordance-enforcement.md)
- Title: latest-main integration for edge certificate recovery and the SFTPGo dependency graph
- Status: `in_progress`
- Latest Reachable origin/main: `bf8be0939` with `VERSION=0.178.133`
- Branch: `codex/dependency-graph-sftpgo-fix`
- Worktree: `.worktrees/dependency-graph-sftpgo-fix`
- Owner: codex

## Purpose

Land the already-verified edge certificate recovery fix and the SFTPGo
dependency-graph refresh onto the latest reachable `origin/main`, then repair
the generated and policy surfaces that currently prevent the integration branch
from clearing the full pre-push gate.

## Scope

- keep `playbooks/fix-edge-certificate.yml` aligned with the live DNS-01
  recovery flow that restored the shared edge certificate lineage
- register `sftpgo` in `config/dependency-graph.json` and refresh the generated
  dependency documentation surfaces
- repair branch-local validation blockers uncovered by the current gate:
  workstream registration, ADR index drift, generated discovery artifacts, SLO
  and HTTPS/TLS generated assets, service completeness metadata, and strict repo
  policy expectations for edge-published services
- finish the closeout on `main`, push `origin/main`, verify the resulting repo
  version, and remove the dedicated worktree only after the merge is fully
  applied

## Verification

- live edge certificate recovery already converged successfully from this branch
- focused branch validation already passed for:
  `tests/test_makefile_playbook_targets.py`
  `tests/test_generate_status_docs.py`
  `tests/test_generate_release_notes.py`
  `tests/test_validation_gate.py`
  `tests/test_ansible_execution_scopes.py`
  `tests/test_platform_manifest.py`
  `tests/test_edge_publication_makefile.py`
- remaining work is to clear the current repository gate set on top of the
  latest reachable `origin/main`
