# Postmortem: Digit-Leading Domain Prefixes Break Multiple Identifier Namespaces

**Date:** 2026-04-23
**Severity:** High (blocks full convergence on any `0xxx.com`-class domain)
**Affected versions:** All versions prior to the `platform_sql_prefix` fix
**Discovered by:** Stage-5 convergence validation on 0fork.com (Hetzner AX41-NVMe)
**Fixed in:** PRs #47, #48

---

## Summary

`platform_config_prefix` is derived as the first DNS label of `platform_domain`
(`0fork.com → "0fork"`). When an operator's domain starts with a digit, this
prefix is injected verbatim into six different identifier namespaces — PostgreSQL
role names, PVE user/role names, POSIX system usernames, Proxmox ACME plugin IDs,
and Proxmox storage IDs — all of which prohibit identifiers that begin with a
non-letter. Every convergence that touched those resources failed.

The fix introduces `platform_sql_prefix` (a misnomer by now — it covers all
identifier-sensitive contexts), which strips leading non-`[a-z_]` characters
before the prefix is used as an identifier.

---

## Timeline

| UTC | Event |
|-----|-------|
| 2026-04-23 09:40 | `converge-openbao` fails: `openbao_postgres_backend requires a safe admin role name`; role name `0fork_openbao_connect_all` rejected by PostgreSQL `CREATEUSER` |
| 2026-04-23 10:15 | Full audit of `platform_config_prefix` usages reveals 6 affected namespaces |
| 2026-04-23 10:30 | `platform_sql_prefix` variable added to `identity.yml`; `openbao_postgres_connect_role` wired to it |
| 2026-04-23 10:45 | Extended sweep: PVE role, PVE user, ACME plugin ID, Linux username, storage ID all updated |
| 2026-04-23 11:00 | PR #47 (PostgreSQL fix) + PR #48 (full sweep) pushed |

---

## Root Cause

The variable `platform_config_prefix` was designed for use in **file names and
human-readable labels**, where leading digits are fine. It was never audited
against the identifier grammars of the systems it was injected into.

Domain names with a digit-leading TLD-1 label (`0fork.com`, `1x.io`, `3ops.dev`)
are valid per RFC 1123 (which relaxed RFC 952's alpha-only first-char rule for
host labels). They are increasingly common in the `0xxx.com` / `1xxx.com`
namespace for tech companies and projects. The platform must support them.

The six affected namespaces and their grammars:

| Namespace | Grammar | Broken value |
|-----------|---------|--------------|
| PostgreSQL role name | `^[a-z_][a-z0-9_]*$` | `0fork_openbao_connect_all` |
| Proxmox PVE role | `^[A-Za-z][A-Za-z0-9]*$` | `0forkAutomation` |
| Proxmox PVE user | `^[A-Za-z0-9\.\-_]+@realm$` (alpha first) | `0fork-automation@pve` |
| POSIX `useradd` username | `^[a-z_][a-z0-9_\-]*$` | `0fork-control-plane-backup` |
| Proxmox ACME plugin ID | `^[A-Za-z][A-Za-z0-9\-_]*$` | `0fork-hetzner-dns` |
| Proxmox storage ID | `^[A-Za-z][A-Za-z0-9\-_]*$` | `0fork-backup-offsite` |

---

## Fix

### New variable: `platform_sql_prefix`

Added to `inventory/group_vars/all/identity.yml`:

```yaml
# SQL-safe identifier derived from platform_config_prefix.
# PostgreSQL role names must start with [a-z_], so any leading digits or
# punctuation are stripped (e.g. `0fork` → `fork`, `lv3` → `lv3`).
# Used wherever the prefix appears in a database role or schema name.
platform_sql_prefix: "{{ platform_config_prefix | regex_replace('^[^a-z_]+', '') }}"
```

The name `platform_sql_prefix` is slightly misleading (it is used beyond SQL)
but is kept for consistency with existing ADR 0385 variable naming. A future
refactor may rename it to `platform_ident_prefix`.

### Variables updated to use `platform_sql_prefix`

All in `inventory/group_vars/all/main.yml`:

