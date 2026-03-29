# Repo-Deploy Base Image Cache

## Purpose

ADR 0274 governs the approved base-image path for repo-backed application
deployments. The current live implementation lands on `coolify-lv3` and adds:

- a repo-managed base-image profile catalog for approved deployment lanes
- a guest-local warm plan under `/opt/repo-deploy-image-cache/seed-plan.json`
- a durable warm receipt under `/opt/repo-deploy-image-cache/warm-status.json`
- a scheduled refresh via `lv3-repo-deploy-image-cache.timer`

This runbook covers the deployment-lane warm-cache surface. ADR 0295 remains the
separate shared artifact-cache plane for the build host.

## Repository Surfaces

- playbook entrypoint: `playbooks/coolify.yml`
- role: `collections/ansible_collections/lv3/platform/roles/repo_deploy_image_cache/`
- approved profile catalog: `config/repo-deploy-base-image-profiles.json`
- helper: `scripts/repo_deploy_image_cache.py`

## Converge The Cache Surface

Replay the governed Coolify service wrapper:

```bash
make live-apply-service service=coolify env=production
```

Expected outcomes on `coolify-lv3`:

- `/opt/repo-deploy-image-cache/catalog.json` matches the committed profile catalog
- `/opt/repo-deploy-image-cache/seed-plan.json` exists and lists the approved warm set
- `/opt/repo-deploy-image-cache/warm-status.json` exists and reports `result: pass`
- `lv3-repo-deploy-image-cache.timer` is enabled and active

## Inspect The Approved Warm Plan

Render the current plan locally from the committed catalog:

```bash
python3 scripts/repo_deploy_image_cache.py plan \
  --catalog config/repo-deploy-base-image-profiles.json
```

Validate the catalog itself:

```bash
python3 scripts/repo_deploy_image_cache.py validate \
  --catalog config/repo-deploy-base-image-profiles.json
```

## Verify The Guest Runtime

Check the timer, plan, and receipt on `coolify-lv3`:

```bash
ansible -i inventory/hosts.yml coolify-lv3 -m shell \
  -a 'systemctl is-active lv3-repo-deploy-image-cache.timer && sudo python3 /usr/local/bin/lv3-repo-deploy-image-cache.py verify --plan-file /opt/repo-deploy-image-cache/seed-plan.json --receipt-file /opt/repo-deploy-image-cache/warm-status.json --required --max-age-seconds 86400' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Inspect the current guest-local receipt:

```bash
ansible -i inventory/hosts.yml coolify-lv3 -m shell \
  -a 'sudo cat /opt/repo-deploy-image-cache/warm-status.json' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Operational Notes

- extend the approved warm set by editing `config/repo-deploy-base-image-profiles.json`, not by warming ad hoc image refs on the guest
- the current approved profile is derived from the live `education_wemeshup` deployment lane and should be expanded through review as new governed repo profiles are admitted
- the warm receipt is the operational proof of freshness; if the receipt ages past the approved bound, replay the Coolify converge path or run the verification command above before new production repo deploys
