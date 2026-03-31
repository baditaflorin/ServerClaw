# Token Exposure Response

Use this runbook when a governed API token is suspected to have been exposed in logs, git history, screenshots, browser copy-paste, or chat.

## Inputs

- `token_id`: canonical identifier from `config/token-inventory.yaml`
- `exposure_source`: where the token was exposed, for example `git_diff`, `log`, `mattermost`, or `screenshot`
- `notes`: optional incident notes

## Dry-run the response

```bash
uv run --with pyyaml python scripts/token_lifecycle.py exposure-response \
  --token-id keycloak-agent-hub-client-secret \
  --exposure-source git_diff \
  --notes "Secret appeared in a local debug diff" \
  --dry-run \
  --print-report-json
```

## Execute the response

```bash
uv run --with pyyaml python scripts/token_lifecycle.py exposure-response \
  --token-id keycloak-agent-hub-client-secret \
  --exposure-source git_diff \
  --notes "Secret appeared in a local debug diff" \
  --print-report-json
```

The Windmill wrapper for the same path is:

```bash
python3 config/windmill/scripts/token-exposure-response.py \
  --repo-path /srv/proxmox_florin_server \
  --token-id keycloak-agent-hub-client-secret \
  --exposure-source git_diff \
  --dry-run
```

## What the workflow does

1. Resolves the governed token record from `config/token-inventory.yaml`.
2. Captures the exposure window from a configured usage-audit hook, or derives it from repo metadata when no hook exists yet.
3. Revokes the token immediately through the configured hook contract.
4. Issues a replacement token when a rotation hook exists.
5. Invalidates sessions when the token policy requires it.
6. Writes an incident receipt under `receipts/security-incidents/` for CLI runs, or under `.local/token-lifecycle/incidents/` from the Windmill wrapper, and emits ledger events for revocation and incident creation.

## Operator notes

- A missing hook is treated as a blocking result, not as success.
- `platform_cli_token` records require session invalidation when exposed.
- `openbao_api_token` records are treated as already expired by policy and therefore skip explicit revocation.
