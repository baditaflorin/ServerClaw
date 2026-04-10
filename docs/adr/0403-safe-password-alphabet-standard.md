# ADR 0403: Safe Password Alphabet Standard

- Status: Accepted
- Implementation Status: Accepted, partial implementation pending
- Implemented In Repo Version: n/a
- Implemented In Platform Version: n/a
- Implemented On: 2026-04-10
- Date: 2026-04-10
- Concern: Security, Platform Reliability
- Depends on: ADR 0370 (Service Lifecycle Task Includes), ADR 0325 (ADR Reservation Ledger)
- Tags: security, secrets, passwords, credentials, reliability

---

## Context

Passwords on this platform are consumed in many different contexts simultaneously:

- **PostgreSQL connection strings** — `postgres://user:PASSWORD@host:5432/db`
- **Docker `env_file` values** — `KEY=VALUE` on a single line
- **YAML configuration files** — passed as plain scalars
- **HTTP Basic Auth URLs** — `https://user:PASSWORD@host/path`
- **Shell scripts** — assigned as `VAR="$PASSWORD"` or passed as arguments
- **Jinja2 templates** — interpolated into `.env`, `.conf`, `.yaml` files

### The Outline incident (2026-04-10)

The Outline wiki service (`wiki.lv3.org`) was broken because its DATABASE_URL
was constructed as:

```
postgres://outline:PASSWORD@postgres-vm-lv3:5432/outline
```

The password had been generated with `openssl rand -base64 24`, which produced
a value containing `/`. This broke URL parsing — the router treated everything
after the first `/` as the path component, not the password. The symptom was a
silent authentication failure at container startup.

The fix required: `| urlencode` in the Jinja2 template. But this is a
**band-aid**. The real fix is to never generate passwords that require encoding
in the first place.

### Existing inconsistency

An audit of the codebase revealed four distinct password-generation patterns in
active use, with no documented rationale for choosing one over another:

| Pattern | Alphabet | URL-safe | Shell-safe | Used in |
|---|---|---|---|---|
| `openssl rand -hex 32` | `[0-9a-f]` | Yes | Yes | keycloak, gitea, seed_data |
| `openssl rand -base64 24` | `[A-Za-z0-9+/=]` | **No** (`/`, `+`) | Conditional | keycloak_runtime (passwords), many roles |
| `python3 -c '…secrets.token_hex(32)'` | `[0-9a-f]` | Yes | Yes | glitchtip |
| `python3 -c '…secrets.token_urlsafe(24)'` | `[A-Za-z0-9-_]` | Yes | Yes | provision_operator, release_bundle, uptime_kuma |

`secret_rotation.py` already defines two allowed generators (`hex_32`,
`base64_24`), but `base64_24` is the problematic one and exists only for
historical reasons.

---

## Decision

### 1. Standard alphabet for machine-generated passwords

All machine-generated passwords on this platform **MUST** use one of two
canonical forms:

| Form | Alphabet | Length | Use case |
|---|---|---|---|
| **hex_32** | `[0-9a-f]` | 64 chars | Database passwords, API tokens, shared secrets between services |
| **urlsafe_32** | `[A-Za-z0-9-_]` | ~43 chars (256 bits) | Human-readable passwords, HTTP Basic Auth, anything embedded in a URL without encoding |

Both forms are URL-safe, shell-safe (no quoting required), YAML-safe, and
`.env`-safe. Neither requires percent-encoding.

**Excluded characters** — the following characters MUST NOT appear in
platform-generated passwords:

| Character | Why excluded |
|---|---|
| `/` | Terminates path component in URLs; also a shell path separator |
| `\` | Shell escape character; breaks Windows paths |
| `@` | Terminates userinfo in URLs (`user:pass@host`) |
| `:` | Separates user from password in URL userinfo |
| `#` | Starts fragment in URLs; starts comments in many config formats |
| `%` | Percent-encoding prefix; double-encoding bugs |
| `+` | URL-encoded space in `application/x-www-form-urlencoded` |
| `=` | Key-value separator in query strings and `.env` files |
| `;` | Statement separator in SQL and many shell-adjacent contexts |
| `,` | Field separator in CSV and some DSN formats |
| `'` `"` `` ` `` | Shell quoting characters |
| `<` `>` `&` | HTML/XML injection vectors; also shell redirect/pipe |
| `!` | Shell history expansion in interactive shells |
| `$` | Shell variable expansion |
| `(` `)` `{` `}` `[` `]` | Shell subshell / grouping; JSON/YAML structural characters |
| space, tab, newline | Obvious tokenization hazards |

### 2. Canonical generation commands

**Preferred — Ansible roles (shell task):**
```bash
# Standard: 256-bit hex (most services, especially database passwords)
openssl rand -hex 32

