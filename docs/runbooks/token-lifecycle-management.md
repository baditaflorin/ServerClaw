# Token Lifecycle Management

Use this runbook for the governed ADR 0141 weekly audit path and for planned token rotations that are triggered by age rather than by an exposure incident.

## Repo-owned sources

- `config/token-policy.yaml` defines the canonical token classes, TTLs, warning windows, and exposure handling mode.
- `config/token-inventory.yaml` lists the currently governed tokens that must be audited.
- `scripts/token_lifecycle.py` performs validation, inventory audit, and hook-driven rotation or revocation.
- `receipts/token-lifecycle/` stores the generated audit receipts.

## Validate the contract

Run this before changing the token inventory or wiring new provider hooks:

```bash
uv run --with pyyaml python scripts/token_lifecycle.py validate
```

## Weekly inventory audit

Dry-run the report locally:

```bash
uv run --with pyyaml python scripts/token_lifecycle.py audit --print-report-json
```

If the report shows expired tokens and the inventory entry has a rotation hook, the overdue remediation path can be exercised with:

```bash
uv run --with pyyaml python scripts/token_lifecycle.py audit --execute-remediations --dry-run --print-report-json
```

The Windmill wrapper for the same flow is:

```bash
python3 config/windmill/scripts/audit-token-inventory.py --repo-path /srv/proxmox_florin_server --dry-run
```

## Planned rotation

Rotate one governed token through its configured hook contract:

```bash
uv run --with pyyaml python scripts/token_lifecycle.py rotate --token-id windmill-superadmin-token --dry-run --print-report-json
```

If the token inventory only defines the workflow identifier and not an executable hook yet, the command will return a blocked or planned result instead of silently pretending the token was rotated.

## Expected outcomes

- a receipt is written under `receipts/token-lifecycle/`
- the mutation ledger file receives a `secret.audited` event for every inventory audit
- successful hook-backed rotations emit `secret.rotated`
