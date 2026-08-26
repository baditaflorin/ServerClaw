# ADR 0483: Hands-Off Bootstrap — Machine-to-Machine Deployment

**Status**: ACCEPTED
**Date**: 2026-05-12
**Decision**: A new deployment goes from "blank Proxmox host + DNS record + secret bag" to "verified-running platform" via a single machine-to-machine command. No human keystrokes between `make bootstrap` and the verified-up state. Every step is a contract the next step refuses to start without; every step ships its own machine-checkable post-condition (ADR 0484); the whole chain is idempotent (ADR 0485) and self-checking (`scripts/self_check.py`).

---

## Context

### Where we are after ADRs 0481 + 0482

- **ADR 0481** made deployment selection explicit (`make whoami`, per-deployment `.local/deployments/<slug>/`).
- **ADR 0482** made VM sizing capacity-aware (probe → resolve → topology.yml).

Both ADRs leave one structural gap: a human is still in the loop **between every step.** Today:

```
make new-deployment slug=mycorp apex=mycorp.com
# human edits identity.yml + connection.yml
make probe-capacity
# human reviews output
make resolve-topology
# human reviews diff
make bootstrap
# human watches Ansible output
# human curls registry.mycorp.com to see if it worked
# human files a workstream when it didn't
```

Every "human watches" / "human reviews" / "human checks" is a manual gate. Every gate is where a fork-attempt stalls when the operator goes to bed. Every gate is also where an agent can't pick up where another agent left off — because the gate's pass/fail state lives in a head, not in the repo.

### Why this matters strategically

The platform's promise is forkability. Real forkability means an operator can spin up a deployment overnight while they sleep. Real *agent-to-agent* forkability means agent A can hand off to agent B at 3am and B doesn't need to ask anyone whether step 5 finished cleanly. Both require the same primitive: **every step's success or failure must be machine-readable, and the chain must drive itself forward without prompting.**

This is the difference between "we have IaC" (the code that converges to a state exists) and "the IaC drives itself" (the code that decides whether to advance also exists). Today we have the first; this ADR adds the second.

### Why not just "use Ansible's idempotency, run it twice"

Idempotency tells you the converge *can* be re-run safely. It doesn't tell you:

1. Whether the previous run actually achieved the declared state. (Ansible exits 0 on tasks that "completed" but produced unverified output.)
2. Whether the step's external-facing contract holds. (`docker compose up -d` exits 0 even when one container has `Status: Exited` 5 minutes later. The 0fork Harbor incident is exactly this failure mode.)
3. Whether the deployment has drifted between converges. (No drift signal except a human noticing things look weird.)

We need explicit post-condition contracts (ADR 0484) and an idempotency check that asserts "no work would be done if we ran again" (ADR 0485) — Ansible's `changed_when` is a hint, not a contract.

---

## Decision

### 1. The deployment manifest is the single declarative input

A new file replaces the operator's hand-editing chain:

```
.local/deployments/<slug>/manifest.yml
```

Schema (excerpt — full schema at `config/contracts/deployment-v1/manifest.schema.json`):

```yaml
schema_version: 1
slug: mycorp
apex_domain: mycorp.com
operator:
  name: "Acme Corp Ops"
  email: ops@mycorp.com
provider:
  kind: hetzner
  host: 203.0.113.3
  port: 22
  initial_user: root
  initial_key_path: .local/ssh/hetzner_llm_agents_ed25519
profiles:
  - core
  - devtools
extra_services: []
disabled_services: []
secrets:
  source: openbao   # or "operator-stdin", "vault", "1password"
  reference: deployments/mycorp/secrets
gates:
  fail_fast: true          # abort chain on first post-condition failure
  max_retries_per_step: 3
  step_timeout_s: 1800
verification:
  smoke_endpoints:
    - https://registry.{apex}/api/v2.0/ping
    - https://sso.{apex}/realms/{apex_slug}/.well-known/openid-configuration
    - https://wiki.{apex}/
  expected_running_vms_count: ">= 5"
```

`manifest.yml` is the **only** file an operator authors. Everything else — `identity.yml`, `connection.yml`, `topology.yml`, `profile.yml`, `capacity.yml`, even the secret keys — is *derived* from manifest + probe + resolver + ADR-0441 service catalog.

