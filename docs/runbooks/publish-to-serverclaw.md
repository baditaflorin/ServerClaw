# Publish to ServerClaw (Public Repo)

## Purpose

Sanitize the private `proxmox_florin_server` repo and push a clean copy to
the public `github.com/baditaflorin/ServerClaw` repo. All operator PII,
real IPs, deployment-specific VM names, and secrets are replaced with
placeholders before publishing.

## Prerequisites

- Git remote `serverclaw` configured: `git remote add serverclaw git@github.com:baditaflorin/ServerClaw.git`
- On `main` branch with clean working tree
- PyYAML available (installed automatically via `uv run --with pyyaml`)

## Commands

### Audit sanitization coverage (pre-flight)

```bash
make audit-sanitization
```

Reports gaps between real inventory values and sanitization patterns.
Exit codes: 0 = clean, 1 = warnings only (strict mode), 2 = CRITICAL gaps.

### Dry-run (sanitize + leak check, no push)

```bash
make publish-serverclaw
```

Creates a temporary worktree, applies all sanitization tiers, runs leak
detection, shows diff stats of what would be pushed. Does not push.

### Publish (sanitize + push)

```bash
make publish-serverclaw-push
```

Same as dry-run, then force-pushes the sanitized snapshot to `serverclaw/main`.

## Sanitization Tiers

### Tier A: Whole-file replacement

Four deployment-specific files are replaced entirely with fork-ready templates:

| Source file | Template |
|-------------|----------|
| `inventory/group_vars/all/identity.yml` | `publication/templates/identity.yml` |
| `inventory/hosts.yml` | `publication/templates/hosts.yml` |
| `config/operators.yaml` | `publication/templates/operators.yaml` |
| `inventory/host_vars/proxmox_florin.yml` | `publication/templates/proxmox_florin.yml` |

### Tier C: Regex string replacement

Applied to all text files not in Tier A. Patterns defined in
`config/publication-sanitization.yaml`:

- Domain: `lv3.org` -> `example.com`
- VM names: `*-lv3` / `*-staging-lv3` -> generic names
- Public IPs: Hetzner IPs -> RFC 5737 documentation IPs (203.0.113.x)
- IPv6: Real addresses -> documentation prefix (2001:db8::)
- PII: Operator names and emails -> `Platform Operator` / `operator@example.com`
- Host identity: `proxmox_florin` -> `proxmox-host`

### Leak check

Post-sanitization scan for marker strings that must never appear in public output.
Markers are auto-derived from the real inventory (CRITICAL values) plus a manual
list for values not in the four authoritative sources (e.g., API keys, secondary emails).

## Adding New Sensitive Values

When you add a new VM, operator, public IP, or domain:

1. Add a `string_replacements` entry in `config/publication-sanitization.yaml`
2. If it belongs in a Tier A file, update the corresponding template in `publication/templates/`
3. If it is CRITICAL (PII, public IP, secret), add it to `leak_markers` in the config
4. Run `make audit-sanitization` to verify coverage
5. Run `make publish-serverclaw` (dry-run) to confirm leak check passes

The drift detector will also catch omissions automatically on the next publish.

## Verification

After publishing, verify the public repo is clean:

```bash
# Clone fresh and scan for leaks
cd /tmp && git clone git@github.com:baditaflorin/ServerClaw.git sc-verify
grep -r 'lv3\.org\|65\.108\.75\|baditaflorin\|busui\.matei' sc-verify/ --include='*.yml' --include='*.yaml' --include='*.md' --include='*.json' | grep -v '.git/'
# Expected: no output (no leaks)

# Verify identity.yml has placeholders
grep 'platform_domain' sc-verify/inventory/group_vars/all/identity.yml
# Expected: platform_domain: example.com

rm -rf sc-verify
```

## Troubleshooting

### "ABORT: N CRITICAL coverage gap(s)"

The drift detector found sensitive values without sanitization patterns.
Run `make audit-sanitization` to see which values need patterns, then update
`config/publication-sanitization.yaml`.

### "ABORT: N leak(s) found"

A leak marker appeared in the sanitized output. Either:
- A Tier A template contains unsanitized values (fix the template)
- A Tier C pattern is missing or incorrect (fix the pattern)
- A new sensitive value was introduced without a pattern (add one)

### `.git` worktree pointer corrupted

The `proxmox[_-]florin` regex can modify the `.git` pointer file in worktrees
(it contains the repo path). The publish script skips `.git` files during
Tier C replacement. If you see `fatal: not a git repository` errors, this
skip is not working.

### Pre-commit/pre-push hooks fail in worktree

The publish script uses `--no-verify` for both commit and push in the
sanitized worktree. Hooks are designed for development commits, not
sanitized snapshots.

## Key Files

| File | Purpose |
|------|---------|
| `scripts/publish_to_serverclaw.py` | Publication engine |
| `scripts/audit_sanitization_coverage.py` | Drift detector |
| `config/publication-sanitization.yaml` | Replacement patterns, leak markers, exclusions |
| `publication/templates/` | Tier A replacement files |

## Related

- AGENTS.md "Publication Pipeline (ServerClaw)" section
- AGENTS.md "Public Repo Mode" section
- `docs/runbooks/published-artifact-secret-scanning.md`
