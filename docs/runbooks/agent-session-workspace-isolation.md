# Agent Session Workspace Isolation

## Purpose

ADR 0156 defines the per-session workspace contract used by controller automation and the remote build gateway.

Use this runbook when you need to:

- understand which local and remote paths a session will use
- force a human-readable session namespace for a live test or debugging session
- troubleshoot concurrent controller runs that should stay isolated

## Repository Surfaces

- `scripts/session_workspace.py`
- `scripts/remote_exec.sh`
- `scripts/run_gate.py`
- `platform/scheduler/watchdog.py`
- `platform/ledger/writer.py`
- `scripts/live_apply_receipts.py`

## Session Model

Each session resolves:

- `LV3_SESSION_ID`: explicit identifier if the caller sets one
- `LV3_SESSION_SLUG`: normalized path-safe / subject-safe identifier
- `LV3_SESSION_LOCAL_ROOT`: session-local runtime state root
- `LV3_SESSION_NATS_PREFIX`: `platform.ws.<session_slug>`
- `LV3_SESSION_STATE_NAMESPACE`: `ws:<session_slug>`
- `LV3_SESSION_RECEIPT_SUFFIX`: normalized receipt suffix

The remote build gateway uses:

```text
<workspace_root>/.lv3-session-workspaces/<session_slug>/repo
```

Each immutable remote run then expands beneath that stable session root as:

```text
<workspace_root>/.lv3-session-workspaces/<session_slug>/repo/.lv3-runs/<run_id>/repo
```

The default local state root is:

```text
.local/session-workspaces/<session_slug>
```

## Inspect A Session Workspace

Show the resolved session metadata for the current checkout:

```bash
python3 scripts/session_workspace.py --repo-root .
```

Inspect the shell assignments that `scripts/remote_exec.sh` consumes:

```bash
python3 scripts/session_workspace.py --repo-root . --remote-workspace-base /home/ops/builds/proxmox-host_server --format shell
```

## Run With An Explicit Session ID

For ad hoc debugging or live verification, pin a readable session id:

```bash
LV3_SESSION_ID=adr-0156-live make check-build-server
LV3_SESSION_ID=adr-0156-live make remote-lint
```

That same `LV3_SESSION_ID` will flow into:

- the remote build-server checkout path
- the immutable remote run namespace path
- remote shell and remote Docker environments
- validation-gate status payload metadata
- scheduler state-store default paths when the tool is session-aware
- ledger metadata and session-suffixed generated live-apply receipts

## Cleanup Model

The build gateway prunes stale remote session directories older than two days during normal remote runs. It also keeps a bounded number of remote session roots, run namespaces, and uploaded snapshot archives so the shared build VM does not fill up during heavy parallel work.

If you must remove one manually:

```bash
ssh -i .local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes \
  -o ProxyCommand='ssh -i .local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes ops@100.64.0.1 -W %h:%p' \
  ops@10.10.10.30 \
  'rm -rf /home/ops/builds/proxmox-host_server/.lv3-session-workspaces/<session_slug>'
```

Only remove a session directory after confirming no active remote command still uses it.

## Troubleshooting

- If two sessions still collide on the build server, verify they are not reusing the same `LV3_SESSION_ID`.
- If a remote tool writes session-local state to an unexpected path, inspect the exported `LV3_SESSION_LOCAL_ROOT` in the remote command log.
- If you need deterministic naming for a live test, always set `LV3_SESSION_ID` explicitly rather than relying on the checkout-derived fallback.