### 2. `make bootstrap` is one command, end-to-end

```bash
make bootstrap deployment=mycorp
```

What this does, in order, with each step gating the next:

| Step | Pre-condition (must hold before) | Action | Post-condition (must hold after) |
|---|---|---|---|
| `0-derive` | `manifest.yml` exists and validates | Derive `identity.yml`, `connection.yml`, `profile.yml` from manifest | All three exist + schema-validate |
| `1-probe-capacity` | `connection.yml` valid, host SSH-reachable | Run `scripts/capacity_probe.py` | `capacity.yml` exists + schema-validates |
| `2-resolve-topology` | `capacity.yml` + `sizing-policy.yml` + `profile.yml` all valid | Run `scripts/resolve_topology.py` | `topology.yml` exists + total RAM ≤ usable host RAM |
| `3-init-remote` | Provider host reachable + provider-initial key works | Bootstrap `ops` sudoer, install ops pubkey | `ssh ops@<host>` succeeds with `bootstrap.id_ed25519` |
| `4-install-proxmox` | `3-init-remote` post-condition holds | Configure Proxmox host (firewall, repos, ZFS pools) | `pveversion` reports configured version + storage pool present |
| `5-provision-guests` | `topology.yml` valid | Create every VM in `topology.proxmox_guests` with sized memory + balloon + cores + disk | `qm list` shows every expected VM running |
| `6-harden-guests` | `5-provision-guests` post-condition holds | Per-guest hardening (ufw, ssh, automatic-updates) | Each guest passes a hardening lint |
| `7-converge-edge` | guest network policies in place | Run nginx + cert lifecycle | Public TLS endpoint on apex returns 200 / 308 |
| `8-converge-postgres` | postgres VM up | Bootstrap pg + roles | `psql -h <vm> -c "SELECT 1"` returns 1 |
| `9-converge-openbao` | postgres up | Bootstrap OpenBao | `openbao status` reports unsealed |
| `10-converge-keycloak` | openbao + postgres up | Bootstrap Keycloak | `.well-known/openid-configuration` returns valid issuer |
| `11-converge-services` | keycloak + openbao + postgres up | Converge every enabled service per profile | Each service's per-service post-condition holds |
| `12-final-smoke` | all of the above | Run every `verification.smoke_endpoints` URL | Each returns 200/308 with expected body fragment |
| `13-write-receipt` | `12-final-smoke` post-condition holds | Write the bootstrap receipt under `receipts/live-applies/<deployment>/...` | Receipt JSON validates against ADR 0420 receipt schema |

If **any** post-condition fails, the chain stops at that step. The receipt records which step failed, the exact output, and the post-condition that didn't hold. The next invocation re-enters at that step (idempotency, ADR 0485).

### 3. The "step contract" is a first-class object

Each step is declared in `config/bootstrap_steps.yml` (committed):

```yaml
steps:
  - id: 5-provision-guests
    make_target: provision-guests
    preconditions:
      - id: topology.valid
        type: schema
        target: .local/deployments/{slug}/topology.yml
        schema:  config/contracts/deployment-v1/topology.schema.json
    postconditions:
      - id: vms.all-running
        type: pveapi
        check: |
          for guest in topology.proxmox_guests:
              assert guest.name in `qm list --running`
      - id: vms.balloon-enabled
        type: pveapi
        check: |
          for guest in topology.proxmox_guests:
              assert qm_config(guest.vmid).balloon > 0
    timeout_s: 1800
    retries: 1
```

`scripts/self_check.py` consumes this file and runs the pre/postconditions. The same registry powers `make self-check` (which can be invoked after any state-changing step) and `make doctor` (drift signal aggregator, already exists).

### 4. Agent-to-agent handoff is a receipt, not a chat

When agent A finishes step N and step N+1 fails, agent A writes a structured failure receipt:

```
receipts/live-applies/<deployment>/<timestamp>-bootstrap-failure-step-<N+1>.json
```

containing:

- which step failed
- which post-condition failed
- the literal output of the failing check
- the slug + manifest hash + topology hash (so the next agent knows nothing drifted)
- a `next_action` field — what would unblock this step