| Variable | Old | New |
|----------|-----|-----|
| `openbao_postgres_connect_role` | `{{ platform_config_prefix }}_openbao_connect_all` | `{{ platform_sql_prefix }}_openbao_connect_all` |
| `proxmox_acme_plugin_id` | `{{ platform_config_prefix }}-hetzner-dns` | `{{ platform_sql_prefix }}-hetzner-dns` |
| `proxmox_api_automation_user` | `{{ platform_config_prefix }}-automation@pve` | `{{ platform_sql_prefix }}-automation@pve` |
| `proxmox_api_token_role` | `{{ platform_config_prefix \| capitalize }}Automation` | `{{ platform_sql_prefix \| capitalize }}Automation` |
| `control_plane_recovery_backup_store_user` | `{{ platform_config_prefix }}-control-plane-backup` | `{{ platform_sql_prefix }}-control-plane-backup` |
| `proxmox_dr_offsite.id` | `{{ platform_config_prefix }}-backup-offsite` | `{{ platform_sql_prefix }}-backup-offsite` |
| `proxmox_dr_offsite.path` | `/mnt/pve/{{ platform_config_prefix }}-backup-offsite` | `/mnt/pve/{{ platform_sql_prefix }}-backup-offsite` |

### Variables intentionally unchanged

These remain on `platform_config_prefix` because the destination namespace
has no restriction on leading digits:

- File paths (`/etc/ssh/sshd_config.d/90-0fork-hardening.conf`, etc.)
- Local `.local/` file paths (controller-side only)
- Directory paths (`/run/0fork-secrets`, `/etc/0fork/windmill`, etc.)

---

## Why It Wasn't Caught Earlier

1. **The example.com production deployment never hit it.** `lv3` starts with a
   letter. All CI and convergence testing was against that identity.

2. **No unit test for identifier grammar.** The platform's `validate_repository_data_models.py`
   validates structural correctness of YAML but does not evaluate Jinja2
   templates against a digit-leading prefix and check the results against
   identifier grammars.

3. **The `| capitalize` filter was misleading.** Jinja2's `capitalize` makes
   the first character uppercase and the rest lowercase. For a string starting
   with a digit (`0fork`), it is a no-op — `0fork | capitalize = 0fork`.
   This looked like it was "fixing" the issue but was not.

---

## Impact

No production impact (production is `example.com`). The `0fork.com` fork clone
was in Stage-5 validation mode and not serving live traffic.

Any operator forking this platform with a domain whose first label starts
with a digit would have hit this in convergence. The fix is backward-compatible:
for `example.com`, `platform_sql_prefix = "lv3"` (unchanged). For `0fork.com`,
`platform_sql_prefix = "fork"`.

---

## Prevention

### Short-term

Add a validation check in `scripts/validate_repository_data_models.py` (or a
dedicated `validate_identity_vars.py`) that:
1. Reads `platform_config_prefix` and `platform_sql_prefix`
2. Asserts `platform_sql_prefix` matches `^[a-z_][a-z0-9_]*$`
3. Asserts `platform_sql_prefix` is non-empty after stripping

### Long-term

- Rename `platform_sql_prefix` to `platform_ident_prefix` for clarity (ADR
  candidate, no urgency).
- Add a fork-validation test in CI that runs the full variable set with a
  digit-leading domain (e.g. `platform_domain: 0test.example.com`) and
  validates all derived identifiers against their target grammars.
- Document the `platform_sql_prefix` variable in ADR 0385 and the operator
  identity guide under "Naming rules for digit-leading domains".

---

## Lessons

1. **"Valid domain" ≠ "valid everywhere a domain label appears."** DNS labels
   allow digits at the start (since RFC 1123). SQL, POSIX, and PVE do not.
   Every system that derives an identifier from a domain label needs an
   explicit grammar safety valve.

2. **Test your claims at the edges.** The "any domain" claim in the README
   was only true for letter-leading domains. We knew `0xxx.com` is a real
   and common domain class; we should have tested it from the first day.

3. **`| capitalize` is not a safety filter.** It does not add a letter prefix;
   it only changes case. Do not use it as a substitute for grammar enforcement.
