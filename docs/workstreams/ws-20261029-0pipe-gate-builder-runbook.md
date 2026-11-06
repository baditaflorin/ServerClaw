# WS-20261029: Run the gate on an alternate build server, and how it runs ansible-lint

## Status

In progress. The pull request is open and not merged; nothing is applied. No `[live-apply]` marker.

## Goal

A second build server was made able to run the pre-push gate on 2026-10-29. Where its setup belongs was decided first: the toolchain installer, the build-server config generator, the run and push wrappers and the version-parity check go to the private repository `baditaflorin/0pipe` (the owner moved everything about that server there, and this repository is sanitised for publication, ADR 0409). This repository keeps only what is a property of the gate itself and is read before pushing. No inventory entry and no play were added: the existing `build-server-gate-tools.yml` installs system-wide on a dedicated builder, the alternate server is a shared CI worker that needs an isolated prefix, and a play change cannot be tested without a live apply.

## Change

- `docs/runbooks/validation-gate.md`: a section "Running the Gate on an Alternate Build Server" (what `REMOTE_EXEC_CONFIG` must change, the toolchain and version parity, and three rules: never run the gate on the pusher's machine because the hook's `--local-fallback` reruns the whole gate locally on any remote failure, a shared server is shared, workspace retention and cleanup) and a subsection "How the Gate Runs ansible-lint" (`scripts/validate_repo.sh` uses `uv tool run` with ansible-lint 24.12.2 and ansible-core 2.17.10 when `uv` is on `PATH`; the native binary fails against ansible-core 2.21.0 because `ansible.parsing.yaml.constructor` is gone, which is why the gate passes while the native command does not).
- Records, without changing it, that the play `build-server-gate-tools.yml` is behind the default builder (tofu 1.9.1 against 1.12.6, semgrep 1.88.0 against 1.155.0, no gitleaks): re-running it as it stands would move tofu back. Aligning the play is a separate change.

Not changed: scripts, config, inventory, plays, the default builder. No host is touched by this change.
