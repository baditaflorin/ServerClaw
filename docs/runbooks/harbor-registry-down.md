# Runbook: Harbor Registry Down

## Severity

medium (blocks gate checks and image builds; does not affect running services)

## Symptoms

- `git push origin main` fails with gate errors
- Docker pull errors: `502 Bad Gateway` from `registry.lv3.org`
- Gate checks show `runner_unavailable` for all Docker-based checks
- Build server cannot pull `registry.lv3.org/check-runner/python:3.12.10`

## What Harbor Blocks When Down

| Blocked | Not blocked |
|---------|-------------|
| Pre-push gate Docker checks | Running services (they use already-pulled images) |
| Building new Docker images | Ansible converge runs |
| Pulling check-runner images | Git operations |
| CI/CD pipelines | SSH access to hosts |

Running services are unaffected — they only pull on first deploy or explicit update.

## Diagnosis

```bash
# Quick check from controller
curl -s -o /dev/null -w "%{http_code}" https://registry.lv3.org/v2/

# Expected: 200 or 401 (auth required = healthy)
# If 502: Harbor or its nginx upstream is down
# If connection refused: VM is down

# Check Harbor VM status on Proxmox
ssh root@10.10.10.1 "qm list | grep harbor"

# SSH to Harbor host and check compose
ssh ops@<harbor-ip>
cd /opt/harbor
docker compose ps
```

## Fix: Restart Harbor

```bash
# On Harbor host
cd /opt/harbor
sudo docker compose down && sudo docker compose up -d

# Wait ~60s for Harbor to become healthy
curl -s -o /dev/null -w "%{http_code}" https://registry.lv3.org/v2/
```

## Fix: Re-converge Harbor

```bash
ansible-playbook \
  collections/ansible_collections/lv3/platform/playbooks/services/build-artifact-cache.yml \
  -i inventory/hosts.yml
```

## Bypass Gate While Harbor Is Down

Use `runner_image_pull_failure` reason code. You must provide substitute evidence
(which checks passed locally) and a remediation reference:

```bash
SKIP_REMOTE_GATE=1 \
GATE_BYPASS_REASON_CODE=runner_image_pull_failure \
GATE_BYPASS_SUBSTITUTE_EVIDENCE="schema-validation+workstream-surfaces passed locally" \
GATE_BYPASS_DETAIL="Harbor registry.lv3.org returning 502" \
GATE_BYPASS_REMEDIATION_REF="restore-harbor-registry" \
git push origin main
```

Valid reason codes are in `config/gate-bypass-waiver-catalog.json`.

Run local checks manually before bypassing:
```bash
# Run the checks that Harbor blocks
./scripts/validate_repo.sh workstream-surfaces
./scripts/validate_repo.sh schema-validation
./scripts/validate_repo.sh ansible-syntax
```

## After Harbor Recovers

No action needed for running services. The next `git push` will use the gate normally.

If check-runner images are stale (new dependencies added), rebuild:
```bash
ansible-playbook \
  collections/ansible_collections/lv3/platform/playbooks/build-artifact-cache.yml \
  -i inventory/hosts.yml
```

## Related

- `docker-check-runners.md` — how check-runner images are built and managed
- `validation-gate.md` — full gate check reference
- `configure-harbor.md` — Harbor initial setup