# Alternative for human-facing: URL-safe base64 (256 bits)
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

**Preferred — Python scripts:**
```python
import secrets
# Database passwords, machine tokens:
password = secrets.token_hex(32)
# Human-facing, Basic Auth:
password = secrets.token_urlsafe(32)
```

**Preferred — Manual / operator bootstrap:**
```bash
# Use the platform helper (preferred — single source of truth):
python3 scripts/init_local_overlay.py  # already uses token_hex

# Or directly:
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

**Forbidden:**
```bash
openssl rand -base64 24   # produces / and + — do not use for new passwords
```

### 3. secret_rotation.py: deprecate base64_24

The `base64_24` generator in `ALLOWED_GENERATORS` is deprecated. No new secrets
should declare `value_generator: base64_24`. Existing secrets using `base64_24`
should be migrated to `hex_32` or `urlsafe_32` at their next scheduled rotation.

When a `base64_24` password appears in a URL context, the Jinja2 template
**MUST** apply `| urlencode` as an intermediate defence until the password is
rotated:

```yaml
# Temporary defence — required while old base64_24 passwords survive:
DATABASE_URL: "postgres://{{ user }}:{{ password | urlencode }}@{{ host }}/{{ db }}"
```

### 4. Jinja2 template rule

Even when the password alphabet is safe, URL-embedded passwords **SHOULD**
still use `| urlencode` in templates as a defence-in-depth measure. The cost is
zero (no-op for safe alphabets); the benefit is protection against future
credential rotation introducing a non-compliant value.

```yaml
# Good — belt and suspenders:
DATABASE_URL: "postgres://{{ user }}:{{ pass | urlencode }}@{{ host }}/{{ db }}"

# Acceptable only when password is provably hex_32 and used outside URL context:
DB_PASSWORD: "{{ pass }}"
```

### 5. No plain-text passwords in Docker images or env_file at build time

The root cause of the Outline incident included Docker caching the `env_file`
at `docker compose up` time. This is standard Docker behaviour. It means:

- Passwords must be written to the `.env` / `provider.env` file **before**
  `docker compose up`.
- After rotating a password, you must run `docker compose down && docker compose up`
  — not just `docker compose restart`.

This is already documented in the common role's `docker_compose_converge.yml`
but is re-stated here as a constraint the password standard must work within.

---

## Consequences

### Positive

- No more `| urlencode` surprises in URL-embedded credentials.
- All passwords safe to embed in YAML, `.env`, shell, SQL `\copy`, and HTTP
  Basic Auth without escaping.
- Single auditable generation path — a future CSPRNG migration touches one
  pattern, not twenty.
- Operator can eyeball a password file and immediately know if it is
  compliant (hex = 64 lowercase hex chars; urlsafe = 43 mixed alphanumeric
  with `-` and `_`).

### Negative / Trade-offs

- `hex_32` passwords have a restricted alphabet (`[0-9a-f]`), which means more
  characters for the same bit-strength compared to `urlsafe_32`. 64 hex chars
  vs ~43 urlsafe chars for 256 bits. Both are well above any brute-force
  threshold for secrets at rest; the difference is negligible.
- `base64_24` passwords already in production cannot be changed without a
  coordinated down+up cycle per service. Migration is deferred to scheduled
  rotation windows, not a flag-day change.
- `token_urlsafe` uses `-` and `_` which are safe everywhere **except** some
  legacy DNS names and shell variable names. These are only used as _values_
  (not identifiers), so this is not a problem in practice.

---

## Migration Checklist (for future sessions)

- [ ] `secret_rotation.py`: add `urlsafe_32` to `ALLOWED_GENERATORS`; mark
  `base64_24` as deprecated in docstring
- [ ] Audit all Jinja2 templates that embed passwords in URLs; add `| urlencode`
  where missing
- [ ] Confirm `outline_runtime` templates use `| urlencode` (fixed as part of
  the incident that motivated this ADR)
- [ ] Update `init_local_overlay.py` to use `token_hex(32)` for all generated
  secrets (already done for most; verify completeness)
- [ ] Update service scaffold template (`roles/_template/`) to generate secrets
  with `openssl rand -hex 32` by default
- [ ] Rotate any `base64_24` passwords at next maintenance window (no rush;
  they are safe while the `| urlencode` guard is in place)
