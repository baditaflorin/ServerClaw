# Configure Repowise

## Purpose

This runbook covers the repo-managed Repowise semantic code search service
introduced by [ADR 0346](../adr/0346-repowise-semantic-search.md).

## Entry Points

- governed live apply: `make live-apply-service service=repowise env=production`
- direct playbook: `ansible-playbook playbooks/repowise.yml -i inventory/hosts.yml --limit docker-runtime`

## Fresh Worktree Notes

- run from the exact worktree you want mirrored into the Repowise index corpus
- the governed wrapper now resolves the shared `.local/identity.yml` overlay from
  the main repo root, so a fresh `.worktrees/...` checkout can use the normal
  `make live-apply-service` path without creating a worktree-local `.local/`
- `make preflight WORKFLOW=live-apply-service` still materializes the shared
  bootstrap key aliases before the live replay starts

## Live Apply

```bash
make preflight WORKFLOW=live-apply-service
make live-apply-service service=repowise env=production
```

## Verification

Run the checks from the controller after the replay:

```bash
ssh -i "$(./scripts/resolve_local_overlay_root.sh)/ssh/bootstrap.id_ed25519" \
  -o StrictHostKeyChecking=no ops@10.10.10.20 \
  'curl -fsS http://127.0.0.1:7070/health'
```

```bash
ssh -i "$(./scripts/resolve_local_overlay_root.sh)/ssh/bootstrap.id_ed25519" \
  -o StrictHostKeyChecking=no ops@10.10.10.20 \
  'curl -fsS -H "Content-Type: application/json" http://127.0.0.1:7070/search \
     -d '"'"'{"query":"repowise service", "limit":3}'"'"''
```

Confirm the service also answers through the published route recorded in the
service catalog:

```bash
python3 scripts/service_id_resolver.py --show repowise
```

## Operational Notes

- the service runs on `docker-runtime` and stores vectors in the shared Qdrant
  deployment used by ADR 0198
- the Repowise runtime mirrors the current repo checkout into `/opt/repowise/repo`
  during converge, so replay from the branch or exact-main tree whose corpus you
  actually want indexed
- nightly rebuilds run from cron at `03:00`
