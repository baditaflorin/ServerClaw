# CPU-Only Platform Operations

ADR 0391 provides `scripts/platform_ops.py`, a deterministic CLI for routine
repository and platform-operation questions that can be answered from local
JSON/YAML contracts.

## Preconditions

- Work from a clean git worktree or record local changes with `git status`.
- Fetch the target comparison branch before using `--since`:

```bash
git fetch origin main --prune
```

## Common Queries

Find repo references for a service:

```bash
python3 scripts/platform_ops.py references --service directus
make ops-references SERVICE=directus
```

Analyze service impact:

```bash
python3 scripts/platform_ops.py impact --service directus
make ops-impact SERVICE=directus
```

Plan convergence from changed files:

```bash
python3 scripts/platform_ops.py converge-plan \
  --changed-files inventory/group_vars/all/identity.yml
```

Plan convergence from a git diff:

```bash
python3 scripts/platform_ops.py converge-plan --since origin/main
make ops-converge-plan SINCE=origin/main
```

Plan validation from a git diff:

```bash
python3 scripts/platform_ops.py validation-plan --since origin/main
make ops-validation-plan SINCE=origin/main
```

Check service completeness:

```bash
python3 scripts/platform_ops.py completeness --service directus
python3 scripts/platform_ops.py completeness --failing
make ops-completeness
```

Draft changelog entries from commits:

```bash
python3 scripts/platform_ops.py changelog --since origin/main
make ops-changelog SINCE=origin/main
```

Preview deterministic decommission cleanup:

```bash
python3 scripts/platform_ops.py decommission-preview --service example_service
```

## Interpreting Validation Plans

`validation-plan` returns:

- `changed_files`: normalized repo-relative inputs.
- `validation_gates`: ordered gate objects with command, reason, triggering
  files, and validation-runner lane metadata when available.
- `commands`: shell commands in the order an operator or CI runner should
  execute them.
- `unmapped_files`: changed files that did not match a deterministic rule.

If `unmapped_files` is non-empty, run the broader validation bundle for the
affected area and extend `scripts/platform_ops.py` with a new classifier rule
before relying on targeted validation for that file type.

## Boundary

Use this CLI for deterministic discovery, graph traversal, contract checks, and
template-like summaries. Use human or agent judgment for policy decisions,
architecture trade-offs, and interpreting failed convergence output.
