# Docker Publication Assurance Runbook

## Purpose

This runbook defines the ADR 0270 workflow that proves Docker-hosted services
still have the expected bridge networks, host-side port bindings, and listener
reachability before readiness is treated as healthy.

## Primary Command

Run the shared convergence playbook from the repository root:

```bash
make converge-docker-publication-assurance env=production
```

That replay targets `docker-runtime-lv3` and `coolify-lv3`, installs the
repo-managed helper at `/usr/local/bin/lv3-docker-publication-assurance`, and
replays every service contract in
[config/health-probe-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/health-probe-catalog.json)
that declares `readiness.docker_publication`.

Service-specific converges also stage a transient copy of the current
repo-managed helper before readiness verification so a stale installed helper
cannot block an otherwise valid live apply.

## What The Helper Verifies

- the declared container still exists
- required Docker bridge networks are attached
- expected host-side port bindings are programmed
- Docker NAT and forward chains exist when the runtime mode requires them
- the intended listener answers on the declared host and port

If `--heal` is enabled, the helper may:

- restart Docker when the publication chains are missing
- restart Docker and retry the compose recreate when `docker compose up` dies
  with a daemon transport EOF during publication recovery
- force-reset the compose project when host-side port programming is still
  missing after a recreate attempt or when Docker reports restarting, zombie,
  or name-conflict container state for the affected service
- remove and rebuild the compose network when Docker reports
  `failed programming external connectivity`, `Unable to enable DNAT rule`, or
  `No chain/target/match by that name` while restoring a published port

## Direct Operator Invocation

The helper can also be run directly on a managed Docker guest:

```bash
sudo /usr/local/bin/lv3-docker-publication-assurance \
  --service-id keycloak \
  --service-probe-base64 '<base64-json>' \
  --contract-base64 '<base64-json>' \
  --heal \
  --allow-listener-warmup-after-heal
```

The repo-managed playbooks generate those base64 payloads automatically; use
manual invocation only for debugging or a focused recovery.

## Validation

Run the focused repository validation slices after changing the contract model
or the helper logic:

```bash
uv run --with pytest --with pyyaml python -m pytest \
  tests/test_docker_publication_assurance.py \
  tests/test_docker_publication_assurance_playbook.py \
  tests/test_docker_runtime_role.py \
  tests/test_platform_observation_tool.py \
  tests/test_post_verify_tasks.py -q
./scripts/validate_repo.sh agent-standards yaml json data-models ansible-syntax role-argument-specs health-probes
```

## Notes

- Prefer contract fixes in `config/health-probe-catalog.json` over one-off
  manual Docker or iptables edits.
- If a full helper replay succeeds but one service still shows the stale
  `HostConfig.PortBindings`-without-live-`NetworkSettings.Ports` signature,
  rerun that service's repo-managed converge playbook so the service-specific
  role can perform its controlled compose reset path before resorting to
  manual Docker commands.
- If a service binds only on the guest IP and not loopback, declare the guest
  IP explicitly under `readiness.docker_publication.bindings`.
- If the application readiness probe intentionally targets a different port than
  the published service port, set `derive_bindings_from_probes: false` and
  declare the explicit bindings the publication contract should enforce.
