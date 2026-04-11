# ws-0368-live-apply — ADR 0368 live apply and completion

## Goal

Close ADR 0368 from its current partial state on `origin/main` by:

- finishing the remaining compose-macro adoption work needed for safe reuse
- reconciling the later hairpin automation path with the original macro design
- live-applying the resulting runtime changes from a fresh `origin/main` base
- recording verification evidence and ADR metadata so a later reader can see
  both the repo state and the live platform state without hidden chat context

## Initial gaps observed on 2026-04-11

- `docs/adr/0368-docker-compose-jinja2-macro-library.md` still says `Status: Proposed`
  even though the repo already contains the shared macro library and partial role adoption.
- Only a minority of `docker-compose.yml.j2` templates import `compose_macros.j2`;
  multiple runtime roles still embed manual OpenBao sidecars, `extra_hosts`, and
  Redis boilerplate.
- Three role-local `compose_macros.j2` files are byte-for-byte duplicates of the
  common macro library, while `plane_runtime` carries a local fork.
- `scripts/generate_cross_cutting_artifacts.py --check --only hairpin` targets the
  generated `inventory/group_vars/platform.yml` / `platform_hairpin.yml` path, so
  this ADR's hairpin automation needs verification as part of the closure work.

## Planned evidence

- branch-local validation output for the macro and hairpin automation path
- live-apply command transcript references and post-apply service verification
- updated ADR metadata documenting repo implementation and verified platform apply
