# Workstream ADR 0042: step-ca For SSH And Internal TLS

- ADR: [ADR 0042](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0042-step-ca-for-ssh-and-internal-tls.md)
- Title: Internal certificate authority for SSH and private TLS
- Status: merged
- Branch: `codex/adr-0042-step-ca`
- Worktree: `../proxmox_florin_server-step-ca`
- Owner: codex
- Depends On: `adr-0014-tailscale`
- Conflicts With: none
- Shared Surfaces: `docker-runtime-lv3`, SSH trust, internal TLS

## Scope

- choose the internal CA app and trust model
- define SSH and X.509 boundaries for humans, agents, services, and hosts
- document the private-only publication and bootstrap expectations

## Non-Goals

- replacing the current public Let's Encrypt edge

## Expected Repo Surfaces

- `docs/adr/0042-step-ca-for-ssh-and-internal-tls.md`
- `docs/workstreams/adr-0042-step-ca.md`
- `docs/runbooks/configure-step-ca.md`
- `docs/runbooks/plan-agentic-control-plane.md`
- `playbooks/step-ca.yml`
- `roles/step_ca_runtime/`
- `roles/step_ca_ssh_trust/`
- `config/controller-local-secrets.json`
- `config/workflow-catalog.json`
- `workstreams.yaml`

## Expected Live Surfaces

- no direct live apply in this integration step
- a ready-to-run `step-ca` converge path for later controlled rollout

## Verification

- `make syntax-check-step-ca`
- `make workflow-info WORKFLOW=converge-step-ca`
- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`

## Merge Criteria

- the repo has a coherent `step-ca` converge path with documented bootstrap artifacts and trust boundaries
- the workstream records the trusted surfaces and dependencies clearly

## Notes For The Next Assistant

- keep the first implementation private-only
- avoid mixing public edge work into the CA rollout
- apply the workflow live only after the short-lived credential rollout and recovery expectations are explicitly approved
