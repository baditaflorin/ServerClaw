# ADR 0431: retired-deployment Full-Day Deployment — Single-Command IaC Entry Point

- Status: Accepted
- Implementation Status: Complete (orchestrator playbook + Make targets + runbook)
- Date: 2026-04-21
- Concern: forkability, operator-onboarding, one-command-deploy, iac-end-to-end
- Tags: retired-deployment, fork-clone, full-day-deploy, iac, orchestrator, adr-0424-extension
- Relates to:
  - ADR 0407 (`.local/` deployment values — scalar overlay)
  - ADR 0424 (example.org clone on Hetzner AX41-NVMe)
  - ADR 0425 (420-ADR retrospective — forkability gap)
  - ADR 0430 (`.local/host_vars/proxmox-host.yml` overlay)

---

## Context

ADR 0424 decomposed the retired-deployment clone into an 11-step execution order, and ADR
0430 closed the last substrate gap (host_vars overlay) that prevented a fork
operator from reusing the committed codebase unchanged. All the primitives
now exist:

- `playbooks/proxmox-install.yml` orchestrates the host-level install (repo,
  kernel, platform, access, **network** → Hetzner WAN bridge via
  `proxmox_network`, tailscale, **headscale**, guests, security).
- `playbooks/site.yml` chains proxmox-install → groups/access → data →
  security → observability → automation → communication → platform-apps.
- `playbooks/mail-platform-send-gmail.yml` sends the acceptance-test email
  to `{{ platform_operator_email }}` through the platform transactional
  gateway on `runtime-control`.
- `env=clone` is wired through `inventory/group_vars/all/main.yml`
  (`playbook_execution_allowed_envs`).
- `.local/identity.yml.retired-deployment` + `.local/host_vars/proxmox-host.yml` supply
  the fork-specific scalars and topology.

What is **missing** is the outer wrapper that binds these primitives into a
single operator action. An operator staring at the repo today can:

1. Read ADR 0424 + the Hetzner bootstrap runbook and execute the 11 steps
   by hand.
2. Assemble a bespoke one-off script that nobody else can re-run.

Neither proves the fork is truly one-command. The forkability claim from
ADR 0385 / 0407 / 0424 / 0430 is only credible if a new operator can type
**one command** and reach a confirmation email in their inbox.

## Decision

Ship a single orchestrator target — `make deploy-retired-deployment` — that chains the
existing IaC primitives in the ADR 0424 order, under `env=clone`, reading
the fork overlay files from `.local/`. No new substrate; only a wrapper.

### Surface

| Target | Purpose |
|--------|---------|
| `make deploy-retired-deployment` | End-to-end: preflight → install-proxmox → site converge → smoke mail |
| `make converge-retired-deployment-chain` | Re-run just the service converge chain (idempotent replays after overlay edits) |
| `make preflight-retired-deployment` | Dry-run validation (DNS token, SSH key, overlay presence, kvm support) |
| `make smoke-retired-deployment-mail` | Standalone acceptance test — sends operator@example.org → operator@example.com |
| `make rotate-hetzner-dns-token` | Token rotation (ADR 0424 resolution item 7) |

All targets are thin Makefile shims around `playbooks/retired-deployment-full-day.yml`
(the orchestrator playbook) and the existing per-service playbooks.

### Orchestrator playbook

`playbooks/retired-deployment-full-day.yml` is a meta-playbook (`import_playbook:` only)
that pins the execution order:

```yaml
- import_playbook: proxmox-install.yml      # host + Hetzner bridge + headscale + guests
- import_playbook: site.yml                  # full service convergence under env=clone
- import_playbook: mail-platform-send-gmail.yml  # acceptance test
```

No new role-level logic. Each imported playbook already respects
`env=clone`, `.local/identity.yml.retired-deployment`, and the host_vars overlay.

### Overlay resolution

`make deploy-retired-deployment` sets two environment variables before invocation:

```bash
PLATFORM_IDENTITY_OVERLAY ?= .local/identity.yml.retired-deployment
env := clone
```

