# ADR 0469: connection.yml SSH key pull from OpenBao

- Status: Accepted
- Implementation Status: Implemented (`scripts/deployment.py::_materialize_vault_key`)
- Date: 2026-04-29
- Concern: secret-handling, multi-deployment, key-rotation
- Tags: openbao, ssh, secrets, deployment-v1, connection
- Implements: improvement #9 from the 2026-04-29 reliability review
- Depends on: ADR 0440 (per-deployment connection registry), ADR 0448

---

## Context

Per-deployment `connection.yml` (ADR 0440) declares the SSH key path used to reach the Proxmox host and its guests. Today that path is a literal string under `.local/ssh/` — fine for a single workstation, brittle for a fleet of operators or a CI runner that doesn't ship those keys to disk.

Operators already keep these keys in OpenBao for the rest of the platform. The deployment wrapper should be able to pull a key on demand, write it to a mode-0600 tempfile for the duration of the SSH command, and unlink it afterwards — same shape as `openbao-agent` ctmpl rendering, but ad-hoc for the bootstrap path that runs before any role.

## Decision

Extend `connection.schema.json` so both `proxmox_host.key` and `guest_ssh.key` accept either of two shapes:

```yaml
# Existing form — literal path
key: bootstrap.id_ed25519

# New form — vault reference
key:
  vault: secret/lv3/ssh/proxmox-bootstrap
  field: private_key      # optional; defaults to "private_key"
```

`scripts/deployment.py::_resolve_ssh_key_spec` dispatches on the type:

- `str` → existing `_resolve_ssh_key` (path under `.local/ssh/`).
- `dict` → `_materialize_vault_key`:
  1. Run `${LV3_VAULT_FETCH_CMD:-openbao} read -field <field> <vault-path>`.
  2. Write the result to `mkstemp(prefix="lv3-vault-key-", dir=$LV3_VAULT_KEY_TMPDIR or $XDG_RUNTIME_DIR or /tmp)`.
  3. `chmod 0o600` the file.
  4. Return the path; the wrapper unlinks it on exit (existing tempfile cleanup hook).

The schema uses `oneOf` on both key fields and forbids unknown properties on the dict form so a typo (`vauld:` instead of `vault:`) fails validation rather than silently falling back to a wrong path.

### What this ADR defers

- **Secret rotation hooks.** OpenBao TTL/lease tracking is out of scope; the wrapper just pulls fresh on each invocation.
- **Per-host key indirection.** `connection.yml` still names a single key per role (proxmox_host vs guest_ssh). Per-host keys remain a `.local/ssh/` thing.
- **Caching.** Each invocation pulls the secret again. If round-trips become a problem, an in-memory cache keyed on `(vault, field)` is straightforward to add.

## Test surface

`tests/test_ws0471_vault_key_pull.py` covers:

- string vs dict dispatch in `_resolve_ssh_key_spec`
- mode-0600 tempfile materialization with the right body
- `--field` forwarding to the CLI
- error paths (fetch failure, empty body, missing `vault:`, empty `vault:`)
- jsonschema acceptance of both forms and rejection of unknown keys

11 tests.

## References

- [ADR 0440 — Per-Deployment Identity and Artifact Isolation](0440-per-deployment-identity-and-artifact-isolation.md)
- [ADR 0448 — Deployment Connection Registry and Wrapper](0448-deployment-connection-registry-and-wrapper.md)
