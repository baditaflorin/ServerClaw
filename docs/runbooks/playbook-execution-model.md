# Playbook Execution Model

## Purpose

This runbook documents the shared playbook execution model introduced by ADR 0079.

The model adds:

- environment-aware host selection via `env=<production|staging>`
- shared preflight checks in [playbooks/tasks/preflight.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/tasks/preflight.yml)
- shared post-apply verification in [playbooks/tasks/post-verify.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/tasks/post-verify.yml)
- group entry points under [playbooks/groups/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/groups)
- service entry points under [playbooks/services/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/services)

## Entry Points

Use the new generic Make targets for the decomposed model:

```bash
make live-apply-group group=observability env=production
make live-apply-service service=grafana env=production
make live-apply-site env=production
```

The legacy top-level playbooks remain in place and still work. They now either import the decomposed service playbooks or use the shared task files directly.

Before the generic `live-apply-group`, `live-apply-service`, `live-apply-site`, and `live-apply-waves` wrappers enter their interface, redundancy, or Ansible execution checks, they now call the controller-local bootstrap preflight. That bootstrap step can materialize declared generated artifacts such as the shared edge portal directories before the live replay starts.

## Environment Resolution

`env` defaults to `production`.

Supported values:

- `production`
- `staging`

The active host patterns live in [inventory/group_vars/all.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/group_vars/all.yml) under `playbook_execution_host_patterns`. Inventory contains staged host placeholders so the playbooks remain syntax-checkable and targetable before the staging topology is live.

## Shared Preflight

`playbooks/tasks/preflight.yml` performs these checks:

- validates that `env` is one of the allowed environment ids
- validates that referenced controller-local secret ids exist in [config/controller-local-secrets.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/controller-local-secrets.json)
- validates that required inventory hosts exist
- verifies SSH reachability for declared required hosts
- asserts Debian targets when requested by the caller
- emits a best-effort mutation audit start event if the audit helper exists

## Shared Post-Verify

`playbooks/tasks/post-verify.yml` loads [config/health-probe-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/health-probe-catalog.json), executes the declared liveness probe, optionally repairs any declared Docker publication contract, and then runs the readiness probe for the service being converged.

Current probe kinds:

- `http`
- `tcp`
- `command`
- `systemd`

If `readiness.docker_publication` is present for a Docker-hosted service, `playbooks/tasks/docker-publication-assert.yml` runs `/usr/local/bin/lv3-docker-publication-assurance` on the owning guest before readiness is allowed to pass. That helper verifies the declared bridge networks, host-side port bindings, and listener reachability, and it may repair missing Docker publication primitives before the normal readiness probe runs.

The current catalog covers the priority services wired into this workstream:

- `grafana`
- `openbao`
- `step_ca`
- `windmill`
- `mail_platform`

## Notifications

`playbooks/tasks/notify.yml` is optional and best-effort.

If these vars are set, it will emit a completion message:

- `playbook_execution_mattermost_webhook_url`
- `playbook_execution_nats_notify_command`

If neither is set, the task file is effectively a no-op.

## Validation

Run the repository gate after changing playbooks:

```bash
make validate
```

Useful syntax checks:

```bash
make syntax-check
make live-apply-service service=grafana env=staging EXTRA_ARGS=--syntax-check
make live-apply-group group=observability env=staging EXTRA_ARGS=--syntax-check
```

## Notes

- `playbooks/site.yml` is now the full convergence entry point for the decomposed playbook graph.
- The legacy host bootstrap targets continue to call `playbooks/proxmox-install.yml` directly so existing tag-based host provisioning semantics do not change.
- Mutation audit emission is best-effort. Missing Loki settings or a missing local sink does not block the playbook.
