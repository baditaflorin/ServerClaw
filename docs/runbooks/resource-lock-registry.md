# Distributed Resource Lock Registry

## Purpose

Operate and verify the ADR 0153 resource lock registry that coordinates concurrent platform mutations.

## Canonical Sources

- [platform/locking/registry.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/locking/registry.py)
- [platform/locking/schema.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/locking/schema.py)
- [scripts/resource_lock_tool.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/resource_lock_tool.py)
- [docs/adr/0153-distributed-resource-lock-registry.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0153-distributed-resource-lock-registry.md)
- [docs/workstreams/adr-0153-distributed-resource-lock-registry.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0153-distributed-resource-lock-registry.md)

## Current Implementation

- The first repository implementation is worker-shared and file-backed, not JetStream-backed.
- The state file defaults to `$(git rev-parse --git-common-dir)/lv3-concurrency/lock-registry.json` when the checkout is inside a git worktree.
- Outside a git checkout, or when git metadata is unavailable, the fallback path is `.local/state/lv3-concurrency/lock-registry.json`.
- Set `LV3_LOCK_REGISTRY_PATH` or pass `--state-path` to force a specific state file during tests or local troubleshooting.
- Locks are TTL-bounded and hierarchical, so `vm:120` conflicts with `vm:120/service:netbox` in both directions.

## Primary Commands

Ensure the shared state file exists and is writable:

```bash
make ensure-resource-lock-registry
```

List active locks:

```bash
make resource-locks
```

Acquire one lock:

```bash
make resource-lock-acquire RESOURCE='vm:130/service:netbox' HOLDER='agent:ops-demo' LOCK_TYPE=exclusive TTL_SECONDS=300 CONTEXT_ID='ctx-demo'
```

Release one lock:

```bash
make resource-lock-release RESOURCE='vm:130/service:netbox' HOLDER='agent:ops-demo'
```

Refresh one lock TTL:

```bash
make resource-lock-heartbeat LOCK_ID='<lock-id>' TTL_SECONDS=300
```

## Verification

1. Run `make ensure-resource-lock-registry`.
2. Acquire a smoke-test lock with `make resource-lock-acquire RESOURCE='vm:120/service:resource-lock-smoke' HOLDER='agent:adr-0153-smoke' LOCK_TYPE=exclusive TTL_SECONDS=120`.
3. Confirm the holder appears in `make resource-locks`.
4. Release it with `make resource-lock-release RESOURCE='vm:120/service:resource-lock-smoke' HOLDER='agent:adr-0153-smoke'`.
5. Confirm `make resource-locks` returns an empty list or no smoke-test entry.

## Troubleshooting

- If the wrong checkout is being inspected, print the resolved state path with `python3 scripts/resource_lock_tool.py list`.
- If a stale lock blocks progress, wait for the TTL to expire or release it explicitly by `lock_id`, `resource`, and/or `holder`.
- If the live platform is unreachable, keep `Implemented In Platform Version` unset and treat the repository implementation as merged but not live-applied.
