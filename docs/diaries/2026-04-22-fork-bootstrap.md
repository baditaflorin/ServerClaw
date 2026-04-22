# Fork-Operator Diary — 2026-04-22

**Author:** claude (session on branch `claude/gallant-chebyshev-b0def1`)
**Context:** installing ServerClaw on a freshly reinstalled Debian 13
Hetzner AX41-NVMe, using the 0fork.com identity, under the documented
`make bootstrap` one-command path.

> This diary exists because the operator asked for it explicitly:
> "you can start a diary from my opinion, but make sure we are converging
> to this self-replicating repository structure." Future agents running
> forks should append entries here, not rewrite the history.

## What I was trying to do

Validate that a plain `make bootstrap` — the command in `README.md` and
`CLAUDE.md` — works end-to-end on a host that isn't the author's
production Proxmox. That is the single biggest forkability claim in the
whole repo, and until now no one had actually tested it against a
non-author environment.

## What I found

Four silent gaps (full detail in the 2026-04-22 postmortem + ADR 0437).
In short: `make bootstrap` was written for the author's environment and
each successive overlay ADR (0407, 0430, 0431) added runtime machinery
without retrofitting the top-level operator command. So forks had to use
a bespoke wrapper (`deploy-0fork`), which silently contradicted the
"one command" promise in the docs.

Most surprising: `scripts/generate_inventory.py` — build-time tooling —
was never updated when ADR 0430 shipped, even though ADR 0430's whole
point was to let `.local/host_vars/proxmox-host.yml` override production
topology. Lesson: audit generators under `scripts/` every time a new
overlay layer is introduced. Runtime consumers are obvious; build-time
ones hide.

## What I changed

- `scripts/generate_inventory.py` gained `--host-vars-overlay` and
  `--out` flags. Default behaviour (no flags) is identical to before,
  so production is unaffected.
- `Makefile` gained a 30-line conditional block at the top. When
  `PLATFORM_IDENTITY_OVERLAY` is set, it rewires inventory path, SSH
  key, env, and ansible extras in one place. All four bootstrap stage
  targets + three verify targets pick up the extras automatically.
- `scripts/timed.sh` — generic instrumentation wrapper promoted from
  `.local/0fork-timings/timed-ssh.sh`. Every fork operator now gets
  wall-clock journaling for free under `.local/timings/journal.ndjson`.
- ADR 0437 documents the new contract. The four fork-specific Make
  targets (`deploy-0fork`, `converge-0fork-chain`, `smoke-0fork-mail`,
  `preflight-0fork`) become deprecated shims; they are not deleted
  yet because they are documented in ADR 0431 and runbooks that
  external readers may still be following.

## What I am still holding

**Observations that are not yet fixes.**

- The fresh-Hetzner host arrived with user `root` and Hetzner's own
  authorized_keys. Before `make bootstrap` can SSH as `ops`, something
  has to create the `ops` user and switch SSH away from root. Today
  that is implicit in the Hetzner installimage template the operator
  selected. If a future fork uses a provider whose default user isn't
  `root`, `make bootstrap` Stage 2 will blow up on the first
  `become: true` task. This is out of scope for ADR 0437 but deserves
  its own note; possibly a `make init-remote` stage that idempotently
  enforces ops-user-with-sudo + SSH-key installation before Stage 2
  runs.
- The Hetzner DNS API was in active brownout on 2026-04-21 (POST
  returns HTTP 200 with a 503 body). The wildcard DNS01 certbot flow
  is blocked until 2026-05-20. 0fork's current workaround is to use
  HTTP-01 webroot (`public_edge_acme_challenge_method: webroot` in the
  identity overlay). Any fork that depends on DNS-01 for wildcards
  would hit the same wall. Consider documenting this in the Hetzner
  runbook's "known external failure modes" section.
- I did not run `make bootstrap` end-to-end yet in this session. The
  code changes are validated via `make -np` (variable resolution) and
  `make generate-inventory` (produces correct 10.20.10.X inventory).
  A live-apply run is queued for the next working window.

## What the operator might want to know if they pick this up tomorrow

1. `PLATFORM_IDENTITY_OVERLAY=.local/identity.yml.0fork make bootstrap`
   is the command. Nothing else. If anything else is required, that is
   a bug — file a gap against ADR 0437 before working around it.
2. `scripts/timed.sh` wraps arbitrary commands. Prefix any long-running
   step with it to keep the journal honest:
   `scripts/timed.sh full-bootstrap make bootstrap`.
3. The 0fork host's VMs were wiped at 17:30 UTC on 2026-04-22 to give
   `make bootstrap` a clean canvas to prove itself on. The Proxmox host
   itself (PVE 9.1.9 on kernel 6.17.13-3-pve, vmbr10 bridge, nftables
   rules) is intact — Stages 2–4 of bootstrap should reconcile-in-place
   quickly.
4. If bootstrap fails on a stage: read `/tmp/claude-*/tasks/*.output` or
   `.local/timings/<ts>-<label>.log`, fix the root cause in the committed
   repo, push via PR, and re-run. Avoid hand-patching the host — the
   whole point of this refactor is that the repo state and the host
   state should converge from a single command.

## Successor prompt (for the next agent)

> You are continuing the fork-bootstrap validation on 0fork.com. Read
> ADR 0437, the 2026-04-22 postmortem, and this diary entry first. The
> code changes are in place but end-to-end live-apply is unvalidated.
> Run `PLATFORM_IDENTITY_OVERLAY=.local/identity.yml.0fork
> scripts/timed.sh full-bootstrap make bootstrap` from the repo root.
> Append your findings — including stage-level timings from
> `.local/timings/journal.ndjson` — to this diary under a new
> dated section. If any stage fails, do not work around it in
> `.local/`; fix the root cause in the committed repo and ship a PR.