Agent B reads the receipt and resumes:

```bash
make bootstrap deployment=mycorp resume-from=<step-N+1>
```

Whether agent B is a human, another Claude session, or a cron job is invisible to the chain. The receipt is the handoff.

### 5. The chain is observable from one place

`make bootstrap-status deployment=<slug>` reads:

- the latest receipt for the deployment
- runs `self-check` against current state
- emits a JSON status object: current step, last-passed step, current failing condition, time-since-last-progress

This is what an agent reads to decide "should I touch this deployment, or is it being worked on / is it healthy."

### 6. Two-way derivation for migration of existing deployments

For lv3 and 0fork, which exist today without a manifest:

```bash
make derive-manifest deployment=0fork  # introspects existing files, emits a draft manifest.yml
```

Once the draft is reviewed and committed (or symlinked), the deployment is hands-off-capable from that point forward.

### 7. Out of scope (for this ADR — punted to follow-ups)

- **Cross-deployment orchestration.** Bootstrap is per-deployment. A separate ADR will define how a fleet manager triggers bootstraps for N deployments in parallel.
- **Provider abstraction.** Today the chain assumes Proxmox-on-Hetzner. A `provider.kind` value of `hetzner` is honoured; `aws-bare-metal`, `oracle`, `local-mini-pc`, etc. become drivers in a future ADR.
- **Self-healing during steady state.** This ADR makes *bootstrap* hands-off. ADR 0485 covers idempotent re-runs. Active self-healing (notice drift, auto-remediate, write receipt) is a different beast and a future ADR.

---

## Consequences

### Positive

- **Wipe-and-reinstall is one command.** The "fresh Proxmox, give me example.org" flow becomes `gh repo clone … && cd … && operator drops manifest.yml && make bootstrap deployment=0fork`. No keystrokes between then and verified-up.
- **Failures are resumable.** Steps 1–13 are idempotent and gated by post-conditions; an interrupted run picks up where it left off.
- **Two agents can hand off work.** Receipts encode where the chain is, why it stopped, and what unblocks it. No chat-log archaeology.
- **The platform tests itself.** Every step's post-condition is a test. `make self-check` is "does the deployment match what its manifest says it should be." `make doctor` (which already exists) aggregates these signals.
- **Drift is impossible to ignore.** A passing `self-check` is required to consider a deployment "up." If something drifts, the next `self-check` flags it without anyone watching.

### Negative

- **Surface area grows.** New ADRs (0484, 0485), new schemas, new scripts (`self_check.py`, `derive_manifest.py`, `bootstrap_orchestrator.py`), new contract file (`config/bootstrap_steps.yml`).
- **Migration of existing deployments takes work.** lv3 and 0fork need `derive-manifest` runs and operator review before they're hands-off.
- **Bad post-conditions are worse than no post-conditions.** A flaky smoke endpoint blocks the chain on every run. Mitigation: post-conditions ship with explicit retry/backoff and timeout. Anything intermittent is a bug to be fixed in the check, not absorbed by an operator.

### Migration

1. Land ADR 0483 + 0484 + 0485 (this PR, design only).
2. Land `scripts/self_check.py` + `config/post_conditions.yml` (this PR, MVP — a small initial set of checks).
3. Land unit tests for the resolver + the self-check runner (this PR).
4. Future PRs: `derive_manifest.py`, `bootstrap_orchestrator.py`, the full `bootstrap_steps.yml`, retro-application to lv3 + 0fork.

---

## References

- ADR 0407 — Generic by default
- ADR 0420 — Receipt schema
- ADR 0440 — Per-deployment directory layout
- ADR 0441 — Service profiles
- ADR 0450 — Drift signals + `make doctor`
- ADR 0481 — Explicit deployment context (the prerequisite)
- ADR 0482 — Capacity-aware dynamic VM sizing (the prerequisite)
- ADR 0484 — Self-verification contracts (the partner)
- ADR 0485 — Convergence idempotency tests (the partner)
- Postmortem: 2026-05-11 0fork Harbor 502 — the load-bearing motivator for ADR 0484
