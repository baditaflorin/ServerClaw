# Configure Ntfy

## Purpose

This runbook converges the published `ntfy` push channel defined by ADR 0299.

It delivers:

- a repo-managed `ntfy` container on `docker-runtime-lv3`
- the governed topic registry in `config/ntfy/topics.yaml`
- repo-managed publisher and subscriber credentials mirrored under `.local/ntfy/`
- a public edge-published endpoint at `https://ntfy.lv3.org`

## Entrypoints

- syntax check: `make syntax-check-ntfy`
- converge: `make converge-ntfy`
- governed service replay: `make live-apply-service service=ntfy env=production`

## Managed Artifacts

- runtime directory: `/opt/ntfy`
- server config: `/opt/ntfy/server.yml`
- data directory: `/var/lib/ntfy`
- topic registry: `config/ntfy/topics.yaml`
- controller-local secret directory: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ntfy/`

Generated controller-local artifacts:

- `alertmanager-password.txt`
- `ansible-password.txt`
- `ansible-token.txt`
- `changedetection-password.txt`
- `gitea-actions-password.txt`
- `gitea-actions-token.txt`
- `ops-password.txt`
- `windmill-password.txt`
- `windmill-token.txt`

## Verification

1. `make syntax-check-ntfy`
2. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'docker compose --file /opt/ntfy/docker-compose.yml ps'`
3. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'curl -fsS http://127.0.0.1:2586/v1/health'`
4. `curl -fsS https://ntfy.lv3.org/v1/health`
5. `python3 scripts/ntfy_publish.py --publisher ansible --topic platform-ansible-info --message 'ADR 0299 verification publish' --sequence-id ws-0299-verify-ansible-info --dedupe-state-file .local/state/ntfy/runbook-verify.json --dedupe-window-seconds 1`
6. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'sudo python3 - <<'"'"'"'"'"'"'"'"'PY'"'"'"'"'"'"'"'"'\nimport sqlite3\nconn = sqlite3.connect(\"/var/lib/ntfy/cache.db\")\ncur = conn.cursor()\nprint({\"platform-security-critical_count\": cur.execute(\"select count(*) from messages where topic=\\'platform-security-critical\\'\").fetchone()[0]})\nPY'`

## Governed Topics

- `platform-monitoring-critical` for Alertmanager critical operator push delivery
- `platform-security-warn` for Changedetection advisories and SBOM delta notifications
- `platform-backup-critical` for restic freshness and restore-readiness failures
- `platform-security-critical` for critical security findings forwarded by the Windmill bridge and the private Falco bridge
- `platform-watchdog-critical` for watchdog escalations from the Windmill bridge
- `platform-ansible-info`, `platform-ansible-warn`, and `platform-ansible-critical` for governed playbook notifications
- `platform-ci-critical` for Gitea validation failures
- `platform-slo-warn` for k6 or SLO warning publication

Compatibility topics retained during rollout:

- `platform-alerts`
- `platform-alerts-sbom-verify`

## Notes

- `scripts/ntfy_publish.py` is the preferred publication path for repo-managed publishers because it validates topic registration, publisher authorization, and controller-local auth material before sending.
- `scripts/ntfy_publish.py` normalizes logical `--sequence-id` values into ntfy-safe identifiers because ntfy accepts only `[-_A-Za-z0-9]{1,64}` for sequence IDs.
- Declarative `auth-users`, `auth-tokens`, and `auth-access` entries are applied into ntfy's `user.db` on container startup, so repo-managed auth changes require a container recreate rather than a bare health check.
- If ntfy startup fails with Docker publication errors such as `Unable to
  enable DNAT rule`, rerun the repo-managed converge rather than patching the
  host by hand; the role now restarts Docker, reasserts bridge chains, and
  retries the ntfy stack automatically.
- Keep the repo-managed ntfy image at or above the live schema level already
  recorded in `/var/lib/ntfy`. Replaying an older image against a newer schema
  causes the container to crash-loop before the health check can recover it.
- Keep ntfy topics hyphenated when their corresponding event or NATS subject is
  dotted. The live ntfy runtime rejected dotted topic patterns during replay,
  including `platform.security.critical` and `platform.slo.warn`.
- Treat `.local/ntfy/` as secret material and keep it outside git.
- If a publisher still uses a compatibility topic or direct basic-auth publish path, keep that exception documented until it is migrated onto the governed registry helper.
