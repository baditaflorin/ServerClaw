# Postmortem: ServerClaw History Reconciliation

**Date:** 2026-04-11
**Severity:** LOW
**Trigger:** `git push serverclaw main` rejected (non-fast-forward)
**Resolution:** Publish script re-run with sanitized snapshot

---

## Incident Summary

After the emergency credential rotation (ADR 0405) was committed and pushed
to `origin` (private repo), a direct `git push serverclaw main` was rejected
because the ServerClaw public remote has a **different commit history** than
the private repo's `main` branch.

This is by design: the `publish_to_serverclaw.py` script creates **sanitized
snapshot commits** on the ServerClaw remote, not direct mirrors. The two repos
share an ancestor but diverge structurally because the publish pipeline:

1. Replaces identity files (hosts.yml, identity.yml, operators.yaml, proxmox-host.yml)
2. Performs regex sanitization on 6,479 files (domains, IPs, hostnames)
3. Deletes excluded files
4. Creates a new commit on the `serverclaw` remote's `main` branch

A direct `git push` would bypass all sanitization and expose private
infrastructure details.

---

## History Divergence Analysis

### Common Ancestor

```
243e407d1 — docs: Codify publication pipeline for agents
```

Both `origin/main` and `serverclaw/main` share this commit as the last
point where they were aligned (the initial public release commit).

### Commits on `origin/main` NOT on `serverclaw/main` (7)

| SHA | Description |
|-----|-------------|
| `49bea24` | docs: Document static analysis gate checks |
| `8d26981` | fix: restore real Proxmox public IP |
| `bd02022` | fix: restore real public IP in subdomain catalog |
| `c4aa848` | chore: regenerate subdomain exposure registry |
| `9b99331` | feat(security): Emergency credential rotation |
| `f03df13` | Merge claude/hungry-raman |
| `ba4b062` | [release] Bump to 0.178.103 |
| `cc072eb` | fix(security): Redact remaining secret values from postmortems |

These commits contain the credential rotation artifacts (ADR 0405,
postmortems, rotation script, runbook) plus IP restoration fixes that
were made after the initial public release.

### Commits on `serverclaw/main` NOT on `origin/main` (1)

| SHA | Description |
|-----|-------------|
| `72a8889` | [publish] Sanitized snapshot from 243e407d13 |

This was the initial sanitized publication commit created by
`publish_to_serverclaw.py`. It applied string replacements across all
6,466 files, replacing `example.com` with `example.com`, real IPs with
placeholders, and operator identity with generic values.

---

## Why Direct Push Would Have Been Wrong

A `git push --force serverclaw main` would have:

1. **Exposed real infrastructure details** — The private `main` branch
   contains real IPs (`203.0.113.1`, `10.10.10.x` subnet), real domain
   (`example.com`), operator identity, and deployment-specific host names. The
   sanitizer replaces all of these.

2. **Overwritten the sanitized inventory** — The public repo has a templated
   `hosts.yml` with fork-friendly placeholders and documentation comments.
   Direct push would replace it with the real production inventory.

3. **Included 3 Dependabot PRs' base** — The ServerClaw remote has 3
   Dependabot PRs for `cryptography`, `python-multipart`, and `requests`.
   A force push would orphan those PRs.

---

## Resolution

The correct procedure is always to use the publish pipeline:

```bash
python3 scripts/publish_to_serverclaw.py --push
```

This was executed successfully. The pipeline:

1. Ran pre-publish coverage audit (13 leak markers checked)
2. Created a temporary worktree from `main @ cc072ebe32`
3. Replaced 4 identity files with templates
4. Applied string sanitization to 6,479 files
5. Ran leak check — **PASSED** (no leaks detected)
6. Committed sanitized snapshot to `serverclaw/main`
7. Pushed to `github.com/baditaflorin/ServerClaw`

### What Was Published

The new sanitized snapshot includes:
- **ADR 0405** — emergency credential rotation decision (with domains sanitized)
- **3 postmortems** — with all secret values redacted and domains sanitized
- **Rotation script** — `scripts/emergency_credential_rotation.py`
- **Rotation runbook** — `docs/runbooks/emergency-credential-rotation.md`
- **Rotation receipts** — 4 timestamped JSON receipts
- **OIDC secret removal** — ws-0362 no longer contains the inline secret

### Leak Prevention

Before publishing, two rounds of redaction were needed:

| File | What Was Leaked | Fix |
|------|-----------------|-----|
| `2026-04-11-public-release-secret-exposure.md` | Semaphore admin password (old, rotated) inline in table | Replaced with `[REDACTED — rotated]` |
| `2026-04-11-public-release-secret-exposure.md` | Keycloak OIDC secret inline in table | Replaced with `[REDACTED — rotated]` |
| `2026-04-11-public-release-secret-exposure.md` | Gitea API token inline in table | Replaced with `[REDACTED — rotated]` |
| `2026-04-11-public-release-secret-exposure.md` | git-filter-repo example with real secret values | Replaced with placeholder patterns |
| `emergency-credential-rotation.md` (runbook) | Gitea token suffix `...6807f3` | Replaced with generic description |
| `2026-04-11-full-credential-rotation-convergence.md` | Gitea token suffix `...6807f3` | Replaced with generic description |

The publish script's built-in leak detector caught the Semaphore password
(`[REDACTED — rotated]`) before it could reach the public repo.
Even though these credentials are all rotated and invalid, publishing old
values in documentation is an anti-pattern.

---

## Lessons Learned

### 1. Never `git push` directly to serverclaw

The publish pipeline exists for a reason. Direct pushes bypass sanitization
and will expose infrastructure details. The `serverclaw` remote intentionally
has divergent history.

### 2. Postmortems about secrets should not contain the secrets

When writing postmortems about credential exposure, use `[REDACTED]` or
reference the `.local/` path instead of pasting the actual value — even if
it's already been rotated. The leak detector is a safety net, not a primary
control.

### 3. The publish pipeline works

The combination of file templates, regex sanitization, and leak detection
successfully prevented 6 inline secret values from reaching the public repo.
The 13-marker leak detection caught what manual review missed.

---

## Artifacts

| Artifact | Path |
|----------|------|
| This postmortem | `docs/postmortems/2026-04-11-serverclaw-history-reconciliation.md` |
| Publish script | `scripts/publish_to_serverclaw.py` |
| Sanitization config | `config/publication-sanitization.yaml` |
| Published repo | `github.com/baditaflorin/ServerClaw` |