Operators can override `PLATFORM_IDENTITY_OVERLAY` for additional fork
deployments (`.local/identity.yml.<name>`). The default keeps the retired-deployment case
one-command.

### Acceptance

`make smoke-retired-deployment-mail` succeeds ⇔ the full deploy succeeded. The target
invokes `mail-platform-send-gmail.yml`, which requires:

1. `runtime-control` VM reachable (proves proxmox-install + guests converged)
2. `mail-platform` VM running Stalwart (proves site converge reached the
   mail stack)
3. DNS records published for the fork domain (proves Hetzner DNS integration
   used the overlay token + zone)
4. Platform transactional gateway on `runtime-control` accepting
   `POST /send` (proves API gateway + openbao-agent rendered secrets)

If any precondition fails, the smoke target fails loudly at that boundary.
This is intentional — a green `deploy-retired-deployment` is load-bearing evidence.

## Consequences

### Positive
- **Forkability is now demonstrably one-command.** The previous 11-step
  manual sequence collapses to a single target with explicit acceptance.
- **Every step remains independently re-runnable.** `converge-retired-deployment-chain`
  is idempotent; operators can iterate on service converges without
  re-running install-proxmox.
- **No new substrate, no new roles.** The orchestrator is pure composition,
  so existing per-service tests keep it honest.
- **Preflight-retired-deployment catches classic fork regressions**: missing overlay,
  stale DNS token, absent bootstrap key, `/dev/kvm` missing on the host.

### Negative
- `deploy-retired-deployment` is a long-running target (all services converge serially).
  Partial failures require the operator to re-invoke the specific
  sub-target; the orchestrator does not checkpoint progress.
- The orchestrator hardcodes `env=clone`. Using it against a different
  environment label requires editing the target (intentional — the clone
  env is the only supported single-command fork flow today).

### Neutral
- Production deployments do not use this entry point; `env=production`
  operators continue to run per-service `converge-*` targets. This ADR
  is additive.

## Alternatives considered

1. **Bash wrapper script** (`scripts/deploy-retired-deployment.sh`) — rejected. Make
   targets are the platform's canonical operator surface; every other
   lifecycle action is a Make target. A bash script would be a second
   parallel orchestration layer.
2. **Ansible role that runs ansible-playbook inside itself** — rejected.
   Nested ansible invocations break preflight assumptions and obscure
   per-step error reporting.
3. **CI workflow as the entry point** — rejected. Fork operators may not
   have CI yet; the entry point must work from a laptop with the repo
   checked out.
4. **Tie deploy-retired-deployment into the pre-push gate** — rejected. The gate is a
   branch-protection check; a multi-hour bare-metal deploy cannot gate
   every push. Smoke-retired-deployment-mail is the right post-deploy gate; it runs on
   demand.

## Verification

- `make preflight-retired-deployment` on a clean clone of the repo returns 0 when
  `.local/identity.yml.retired-deployment`, `.local/host_vars/proxmox-host.yml`,
  `.local/hetzner/dns.env`, and `.local/ssh/hetzner_llm_agents_ed25519`
  are all present and valid.
- `make smoke-retired-deployment-mail` on a fully-deployed clone delivers an email to
  `operator@example.com` (observed in the operator's Gmail inbox).
- The orchestrator playbook `ansible-playbook --syntax-check` passes.
- `playbooks/retired-deployment-full-day.yml` is listed in
  `playbook_execution_allowed_envs` registry and picked up by
  `scripts/ansible_scope_runner.py` under `env=clone`.

## Cross-references

- ADR 0407 — `.local/identity.yml` scalar overlay
- ADR 0424 — The 11-step ordered plan this ADR collapses
- ADR 0425 — Retrospective that identified the "one-command fork" gap
- ADR 0430 — `.local/host_vars/proxmox-host.yml` overlay (the last
  missing substrate piece)
- Runbook: [docs/runbooks/retired-deployment-full-day-deploy.md](../runbooks/retired-deployment-full-day-deploy.md)
